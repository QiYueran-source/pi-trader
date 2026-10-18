"""信号计算：滚动波动、一阶冲击/二阶确认/纯阴跌与情绪面。"""
from __future__ import annotations

from typing import Any

from functions.market import board_limit_ratio, fetch_market_daily, is_limit_down, is_limit_up


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
