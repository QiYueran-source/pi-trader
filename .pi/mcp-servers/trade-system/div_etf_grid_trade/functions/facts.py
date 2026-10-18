"""三类事实计算：风险事实、调节器事实、板块事实。"""
from __future__ import annotations

from typing import Any

from functions.artifacts import artifact
from functions.market import average_range, consecutive_down, fetch_fund_daily, fetch_market_daily, get_client, is_limit_up
from functions.paths import normalize_date
from functions.scaling import apply_factors, floor100
from functions.signals import emotion_facts, leg_signals


def positions_input(value: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict) or "positions" not in value or "cash" not in value:
        raise ValueError("positions 必须包含真实账户快照的 positions 和 cash")
    positions = value.get("positions")
    if not isinstance(positions, dict):
        raise ValueError("positions.positions 必须是对象")
    cash = value.get("cash")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)):
        raise ValueError("positions.cash 必须是数值")
    result = dict(positions)
    result["cash"] = float(cash)
    return result, str(value.get("source", "mcp_input"))


def system_nav(positions: dict[str, Any], instruments: dict[str, Any], closes: dict[str, float]) -> tuple[float, str]:
    market_value = sum(
        int(positions.get(key, {}).get("shares", 0) or 0) * closes.get(key, 0.0)
        for key in instruments["instruments"]
    )
    cash = positions["cash"]
    return market_value + float(cash), "positions.cash"


def risk_facts(target_date: str, parameters: dict[str, dict[str, Any]], positions_value: dict[str, Any] | None) -> dict[str, Any]:
    api_date, directory_date = normalize_date(target_date)
    risk = parameters["risk"]
    instruments = parameters["instruments"]
    positions, position_source = positions_input(positions_value)
    pro = get_client()
    rows_by_id = {key: fetch_fund_daily(pro, instruments["instruments"][key]["ts_code"], api_date, 90) for key in risk["scope"]["instrument_ids"]}
    closes = {key: float(rows[-1]["close"]) for key, rows in rows_by_id.items()}
    nav, nav_source = system_nav(positions, instruments, closes)
    facts: dict[str, Any] = {}
    window = int(risk["volatility"]["average_range_window_trading_days"])
    anomalies = risk["market_anomalies"]
    for key, rows in rows_by_id.items():
        latest = rows[-1]
        previous = float(rows[-2]["close"]) if len(rows) > 1 else float(latest["close"])
        close = float(latest["close"])
        daily_change = close / previous - 1 if previous else 0.0
        vol_rows = rows[-window:]
        avg_volume = sum(float(row["vol"]) for row in vol_rows) / len(vol_rows)
        volume_ratio = float(latest["vol"]) / avg_volume if avg_volume else 0.0
        down_days, down_loss = consecutive_down(rows)
        boundary = risk["price_boundary"]["by_instrument"][key]
        shares = int(positions.get(key, {}).get("shares", 0) or 0)
        market_value = float(positions.get(key, {}).get("market_value_amount", shares * close) or 0.0)
        facts[key] = {
            "market": {"trade_date": latest["trade_date"], "close": close, "daily_change_ratio": round(daily_change, 8), "volume_ratio": round(volume_ratio, 8), "average_range_ratio": round(average_range(rows, window), 8), "consecutive_down_trading_days": down_days, "consecutive_down_loss_ratio": round(down_loss, 8)},
            "price_boundary_reference": {**boundary, "source": f"params/risk.json#price_boundary.by_instrument.{key}"},
            "position": {"shares": shares, "market_value_amount": round(market_value, 2), "leg_weight": round(market_value / nav, 8) if nav else 0.0, "weight_base": "system_nav", "nav_amount": round(nav, 2), "nav_source": nav_source},
            "threshold_hits": {"below_price_boundary": close <= float(boundary["lower_boundary"]), "above_price_boundary": close >= float(boundary["upper_boundary"]), "consecutive_down": down_days >= int(anomalies["consecutive_down_trading_days"]) and down_loss >= float(anomalies["consecutive_down_loss_ratio"]), "sharp_drop_with_volume": daily_change <= -float(anomalies["sharp_drop_ratio"]) and volume_ratio >= float(anomalies["sharp_drop_volume_ratio"]), "sharp_rise_notice": daily_change >= float(anomalies["sharp_rise_notice_ratio"]), "sharp_rise_take_profit_notice": daily_change >= float(anomalies["sharp_rise_take_profit_notice_ratio"])},
        }
    return artifact("risk_facts", directory_date, parameters, {"parameter_schema_version": risk["schema_version"], "version": parameters["regulator"]["version"], "positions_source": position_source, "facts": facts, "note": "v4：采集双标的；系统不计算券商档位价格。"})


