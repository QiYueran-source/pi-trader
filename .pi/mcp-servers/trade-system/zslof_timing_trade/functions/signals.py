"""信号判定、判据组装与从锚日重放校验。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from functions.artifacts import artifact
from functions.market import fetch_daily, get_client
from functions.paths import SYSTEM_ID, normalize_date, process_dir, read_json
from functions.state import advance_state, initial_state, state_lookup

def action_tomorrow(signal: str | None, strategy_position: str) -> str:
    actions = {"buy": "buy", "sell": "sell_all", "stop_loss_sell": "sell_all", "chase_buy": "buy"}
    return actions.get(signal, "hold" if strategy_position == "hold" else "no_action")

def build_checks(before: dict[str, Any], after: dict[str, Any], close: float, timing: dict[str, Any]) -> list[dict[str, Any]]:
    """把当日判定拆成结构化判据，供报告渲染与复核。"""
    confirmation_days = int(timing["confirmation_days"])
    checks: list[dict[str, Any]] = []

    if before["strategy_position"] == "flat":
        trough = before["trough"]
        if after["trough"] == trough:
            checks.append({"label": "非创新低", "met": False, "detail": f"收盘 {close} 未严格低于空仓期谷值 {trough}；谷值不变，no_low_days 累计至 {after['no_low_days']}"})
        else:
            checks.append({"label": "创新低", "met": True, "detail": f"收盘 {close} 低于原谷值 {trough} → 谷值更新为 {after['trough']}，no_low_days 归零"})
        count_leg = after["no_low_days"] >= confirmation_days
        price_leg = after["trough"] is not None and close > float(after["trough"])
        checks.append({
            "label": "普通买入条件",
            "met": bool(count_leg and price_leg),
            "detail": f"计数腿 {after['no_low_days']} ≥ {confirmation_days}：{'成立' if count_leg else '不成立'}；价格腿 收盘 {close} 严格高于谷值 {after['trough']}：{'成立' if price_leg else '不成立'}",
        })
        anchor = before["last_sell_peak"]
        if anchor is None:
            checks.append({"label": "追回买入条件", "met": None, "detail": "无追回锚（last_sell_peak 为空）"})
        else:
            checks.append({
                "label": "追回买入条件",
                "met": close > float(anchor),
                "detail": f"追回锚 {anchor}；收盘 {close} {'严格高于' if close > float(anchor) else '未突破'}（差 {round(float(anchor) - close, 6)}）",
            })
        checks.append({"label": "止损", "met": None, "detail": "空仓期不检查止损（止损仅作用于持仓期跌破买入前谷值）"})
    else:
        peak = before["peak"]
        if after["peak"] != peak:
            checks.append({"label": "创出新高", "met": True, "detail": f"收盘 {close} 高于原峰值 {peak} → 峰值更新为 {after['peak']}，no_high_days 归零"})
        else:
            checks.append({"label": "未创出新高", "met": False, "detail": f"收盘 {close} 未高于峰值 {peak}；no_high_days 累计至 {after['no_high_days']}"})
        buy_trough = before["buy_trough"]
        if not timing["stop_loss_enabled"]:
            checks.append({"label": "止损条件", "met": None, "detail": "未启用止损"})
        elif buy_trough is None:
            checks.append({"label": "止损条件", "met": None, "detail": "无买入前谷值（buy_trough 为空）"})
        else:
            checks.append({"label": "止损条件", "met": close < float(buy_trough), "detail": f"买入前谷值 {buy_trough}；收盘 {close} {'低于' if close < float(buy_trough) else '未低于'}"})
        count_leg = after["no_high_days"] >= confirmation_days
        price_leg = close < float(after["peak"])
        checks.append({
            "label": "普通卖出条件",
            "met": bool(count_leg and price_leg),
            "detail": f"计数腿 {after['no_high_days']} ≥ {confirmation_days}：{'成立' if count_leg else '不成立'}；价格腿 收盘 {close} 低于峰值 {after['peak']}：{'成立' if price_leg else '不成立'}",
        })
    return checks

def compose_note(checks: list[dict[str, Any]], signal: str | None) -> str:
    def state_text(met: Any) -> str:
        return "成立" if met is True else ("不成立" if met is False else "不适用")
    parts = [f"{check['label']}{state_text(check['met'])}（{check['detail']}）" for check in checks]
    return "；".join(parts) + f"；signal = {signal if signal is not None else 'null'}。"

def calculate_signal(target_date: str, parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    api_date, directory_date = normalize_date(target_date)
    instrument = parameters["instrument"]["instrument"]
    timing = parameters["timing"]
    runtime = parameters["runtime"]

    prior_state, prior_logical, prior_info = state_lookup(directory_date)
    pro = get_client()
    lookback_days = int(runtime["history_lookback_calendar_days"])
    start_date = (datetime.strptime(api_date, "%Y%m%d").date() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    rows = fetch_daily(pro, instrument["ts_code"], start_date, api_date)

    state = dict(prior_state)
    before_target = dict(state)
    emitted_signal: str | None = None
    for row in rows:
        trade_date = row["trade_date"]
        if state["last_processed_trade_date"] and trade_date <= state["last_processed_trade_date"]:
            continue
        if trade_date == api_date:
            before_target = dict(state)
        signal = advance_state(state, trade_date, row["close"], timing)
        if signal is not None and trade_date == api_date:
            emitted_signal = signal

    if state["last_processed_trade_date"] != api_date:
        raise ValueError("目标日期没有推进理论策略状态")
    if emitted_signal is None and state["last_signal_trade_date"] == api_date:
        emitted_signal = state["last_signal"]

    target_row = rows[-1]
    previous_row = rows[-2] if len(rows) > 1 else None
    close = float(target_row["close"])
    pre_close = target_row["pre_close"]
    volume = target_row["vol"]
    previous_volume = previous_row["vol"] if previous_row else None
    daily_change = (close / pre_close - 1) if pre_close else None
    volume_change = (volume / previous_volume - 1) if volume and previous_volume else None
    checks = build_checks(before_target, state, close, timing)

    strategy_state = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "strategy_state",
        "source_state": prior_logical,
        "source_state_detail": prior_info,
        "state": state,
    }
    signal_facts = {
        "instrument": instrument,
        "market": {
            "trade_date": api_date,
            "close": close,
            "pre_close": pre_close,
            "daily_change_ratio": round(daily_change, 8) if daily_change is not None else None,
            "volume": volume,
            "volume_change_ratio": round(volume_change, 8) if volume_change is not None else None,
            "source_data_start_date": rows[0]["trade_date"],
        },
        "strategy_position": state["strategy_position"],
        "position_before": before_target["strategy_position"],
        "signal": emitted_signal,
        "next_trading_action": action_tomorrow(emitted_signal, state["strategy_position"]),
        "state_anchors": {
            "peak": state["peak"] if state["peak"] else None,
            "trough": state["trough"],
            "buy_trough": state["buy_trough"],
            "last_sell_peak": state["last_sell_peak"],
        },
        "checks": checks,
        "parameters": {
            "confirmation_days": timing["confirmation_days"],
            "stop_loss_enabled": timing["stop_loss_enabled"],
            "chase_enabled": timing["chase_enabled"],
            "order_amount": timing["order_amount"],
            "execution_timing": timing["execution_timing"],
        },
        "state_source_path": prior_logical,
        "note": compose_note(checks, emitted_signal),
    }
    return {
        "strategy_state": artifact("strategy_state", directory_date, parameters, strategy_state),
        "signal_facts": artifact("signal_facts", directory_date, parameters, signal_facts),
    }

def replay_check(target_date: str, parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """从锚日重放收盘价序列并与存储状态比对（只读，不写产物）。"""
    api_date, directory_date = normalize_date(target_date)
    instrument = parameters["instrument"]["instrument"]
    timing = parameters["timing"]
    runtime = parameters["runtime"]
    anchor_api, _ = normalize_date(str(runtime["state_anchor_date"]))
    if anchor_api > api_date:
        raise ValueError(f"锚日 {anchor_api} 晚于目标日期 {api_date}")

    pro = get_client()
    rows = fetch_daily(pro, instrument["ts_code"], anchor_api, api_date)
    replayed = initial_state()
    signals: list[dict[str, Any]] = []
    for row in rows:
        signal = advance_state(replayed, row["trade_date"], row["close"], timing)
        if signal is not None:
            signals.append({"trade_date": row["trade_date"], "signal": signal, "close": row["close"]})

    stored_path = process_dir(directory_date) / str(runtime["strategy_state_file"])
    if stored_path.is_file():
        reference = read_json(stored_path)["state"]
        reference_source = str(stored_path)
    else:
        prior_state, prior_logical, _ = state_lookup(directory_date)
        reference = dict(prior_state)
        for row in rows:
            if reference["last_processed_trade_date"] and row["trade_date"] <= reference["last_processed_trade_date"]:
                continue
            advance_state(reference, row["trade_date"], row["close"], timing)
        reference_source = f"由最近先前状态（{prior_logical}）推进至 {api_date}"

    diff = [key for key in sorted(set(replayed) | set(reference)) if replayed.get(key) != reference.get(key)]
    return {
        "ok": True,
        "artifact": "replay_check",
        "system_id": SYSTEM_ID,
        "date": directory_date,
        "anchor_date": anchor_api,
        "bars": len(rows),
        "signals_replayed": signals,
        "state_replayed": replayed,
        "state_reference": reference,
        "reference_source": reference_source,
        "matched": not diff,
        "diff_fields": diff,
    }
