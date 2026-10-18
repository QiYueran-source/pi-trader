#!/usr/bin/env python3
"""红利科创 ETF 双网格体系（system-id: div_etf_grid_trade）MCP 服务入口。

一个体系一个服务：实现、`system.yml`、`params/` 与 `templates/` 都在本目录内，
目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `div-etf-grid-trade`。
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = SYSTEM_ROOT.parent
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "红利科创ETF双网格体系"
PARAMETER_FILES = ("grid", "instruments", "regulator", "risk", "runtime", "sector_classification")
EXPANSION_KEYS = {"buy_step_ratio", "sell_step_ratio", "buy_shares", "sell_shares"}
if not (SYSTEM_ROOT / "system.yml").is_file():
    raise RuntimeError(f"体系运行定义缺失：{SYSTEM_ROOT / 'system.yml'}")


def load_env() -> None:
    env_file = REPO_ROOT / ".pi/mcp-servers/tushare/.env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    else:
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        parsed = datetime.strptime(value, fmt).date()
    return parsed.strftime("%Y%m%d"), parsed.strftime("%Y-%m-%d")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON 文件不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效：{path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象：{path}")
    return value


def floor100(value: float) -> int:
    """申报份数取整：向下取到 100 的整数倍，最小 100 份（ETF 最小交易单位）。"""
    return max(100, int(value // 100) * 100)


def apply_factors(value: float, factors: Any, *, defense_multiplier: float, capital_multiplier: float) -> float:
    """按 params/regulator.json#scaling 声明的因子列表缩放一个量。"""
    result = float(value)
    if not isinstance(factors, list):
        raise ValueError("scaling 的 factors 必须是数组")
    for factor in factors:
        if factor == "defense":
            result *= float(defense_multiplier)
        elif factor == "capital":
            result *= float(capital_multiplier)
        else:
            raise ValueError(f"未知缩放因子：{factor}")
    return result


def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: read_json(PARAMS_ROOT / f"{name}.json") for name in PARAMETER_FILES}
    validate_parameters(parameters)
    return parameters


def validate_parameters(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(parameters) != set(PARAMETER_FILES):
        raise ValueError(f"参数文件必须为：{', '.join(PARAMETER_FILES)}")
    for name, value in parameters.items():
        version = value.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError(f"{name}.schema_version 必须是不小于 1 的整数")
    instruments = parameters["instruments"].get("instruments")
    if not isinstance(instruments, dict) or set(instruments) != {"dividend", "growth"}:
        raise ValueError("instruments.instruments 必须且只能包含 dividend 与 growth")
    regulator = parameters["regulator"]
    normal = {key: value for key, value in regulator.get("normal_state", {}).items() if not key.startswith("note")}
    if not isinstance(normal, dict) or set(normal) != {"dividend", "growth"}:
        raise ValueError("regulator.normal_state 必须包含 dividend 与 growth")
    guard = regulator.get("capital_guard", {})
    if float(guard.get("resume_u", 1)) >= float(guard.get("stop_buy_u", 0)):
        raise ValueError("capital_guard.resume_u 必须低于 stop_buy_u")
    scaling = regulator.get("scaling")
    declared = {name: value for name, value in scaling.items() if not name.startswith("note")} if isinstance(scaling, dict) else {}
    if set(declared) != EXPANSION_KEYS:
        raise ValueError(f"regulator.scaling 必须且只能包含：{', '.join(sorted(EXPANSION_KEYS))}")
    scaling = declared
    for name in sorted(EXPANSION_KEYS):
        item = scaling[name]
        if not isinstance(item, dict):
            raise ValueError(f"scaling.{name} 必须是对象")
        factors = item.get("factors")
        if not isinstance(factors, list) or not factors or any(factor not in {"defense", "capital"} for factor in factors):
            raise ValueError(f"scaling.{name}.factors 必须是非空数组且只含 defense / capital")
        if item.get("cap") not in {None, "step_cap"}:
            raise ValueError(f"scaling.{name}.cap 只能是 null 或 step_cap")
        if item.get("rounding") not in {None, "floor100"}:
            raise ValueError(f"scaling.{name}.rounding 只能是 null 或 floor100")
    for name in ("buy_shares", "sell_shares"):
        item = scaling[name]
        if item.get("cap") is not None:
            raise ValueError(f"scaling.{name} 不支持 cap（档距上限只用于档距）")
    for name in ("buy_step_ratio", "sell_step_ratio"):
        if scaling[name].get("rounding") is not None:
            raise ValueError(f"scaling.{name} 不支持 rounding（取整只用于份数）")
    for key in normal:
        for field in ("buy_shares", "sell_shares"):
            shares = normal[key].get(field)
            if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0 or shares % 100:
                raise ValueError(f"regulator.normal_state.{key}.{field} 必须是 100 的正整数倍")
    reserve = regulator.get("reserve_shares", {})
    if reserve.get("enabled"):
        if reserve.get("mode") != "shares":
            raise ValueError("reserve_shares.mode 目前只支持 shares")
        per_leg = reserve.get("per_leg")
        if not isinstance(per_leg, dict) or set(per_leg) != {"dividend", "growth"}:
            raise ValueError("reserve_shares.per_leg 必须包含 dividend 与 growth")
        for key in sorted(per_leg):
            floor_shares = per_leg[key]
            if not isinstance(floor_shares, int) or isinstance(floor_shares, bool) or floor_shares < 0 or floor_shares % 100:
                raise ValueError(f"reserve_shares.per_leg.{key} 必须是 100 的非负整数倍")
    if regulator.get("policy", {}).get("liquidation") != "forbidden":
        raise ValueError("v4 禁止清仓")
    if regulator.get("policy", {}).get("reduce_position") != "forbidden":
        raise ValueError("v4 禁止减仓")
    return {"valid": True, "files": list(PARAMETER_FILES)}


def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": parameters["regulator"].get("version", "unknown"),
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }


def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()


def fetch_fund_daily(pro: Any, code: str, api_date: str, calendar_days: int) -> list[dict[str, Any]]:
    end = datetime.strptime(api_date, "%Y%m%d")
    frame = pro.fund_daily(
        ts_code=code,
        start_date=(end - timedelta(days=calendar_days)).strftime("%Y%m%d"),
        end_date=api_date,
        fields="trade_date,close,high,low,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {code} 的行情")
    rows = []
    for row in frame.sort_values("trade_date").to_dict("records"):
        rows.append({key: (str(row[key]) if key == "trade_date" else float(row[key])) for key in ("trade_date", "close", "high", "low", "vol", "amount")})
    if rows[-1]["trade_date"] != api_date:
        raise ValueError(f"{code} 的目标日期没有行情：{api_date}")
    return rows


def fetch_market_daily(pro: Any, api_date: str) -> list[dict[str, Any]]:
    frame = pro.daily(trade_date=api_date, fields="ts_code,pct_chg")
    if frame is None or frame.empty:
        raise ValueError(f"无 {api_date} 全市场日线数据")
    return frame.to_dict("records")


def board_limit_ratio(code: str) -> float:
    raw = code.split(".", 1)[0]
    if code.endswith(".BJ") or raw.startswith(("8", "4", "92")):
        return 0.30
    if raw.startswith(("30", "68")):
        return 0.20
    return 0.10


def is_limit_up(code: str, pct_change: float) -> bool:
    return pct_change / 100 >= board_limit_ratio(code) - 0.002


def is_limit_down(code: str, pct_change: float) -> bool:
    return pct_change / 100 <= -(board_limit_ratio(code) - 0.002)


def consecutive_down(rows: list[dict[str, Any]]) -> tuple[int, float]:
    days = 0
    cumulative = 0.0
    for index in range(len(rows) - 1, 0, -1):
        current = float(rows[index]["close"])
        previous = float(rows[index - 1]["close"])
        if current >= previous:
            break
        days += 1
        cumulative = 1 - (1 - cumulative) * current / previous
    return days, cumulative


def average_range(rows: list[dict[str, Any]], window: int) -> float:
    values = []
    for index in range(1, len(rows)):
        previous = float(rows[index - 1]["close"])
        if previous > 0:
            values.append((float(rows[index]["high"]) - float(rows[index]["low"])) / previous)
    values = values[-window:]
    return sum(values) / len(values) if values else 0.0


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