def regulator_facts(target_date: str, parameters: dict[str, dict[str, Any]], positions_value: dict[str, Any] | None, human_review: dict[str, Any] | None = None, skip_emotion: bool = False) -> dict[str, Any]:
    api_date, directory_date = normalize_date(target_date)
    regulator, instruments = parameters["regulator"], parameters["instruments"]
    positions, position_source = positions_input(positions_value)
    pro = get_client()
    ids = [key for key in regulator["normal_state"] if key in instruments["instruments"]]
    rows_by_id = {key: fetch_fund_daily(pro, instruments["instruments"][key]["ts_code"], api_date, 120) for key in ids}
    closes = {key: float(rows[-1]["close"]) for key, rows in rows_by_id.items()}
    leg_values = {key: int(positions.get(key, {}).get("shares", 0) or 0) * closes[key] for key in ids}
    cash = positions["cash"]
    cash_amount = float(cash)
    nav = sum(leg_values.values()) + cash_amount
    guard_spec = regulator["capital_guard"]
    ratio = sum(leg_values.values()) / nav if nav else 0.0
    tier_hit = None
    multiplier = 1.0
    for tier in guard_spec["tiers"]:
        if ratio >= float(tier["u"]):
            tier_hit, multiplier = tier, float(tier["step_multiplier"])
    guard = {"weight_base": guard_spec["weight_base"], "nav_amount": round(nav, 2), "usage_ratio": round(ratio, 8), "tier_hit": tier_hit, "step_multiplier": multiplier, "stop_buy": ratio >= float(guard_spec["stop_buy_u"]), "stop_ratio": float(guard_spec["stop_buy_u"]), "resume_ready": ratio <= float(guard_spec["resume_u"]), "resume_ratio": float(guard_spec["resume_u"]), "leg_weights": {key: round(value / nav, 8) if nav else 0.0 for key, value in leg_values.items()}, "leg_max_weight": float(guard_spec["leg_max_weight"]), "leg_cap_breach": {key: (value / nav if nav else 0.0) >= float(guard_spec["leg_max_weight"]) for key, value in leg_values.items()}}
    scaling = regulator["scaling"]
    review = human_review or {"level": "A0", "approved": []}
    level_table = {name: spec for name, spec in regulator["defense_levels"].items() if isinstance(spec, dict)}
    level = str(review.get("level", "A0"))
    per_leg_review = review.get("per_leg") or {}
    if not isinstance(per_leg_review, dict):
        raise ValueError("human_review.per_leg 必须是对象（腿名 → 防守档）")
    unknown = sorted(set(per_leg_review) - set(ids))
    if unknown:
        raise ValueError(f"human_review.per_leg 只支持 {', '.join(sorted(ids))}，收到：{', '.join(unknown)}")
    for name in [level, *(str(value) for value in per_leg_review.values())]:
        if name not in level_table:
            raise ValueError(f"防守档不存在：{name}（可选：{', '.join(sorted(level_table))}）")
    leg_levels = {key: str(per_leg_review.get(key, level)) for key in ids}
    level_spec = level_table[level]
    reserve = regulator.get("reserve_shares", {})
    reserve_enabled = bool(reserve.get("enabled"))
    reserve_floors = reserve.get("per_leg", {}) if reserve_enabled else {}
    legs = {}
    for key, rows in rows_by_id.items():
        normal = regulator["normal_state"][key]
        signals = leg_signals(rows, regulator["signals"])
        defense_step = float(level_table[leg_levels[key]]["step_multiplier"])
        defense_shares = float(level_table[leg_levels[key]]["shares_multiplier"])
        cap = float(guard_spec["step_cap"][key])

        buy_cap = cap if scaling["buy_step_ratio"].get("cap") == "step_cap" else None
        sell_cap = cap if scaling["sell_step_ratio"].get("cap") == "step_cap" else None
        buy_step_raw = apply_factors(normal["buy_step_ratio"], scaling["buy_step_ratio"]["factors"], defense_multiplier=defense_step, capital_multiplier=multiplier)
        buy_step = min(buy_step_raw, buy_cap) if buy_cap is not None else buy_step_raw
        sell_step_raw = apply_factors(normal["sell_step_ratio"], scaling["sell_step_ratio"]["factors"], defense_multiplier=defense_step, capital_multiplier=multiplier)
        sell_step = min(sell_step_raw, sell_cap) if sell_cap is not None else sell_step_raw

        buy_shares_raw = apply_factors(normal["buy_shares"], scaling["buy_shares"]["factors"], defense_multiplier=defense_shares, capital_multiplier=multiplier)
        sell_shares_raw = apply_factors(normal["sell_shares"], scaling["sell_shares"]["factors"], defense_multiplier=defense_shares, capital_multiplier=multiplier)
        buy_shares = floor100(buy_shares_raw) if scaling["buy_shares"].get("rounding") == "floor100" else int(round(buy_shares_raw))
        sell_shares = floor100(sell_shares_raw) if scaling["sell_shares"].get("rounding") == "floor100" else int(round(sell_shares_raw))

        floor_shares = int(reserve_floors.get(key, 0) or 0)
        held_shares = int(positions.get(key, {}).get("shares", 0) or 0)
        reserve_hit = bool(floor_shares) and held_shares <= floor_shares
        sell_enabled = bool(normal["sell_enabled"]) and not reserve_hit
        legs[key] = {
            "ts_code": normal["code"],
            "normal": {field: normal[field] for field in ("buy_step_ratio", "sell_step_ratio", "buy_shares", "sell_shares")},
            "effective": {
                "buy_step_ratio": round(buy_step, 8),
                "buy_raw_step_ratio": round(buy_step_raw, 8),
                "raw_step_ratio": round(buy_step_raw, 8),
                "step_cap": buy_cap,
                "capped": buy_cap is not None and buy_step_raw > buy_cap,
                "buy_shares": buy_shares,
                "buy_enabled": bool(normal["buy_enabled"]) and not guard["stop_buy"] and not guard["leg_cap_breach"][key],
                "sell_step_ratio": round(sell_step, 8),
                "sell_raw_step_ratio": round(sell_step_raw, 8),
                "sell_step_cap": sell_cap,
                "capped_sell": sell_cap is not None and sell_step_raw > sell_cap,
                "sell_shares": sell_shares,
                "sell_enabled": sell_enabled,
                "sell_disabled_reason": "reserve_floor" if reserve_hit else None,
                "reserve_floor": floor_shares,
            },
            "defense_level": leg_levels[key],
            "defense_spec": level_table[leg_levels[key]],
            "close": closes[key],
            "market_value_amount": round(leg_values[key], 2),
            "weight": guard["leg_weights"][key],
            "signals": signals,
        }
    emotion = None if skip_emotion else emotion_facts(pro, api_date, regulator["signals"]["emotion"])
    score = int(emotion.get("quant_score", 0)) if emotion else 0
    def suggest_level(state: str) -> str:
        return "A3" if state == "strong" and score >= 3 else "A2" if state in {"strong", "confirmed"} else "A1" if state in {"weak", "pending"} else "A0"

    states = [leg["signals"]["state"] for leg in legs.values()]
    suggested = "A3" if "strong" in states and score >= 3 else "A2" if "strong" in states or "confirmed" in states else "A1" if "weak" in states or "pending" in states else "A0"
    suggested_per_leg = {key: suggest_level(leg["signals"]["state"]) for key, leg in legs.items()}
    result = {"nav_amount": round(nav, 2), "cash_amount": round(cash_amount, 2), "positions_source": position_source, "capital_guard": guard, "defense": {"requested_level": level, "requested_per_leg": per_leg_review, "effective_levels": leg_levels, "level_spec": level_spec, "suggested_level": suggested, "suggested_per_leg": suggested_per_leg, "suggested_reason": "强确认且情绪极弱→A3；强确认或确认→A2；弱确认/观察中→A1；否则 A0", "approval_required": True, "approval_record": "mcp_input" if human_review else "default", "approved": review.get("approved", []), "plan_after_approval": bool(regulator["approval"]["plan_after_approval"])}, "legs": legs, "boundary_note": "档位价格与锚由券商软件维护（锚不因参数变更而重设）；本文件只输出参数与建议，不含档位价格。买入档距受档距上限约束，卖出档距随防守倍数缩放、不随资金倍数缩放且不设上限；份数按 100 的整数倍向下取整；保底仓触达即停卖该腿（回到下限之上自动恢复）；防守档为体系级（`human_review.level`），可用 `human_review.per_leg` 按腿覆盖。"}
    if emotion is not None:
        result["emotion"] = emotion
    return artifact("regulator_facts", directory_date, parameters, result)


