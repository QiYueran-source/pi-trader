#!/usr/bin/env python3
"""v4：按 params/regulator.json 计算硬闸占用、实际档距、信号评估与建议防守档。

只输出参数与建议，不产生交易决策，不自动切换防守档。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from runtime_support import (
    SYSTEM_ID,
    artifact_path,
    load_parameters,
    logical_path,
    normalize_date,
    read_json,
    tushare_client,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格 v4 调节器事实")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--positions", required=True, help="持仓事实 JSON（positions.json）")
    parser.add_argument("--human-review", help="审批留痕 JSON；缺省时读取当日 human_review.json（若存在）")
    parser.add_argument("--skip-emotion", action="store_true", help="跳过全市场情绪量化（节省接口调用）")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def fetch_daily(pro: Any, ts_code: str, api_date: str, calendar_days: int = 120) -> list[dict[str, float | str]]:
    end = datetime.strptime(api_date, "%Y%m%d")
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=(end - timedelta(days=calendar_days)).strftime("%Y%m%d"),
        end_date=api_date,
        fields="trade_date,close,high,low,vol",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情")
    return [
        {
            "trade_date": str(row["trade_date"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "vol": float(row["vol"]),
        }
        for row in frame.sort_values("trade_date").to_dict("records")
    ]


def returns(rows: list[dict[str, float | str]]) -> list[float]:
    return [float(rows[i]["close"]) / float(rows[i - 1]["close"]) - 1 for i in range(1, len(rows))]


def rolling_sigma(rows: list[dict[str, float | str]], index: int, window: int) -> float:
    rets = returns(rows[: index + 1])[-window:]
    if len(rets) < 2:
        return 0.012
    mean = sum(rets) / len(rets)
    variance = sum((value - mean) ** 2 for value in rets) / len(rets)
    return max(variance ** 0.5, 0.0005)


def leg_signals(rows: list[dict[str, float | str]], spec: dict[str, Any]) -> dict[str, Any]:
    """一阶冲击 → 二阶确认；另有纯阴跌判定。只评估，不动作。"""
    shock_spec = spec["shock"]
    second = spec["second_order"]
    bleed = spec["slow_bleed"]
    last_index = len(rows) - 1
    sigma_now = rolling_sigma(rows, last_index, int(shock_spec.get("window", 20)))

    shock: dict[str, Any] | None = None
    for index in range(last_index, 0, -1):
        change = float(rows[index]["close"]) / float(rows[index - 1]["close"]) - 1
        sigma = rolling_sigma(rows, index, int(shock_spec.get("window", 20)))
        threshold = max(float(shock_spec["min_pct"]), float(shock_spec["sigma_mult"]) * sigma)
        if change <= -threshold:
            shock = {"index": index, "trade_date": rows[index]["trade_date"], "drop_ratio": round(-change, 8), "sigma": round(sigma, 8), "sigma_multiple": round(-change / sigma, 3) if sigma else None}
            break

    second_order: dict[str, Any] = {"state": "none"}
    if shock is not None:
        index = shock["index"]
        t0_close = float(rows[index]["close"])
        days_elapsed = last_index - index
        recovered = float(rows[last_index]["close"]) / t0_close - 1 if t0_close else 0.0
        recovery_target = float(second["recover_ratio"]) * shock["drop_ratio"]
        new_low_window = int(second["new_low_window_days"])
        prior_closes = [float(row["close"]) for row in rows[max(0, index - new_low_window): index]]
        prior_low = min(prior_closes) if prior_closes else None
        lowest_since = min(float(row["close"]) for row in rows[index:])
        if recovered >= recovery_target:
            state = "recovered"
        elif prior_low is not None and lowest_since < prior_low:
            state = "strong"
        elif days_elapsed > int(second["window_days"]):
            state = "confirmed"
        else:
            state = "pending"
        second_order = {
            "state": state,
            "days_elapsed": days_elapsed,
            "recovered_ratio": round(recovered, 8),
            "recovery_target": round(recovery_target, 8),
            "prior_low": prior_low,
            "lowest_since_shock": round(lowest_since, 6),
        }

    down_days = 0
    cumulative = 0.0
    for index in range(last_index, 0, -1):
        change = float(rows[index]["close"]) / float(rows[index - 1]["close"]) - 1
        if change >= 0:
            break
        down_days += 1
        cumulative = 1 - (1 - cumulative) * (1 + change)
    bleed_threshold = max(float(bleed["cum_pct"]), float(bleed["sigma_mult"]) * sigma_now)
    slow_bleed = {
        "down_days": down_days,
        "cumulative_loss_ratio": round(cumulative, 8),
        "threshold": round(bleed_threshold, 8),
        "hit": down_days >= int(bleed["down_days"]) and cumulative >= bleed_threshold,
    }

    state = "none"
    if second_order["state"] == "strong":
        state = "strong"
    elif second_order["state"] == "confirmed":
        state = "confirmed"
    elif slow_bleed["hit"]:
        state = "weak"
    elif second_order["state"] == "pending":
        state = "pending"
    return {
        "shock": shock,
        "second_order": second_order,
        "slow_bleed": slow_bleed,
        "state": state,
        "sigma20": round(sigma_now, 8),
        "basis": {"sigma_window": int(shock_spec.get("window", 20)), "min_pct": float(shock_spec["min_pct"]), "sigma_mult": float(shock_spec["sigma_mult"])},
    }


def board_limit_ratio(ts_code: str) -> float:
    code = ts_code.split(".")[0]
    if code.startswith(("300", "301", "302", "688", "689")):
        return 0.20
    if code.startswith(("8", "4", "92")):
        return 0.30
    return 0.10


def emotion_facts(pro: Any, api_date: str, spec: dict[str, Any]) -> dict[str, Any]:
    frame = pro.daily(trade_date=api_date)
    if frame is None or frame.empty:
        return {"available": False, "note": "未获取到全市场日线"}
    limit_down = 0
    limit_up = 0
    advance = 0
    decline = 0
    for row in frame.to_dict("records"):
        code = str(row["ts_code"])
        if code.startswith(("N", "C")):
            continue
        change = float(row["pct_chg"]) / 100
        ratio = board_limit_ratio(code)
        if change >= ratio - 0.02:
            limit_up += 1
        if change <= -(ratio - 0.02):
            limit_down += 1
        if change > 0:
            advance += 1
        elif change < 0:
            decline += 1
    tiers = spec["limit_down_count"]
    ratio_tiers = spec["advance_decline_ratio"]
    score = 0
    if limit_down >= int(tiers["l1"]):
        score += 2
    if limit_down >= int(tiers["l2"]):
        score += 1
    if decline and advance / decline <= 1 / float(ratio_tiers["l1"]):
        score += 2
    if decline and advance / decline <= 1 / float(ratio_tiers["l2"]):
        score += 1
    if advance and decline and advance / decline >= 2.5:
        score = 0
    return {
        "available": True,
        "limit_up_board_aware": limit_up,
        "limit_down_board_aware": limit_down,
        "advance": advance,
        "decline": decline,
        "quant_score": min(score, 4),
        "narrative_label": None,
        "narrative_note": "文本性质（结构性恶化 / 一次性外部冲击 / 无明确催化）由任务侧读取知识库资料后填写",
        "board_aware": True,
    }


def capital_guard(nav: float, leg_values: dict[str, float], guard: dict[str, Any]) -> dict[str, Any]:
    ratio = sum(leg_values.values()) / nav if nav else 0.0
    multiplier = 1.0
    tier_hit = None
    for tier in guard["tiers"]:
        if ratio >= float(tier["u"]):
            multiplier = float(tier["step_multiplier"])
            tier_hit = tier
    stop = ratio >= float(guard["stop_buy_u"])
    resume = ratio <= float(guard["resume_u"])
    breaches = {instrument_id: (value / nav if nav else 0.0) >= float(guard["leg_max_weight"]) for instrument_id, value in leg_values.items()}
    return {
        "weight_base": guard["weight_base"],
        "nav_amount": round(nav, 2),
        "usage_ratio": round(ratio, 8),
        "tier_hit": tier_hit,
        "step_multiplier": multiplier,
        "stop_buy": stop,
        "stop_ratio": float(guard["stop_buy_u"]),
        "resume_ready": resume,
        "resume_ratio": float(guard["resume_u"]),
        "leg_weights": {instrument_id: round(value / nav, 8) if nav else 0.0 for instrument_id, value in leg_values.items()},
        "leg_max_weight": float(guard["leg_max_weight"]),
        "leg_cap_breach": breaches,
    }


def load_review(path: str | None, directory_date: str) -> tuple[dict[str, Any], str]:
    if path:
        return read_json(__import__("pathlib").Path(path)), logical_path(path)
    candidate = artifact_path(directory_date, "human_review.json")
    if candidate.is_file():
        return read_json(candidate), logical_path(candidate)
    return {"level": "A0", "approved": []}, "default"


def main() -> None:
    args = parse_args()
    api_date, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    regulator = parameters["regulator"]
    risk = parameters["risk"]
    instruments = parameters["instruments"]
    positions, position_source = load_positions(args.positions)
    pro = tushare_client()

    instrument_ids = [key for key, value in regulator["normal_state"].items() if isinstance(value, dict)]
    rows_by_instrument = {
        instrument_id: fetch_daily(pro, instruments["instruments"][instrument_id]["ts_code"], api_date)
        for instrument_id in instrument_ids
    }
    closes = {instrument_id: float(rows[-1]["close"]) for instrument_id, rows in rows_by_instrument.items()}
    leg_values = {
        instrument_id: int(positions.get(instrument_id, {}).get("shares", 0) or 0) * closes[instrument_id]
        for instrument_id in rows_by_instrument
    }
    cash = positions.get("cash")
    cash_amount = float(cash) if isinstance(cash, (int, float)) and not isinstance(cash, bool) else float(instruments["account"]["total_capital_amount"])
    nav = sum(leg_values.values()) + cash_amount

    guard = capital_guard(nav, leg_values, regulator["capital_guard"])
    review, review_source = load_review(args.human_review, directory_date)
    level = str(review.get("level", "A0"))
    level_spec = regulator["defense_levels"].get(level, regulator["defense_levels"]["A0"])

    legs: dict[str, Any] = {}
    for instrument_id, rows in rows_by_instrument.items():
        normal = regulator["normal_state"][instrument_id]
        signals = leg_signals(rows, regulator["signals"])
        raw_step = float(normal["buy_step_ratio"]) * float(level_spec["step_multiplier"]) * float(guard["step_multiplier"])
        cap = float(regulator["capital_guard"]["step_cap"][instrument_id])
        effective_step = min(raw_step, cap)
        shares = int(round(int(normal["buy_shares"]) * float(level_spec["shares_multiplier"])))
        legs[instrument_id] = {
            "ts_code": normal["code"],
            "normal": {"buy_step_ratio": normal["buy_step_ratio"], "sell_step_ratio": normal["sell_step_ratio"], "buy_shares": normal["buy_shares"], "sell_shares": normal["sell_shares"]},
            "effective": {"buy_step_ratio": round(effective_step, 8), "raw_step_ratio": round(raw_step, 8), "step_cap": cap, "capped": raw_step > cap, "buy_shares": shares, "buy_enabled": bool(normal["buy_enabled"]) and not guard["stop_buy"] and not guard["leg_cap_breach"].get(instrument_id, False), "sell_enabled": bool(normal["sell_enabled"])},
            "close": closes[instrument_id],
            "market_value_amount": round(leg_values[instrument_id], 2),
            "weight": guard["leg_weights"].get(instrument_id, 0.0),
            "signals": signals,
        }

    emotion = None if args.skip_emotion else emotion_facts(pro, api_date, regulator["signals"]["emotion"])
    emotion_score = int(emotion.get("quant_score", 0)) if emotion else 0
    states = [leg["signals"]["state"] for leg in legs.values()]
    if "strong" in states and emotion_score >= 3:
        suggested = "A3"
    elif "strong" in states or "confirmed" in states:
        suggested = "A2"
    elif "weak" in states or "pending" in states:
        suggested = "A1"
    else:
        suggested = "A0"

    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "regulator_facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": regulator["version"],
        "positions_source": position_source,
        "nav_amount": round(nav, 2),
        "cash_amount": round(cash_amount, 2),
        "capital_guard": guard,
        "defense": {
            "requested_level": level,
            "level_spec": level_spec,
            "suggested_level": suggested,
            "suggested_reason": "按风控调节器.md 映射：强确认且情绪极弱（量化分≥3）→A3；强确认或确认→A2；弱确认/观察中→A1；否则 A0",
            "approval_required": True,
            "approval_record": review_source,
            "approved": review.get("approved", []),
            "plan_after_approval": bool(regulator["approval"]["plan_after_approval"]),
        },
        "legs": legs,
        "boundary_note": "档位价格与锚由券商软件维护；本文件只输出参数与建议，不含档位价格。",
    }
    if emotion is not None:
        output["emotion"] = emotion
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "regulator_facts.json")
    write_json(path, output)
    print(path)


def load_positions(path: str) -> tuple[dict[str, Any], str]:
    document = read_json(__import__("pathlib").Path(path))
    positions = document.get("positions")
    if not isinstance(positions, dict):
        raise ValueError("持仓事实必须包含 positions 对象")
    positions = dict(positions)
    cash = document.get("cash")
    if isinstance(cash, (int, float)) and not isinstance(cash, bool):
        positions["cash"] = float(cash)
    return positions, logical_path(path)


if __name__ == "__main__":
    main()