def rolling_sigma(rows: list[dict[str, Any]], index: int, window: int) -> float:
    values = [float(rows[i]["close"]) / float(rows[i - 1]["close"]) - 1 for i in range(1, index + 1)][-window:]
    if len(values) < 2:
        return 0.012
    mean = sum(values) / len(values)
    return max((sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5, 0.0005)


def leg_signals(rows: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    last = len(rows) - 1
    shock_spec, second, bleed = spec["shock"], spec["second_order"], spec["slow_bleed"]
    sigma_now = rolling_sigma(rows, last, int(shock_spec["window"]))
    shock = None
    for index in range(last, 0, -1):
        change = float(rows[index]["close"]) / float(rows[index - 1]["close"]) - 1
        sigma = rolling_sigma(rows, index, int(shock_spec["window"]))
        threshold = max(float(shock_spec["min_pct"]), float(shock_spec["sigma_mult"]) * sigma)
        if change <= -threshold:
            shock = {"index": index, "trade_date": rows[index]["trade_date"], "drop_ratio": round(-change, 8), "sigma": round(sigma, 8), "sigma_multiple": round(-change / sigma, 3) if sigma else None}
            break
    second_order: dict[str, Any] = {"state": "none"}
    if shock:
        index = shock["index"]
        t0 = float(rows[index]["close"])
        elapsed = last - index
        recovered = float(rows[last]["close"]) / t0 - 1 if t0 else 0.0
        target = float(second["recover_ratio"]) * shock["drop_ratio"]
        prior = [float(row["close"]) for row in rows[max(0, index - int(second["new_low_window_days"])):index]]
        lowest = min(float(row["close"]) for row in rows[index:])
        state = "recovered" if recovered >= target else "strong" if prior and lowest < min(prior) else "confirmed" if elapsed > int(second["window_days"]) else "pending"
        second_order = {"state": state, "days_elapsed": elapsed, "recovered_ratio": round(recovered, 8), "recovery_target": round(target, 8), "prior_low": min(prior) if prior else None, "lowest_since_shock": round(lowest, 6)}
    down_days = 0
    cumulative = 0.0
    for index in range(last, 0, -1):
        change = float(rows[index]["close"]) / float(rows[index - 1]["close"]) - 1
        if change >= 0:
            break
        down_days += 1
        cumulative = 1 - (1 - cumulative) * (1 + change)
    threshold = max(float(bleed["cum_pct"]), float(bleed["sigma_mult"]) * sigma_now)
    slow = {"down_days": down_days, "cumulative_loss_ratio": round(cumulative, 8), "threshold": round(threshold, 8), "hit": down_days >= int(bleed["down_days"]) and cumulative >= threshold}
    state = "strong" if second_order["state"] == "strong" else "confirmed" if second_order["state"] == "confirmed" else "weak" if slow["hit"] else "pending" if second_order["state"] == "pending" else "none"
    return {"shock": shock, "second_order": second_order, "slow_bleed": slow, "state": state, "sigma20": round(sigma_now, 8), "basis": {"sigma_window": int(shock_spec["window"]), "min_pct": float(shock_spec["min_pct"]), "sigma_mult": float(shock_spec["sigma_mult"])} }


def emotion_facts(pro: Any, api_date: str, spec: dict[str, Any]) -> dict[str, Any]:
    rows = fetch_market_daily(pro, api_date)
    limit_up = limit_down = advance = decline = 0
    for row in rows:
        code = str(row["ts_code"])
        if code.startswith(("N", "C")):
            continue
        change = float(row.get("pct_chg") or 0.0) / 100
        ratio = board_limit_ratio(code)
        if is_limit_up(code, float(row.get("pct_chg") or 0.0)):
            limit_up += 1
        if is_limit_down(code, float(row.get("pct_chg") or 0.0)):
            limit_down += 1
        advance += change > 0
        decline += change < 0
    tiers, ratios = spec["limit_down_count"], spec["advance_decline_ratio"]
    score = (2 if limit_down >= int(tiers["l1"]) else 0) + (1 if limit_down >= int(tiers["l2"]) else 0)
    score += (2 if decline and advance / decline <= 1 / float(ratios["l1"]) else 0) + (1 if decline and advance / decline <= 1 / float(ratios["l2"]) else 0)
    if advance and decline and advance / decline >= 2.5:
        score = 0
    return {"available": True, "limit_up_board_aware": limit_up, "limit_down_board_aware": limit_down, "advance": advance, "decline": decline, "quant_score": min(score, 4), "narrative_label": None, "narrative_note": "文本性质由任务侧结合知识库资料填写", "board_aware": True}


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
    level = str(review.get("level", "A0"))
    level_spec = regulator["defense_levels"].get(level, regulator["defense_levels"]["A0"])
    reserve = regulator.get("reserve_shares", {})
    reserve_enabled = bool(reserve.get("enabled"))
    reserve_floors = reserve.get("per_leg", {}) if reserve_enabled else {}
    legs = {}
    for key, rows in rows_by_id.items():
        normal = regulator["normal_state"][key]
        signals = leg_signals(rows, regulator["signals"])
        defense_step = float(level_spec["step_multiplier"])
        defense_shares = float(level_spec["shares_multiplier"])
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
            "close": closes[key],
            "market_value_amount": round(leg_values[key], 2),
            "weight": guard["leg_weights"][key],
            "signals": signals,
        }
    emotion = None if skip_emotion else emotion_facts(pro, api_date, regulator["signals"]["emotion"])
    score = int(emotion.get("quant_score", 0)) if emotion else 0
    states = [leg["signals"]["state"] for leg in legs.values()]
    suggested = "A3" if "strong" in states and score >= 3 else "A2" if "strong" in states or "confirmed" in states else "A1" if "weak" in states or "pending" in states else "A0"
    result = {"nav_amount": round(nav, 2), "cash_amount": round(cash_amount, 2), "positions_source": position_source, "capital_guard": guard, "defense": {"requested_level": level, "level_spec": level_spec, "suggested_level": suggested, "suggested_reason": "强确认且情绪极弱→A3；强确认或确认→A2；弱确认/观察中→A1；否则 A0", "approval_required": True, "approval_record": "mcp_input" if human_review else "default", "approved": review.get("approved", []), "plan_after_approval": bool(regulator["approval"]["plan_after_approval"])}, "legs": legs, "boundary_note": "档位价格与锚由券商软件维护（锚不因参数变更而重设）；本文件只输出参数与建议，不含档位价格。买入档距受档距上限约束，卖出档距随防守倍数缩放、不随资金倍数缩放且不设上限；份数按 100 的整数倍向下取整；保底仓触达即停卖该腿（回到下限之上自动恢复）。"}
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


def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    return {"date": directory_date, "system_id": SYSTEM_ID, "artifact": kind, "generated_at": datetime.now(timezone.utc).isoformat(), "version": parameters["regulator"].get("version", "unknown"), **parameter_metadata(parameters), **payload}


def process_dir(directory_date: str) -> Path:
    runtime = read_json(PARAMS_ROOT / "runtime.json")
    return REPO_ROOT / runtime["process_root"] / directory_date / SYSTEM_NAME


def write_artifact(document: dict[str, Any], filename: str) -> str:
    path = process_dir(document["date"]) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def render_artifact(kind: str, document: dict[str, Any]) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    mapping = {"risk_facts": "risk_facts.md.j2", "sector_facts": "sector_facts.md.j2", "regulator_facts": "regulator_facts.md.j2"}
    if kind not in mapping:
        raise ValueError(f"不支持的渲染目标：{kind}")
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(mapping[kind]).render(data=document, source_path=f"交易/过程资料/{document['date']}/{SYSTEM_NAME}/{kind}.json", report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{document['date']}:{kind}").hex, updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    path = process_dir(document["date"]) / f"{kind}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {"path": str(path), "artifact": kind, "system_id": SYSTEM_ID, "date": document["date"]}


def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    validate_parameters(parameters)
    operation = arguments.get("operation")
    if operation == "risk_facts":
        result = risk_facts(arguments["date"], parameters, arguments.get("positions"))
    elif operation == "regulator_facts":
        result = regulator_facts(arguments["date"], parameters, arguments.get("positions"), arguments.get("human_review"), bool(arguments.get("skip_emotion", False)))
    elif operation == "sector_facts":
        result = sector_facts(arguments["date"], parameters)
    else:
        raise ValueError("operation 必须是 risk_facts、regulator_facts 或 sector_facts")
    if not arguments.get("dry_run", False):
        path = write_artifact(result, f"{operation}.json")
        result["output_path"] = path
    return result


TOOLS = [
    Tool(name="list_systems", description="列出已注册的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_manifest", description="查看红利科创 ETF 双网格体系运行定义和支持的操作。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="validate_parameters", description="校验指定交易体系当前参数。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="calculate", description="计算双网格风险事实、调节器事实或板块事实；默认写入日期化过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "operation": {"type": "string", "enum": ["risk_facts", "regulator_facts", "sector_facts"]}, "date": {"type": "string"}, "positions": {"type": "object", "required": ["positions", "cash"]}, "human_review": {"type": "object"}, "skip_emotion": {"type": "boolean"}, "dry_run": {"type": "boolean"}}, "required": ["system_id", "operation", "date"]}),
    Tool(name="render", description="渲染已生成的双网格 JSON 事实为 Markdown；`document` 省略时按 `date` + `artifact` 读同日过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "artifact": {"type": "string", "enum": ["risk_facts", "sector_facts", "regulator_facts"]}, "date": {"type": "string"}, "document": {"type": "object"}}, "required": ["system_id", "artifact", "date"]}),
]

server = Server("div-etf-grid-trade")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": ["risk_facts", "regulator_facts", "sector_facts"]}]}
        elif name == "get_manifest":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = {"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "system_root": str(SYSTEM_ROOT), "parameter_root": str(PARAMS_ROOT), "template_root": str(TEMPLATES_ROOT), "operations": ["risk_facts", "regulator_facts", "sector_facts"], "writes_to": "knowledge/交易/过程资料/{date}/红利科创ETF双网格体系", "expansion": {"declaration": "regulator.scaling", "note": "每个量吃哪些倍数由 params/regulator.json#scaling 声明：买入档距=防守×资金且受档距上限；卖出档距=防守且无上限；买卖份数=防守份数倍数并按 100 份向下取整", "multiplier_sources": {"defense": "regulator.defense_levels[].step_multiplier / shares_multiplier", "capital": "regulator.capital_guard.tiers[].step_multiplier"}}, "reserve_shares": "regulator.reserve_shares（enabled=true 时持仓 ≤ 保底下限即停卖该腿，产物给 sell_disabled_reason=reserve_floor）", "leg_effective_fields": ["buy_step_ratio", "buy_raw_step_ratio", "step_cap", "capped", "buy_shares", "buy_enabled", "sell_step_ratio", "sell_raw_step_ratio", "sell_shares", "sell_enabled", "sell_disabled_reason", "reserve_floor"]}
        elif name == "validate_parameters":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "calculate":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = tool_calculate(args)
        elif name == "render":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            _, directory_date = normalize_date(args["date"])
            document = args.get("document")
            if document is None:
                document = read_json(process_dir(directory_date) / f"{args['artifact']}.json")
            if not isinstance(document, dict):
                raise ValueError("document 必须是 JSON 对象")
            if document.get("date") != directory_date:
                raise ValueError("document.date 与 date 不一致")
            result = render_artifact(args["artifact"], document)
        else:
            raise ValueError(f"未知工具：{name}")
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


async def list_tools_legacy() -> list[Tool]:
    return list_tools_result()


async def call_tool_legacy(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    return call_tool_result(name, arguments)


if hasattr(server, "list_tools") and hasattr(server, "call_tool"):
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list_tools_result()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return call_tool_result(name, arguments)
else:
    async def list_tools(_context: Any, _params: Any) -> Any:
        from mcp.types import ListToolsResult
        return ListToolsResult(tools=TOOLS)

    async def call_tool(_context: Any, params: Any) -> Any:
        from mcp.types import CallToolResult
        content = call_tool_result(params.name, params.arguments or {})
        return CallToolResult(content=content)

    server = Server(
        "div-etf-grid-trade",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