def sector_facts(target_date: str, parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    api_date, directory_date = normalize_date(target_date)
    pro = get_client()
    daily = fetch_market_daily(pro, api_date)
    basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
    industry_by_code = {str(row["ts_code"]): {"name": str(row["name"]), "industry": str(row.get("industry") or "未知")} for row in (basic.to_dict("records") if basic is not None else [])}
    keywords = parameters["sector_classification"]["technology_industry_keywords"]
    sectors: dict[str, Any] = {}
    count = 0
    for row in daily:
        code = str(row["ts_code"])
        pct = float(row.get("pct_chg") or 0.0)
        if not is_limit_up(code, pct):
            continue
        count += 1
        profile = industry_by_code.get(code, {"name": code, "industry": "未知"})
        industry = profile["industry"]
        sector = sectors.setdefault(industry, {"industry": industry, "limit_up_count": 0, "sample_stocks": []})
        sector["limit_up_count"] += 1
        if len(sector["sample_stocks"]) < 3:
            sector["sample_stocks"].append({"ts_code": code, "name": profile["name"], "pct_change_ratio": round(pct / 100, 6)})
    ranked = sorted(sectors.values(), key=lambda item: item["limit_up_count"], reverse=True)
    for sector in ranked:
        sector["is_technology"] = any(keyword in sector["industry"] for keyword in keywords)
    technology = sum(item["limit_up_count"] for item in ranked if item["is_technology"])
    return artifact("sector_facts", directory_date, parameters, {"source_trade_date": api_date, "classification_parameter_version": parameters["sector_classification"]["schema_version"], "limit_up": {"stock_count": count, "sector_count": len(ranked), "technology_stock_count": technology, "technology_stock_ratio": round(technology / count, 8) if count else 0.0}, "top_sectors": ranked[:10]})
