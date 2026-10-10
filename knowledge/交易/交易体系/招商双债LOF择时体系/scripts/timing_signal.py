#!/opt/hermes/.venv/bin/python3
"""计算招商双债 LOF 的收盘信号与理论策略状态。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import tushare as ts

from runtime_support import (
    SYSTEM_ID,
    latest_prior_strategy_state,
    load_parameters,
    normalize_date,
    process_dir,
    read_json,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="招商双债 LOF 收盘信号计算")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def tushare_client() -> Any:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def initial_state() -> dict[str, Any]:
    return {
        "strategy_position": "flat",
        "peak": 0.0,
        "trough": None,
        "no_high_days": 0,
        "no_low_days": 0,
        "buy_trough": None,
        "last_sell_peak": None,
        "last_processed_trade_date": None,
        "last_signal": None,
        "last_signal_trade_date": None,
    }


def load_prior_state(target_date: str) -> tuple[dict[str, Any], str | None]:
    path = latest_prior_strategy_state(target_date)
    if path is None:
        return initial_state(), None
    document = read_json(path)
    state = document.get("state")
    if not isinstance(state, dict):
        raise ValueError(f"策略状态缺少 state 对象: {path}")
    return {**initial_state(), **state}, str(path)


def fetch_daily(pro: Any, ts_code: str, target_api_date: str, start_api_date: str) -> pd.DataFrame:
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=start_api_date,
        end_date=target_api_date,
        fields="ts_code,trade_date,close",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情")
    result = frame.sort_values("trade_date").reset_index(drop=True)
    result["trade_date"] = result["trade_date"].astype(str)
    result["close"] = result["close"].astype(float)
    if str(result.iloc[-1]["trade_date"]) != target_api_date:
        raise ValueError(f"目标日期不是有效行情日: {target_api_date}")
    return result


def start_date_for_fetch(target_api_date: str, prior_state: dict[str, Any], lookback_days: int) -> str:
    target = datetime.strptime(target_api_date, "%Y%m%d").date()
    fallback = target - timedelta(days=lookback_days)
    prior = prior_state.get("last_processed_trade_date")
    if not isinstance(prior, str) or not prior:
        return fallback.strftime("%Y%m%d")
    try:
        prior_date = datetime.strptime(prior, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"策略状态 last_processed_trade_date 无效: {prior}") from exc
    return min(prior_date + timedelta(days=1), target).strftime("%Y%m%d")


def advance_state(state: dict[str, Any], trade_date: str, close: float, timing: dict[str, Any]) -> str | None:
    position = state["strategy_position"]
    confirmation_days = int(timing["confirmation_days"])
    signal: str | None = None

    if position == "flat" and timing["chase_enabled"] and state["last_sell_peak"] is not None and close > float(state["last_sell_peak"]):
        state.update({
            "strategy_position": "hold",
            "peak": close,
            "no_high_days": 0,
            "no_low_days": 0,
            "buy_trough": state["trough"] if state["trough"] is not None else close,
            "last_sell_peak": None,
        })
        signal = "chase_buy"
    elif position == "hold":
        if close > float(state["peak"]):
            state["peak"] = close
            state["no_high_days"] = 0
        else:
            state["no_high_days"] += 1

        if timing["stop_loss_enabled"] and state["buy_trough"] is not None and close < float(state["buy_trough"]):
            state.update({
                "strategy_position": "flat",
                "trough": close,
                "no_low_days": 0,
                "no_high_days": 0,
                "last_sell_peak": state["peak"],
                "buy_trough": None,
            })
            signal = "stop_loss_sell"
        elif state["no_high_days"] >= confirmation_days and close < float(state["peak"]):
            state.update({
                "strategy_position": "flat",
                "trough": close,
                "no_low_days": 0,
                "no_high_days": 0,
                "last_sell_peak": state["peak"],
                "buy_trough": None,
            })
            signal = "sell"
    else:
        trough = state["trough"]
        if trough is None or close < float(trough):
            state["trough"] = close
            state["no_low_days"] = 0
        else:
            state["no_low_days"] += 1

        if state["no_low_days"] >= confirmation_days and close > float(state["trough"]):
            state.update({
                "strategy_position": "hold",
                "peak": close,
                "no_high_days": 0,
                "no_low_days": 0,
                "buy_trough": state["trough"],
                "last_sell_peak": None,
            })
            signal = "buy"

    state["last_processed_trade_date"] = trade_date
    if signal is not None:
        state["last_signal"] = signal
        state["last_signal_trade_date"] = trade_date
    return signal


def action_tomorrow(signal: str | None, strategy_position: str) -> str:
    actions = {
        "buy": "buy",
        "sell": "sell_all",
        "stop_loss_sell": "sell_all",
        "chase_buy": "buy",
    }
    return actions.get(signal, "hold" if strategy_position == "hold" else "no_action")


def main() -> None:
    args = parse_args()
    target_api_date, target_date = normalize_date(args.date)
    parameters = load_parameters()
    instrument = parameters["instrument"]["instrument"]
    timing = parameters["timing"]
    runtime = parameters["runtime"]
    prior_state, prior_state_source = load_prior_state(target_date)
    pro = tushare_client()
    frame = fetch_daily(
        pro,
        instrument["ts_code"],
        target_api_date,
        start_date_for_fetch(target_api_date, prior_state, int(runtime["history_lookback_calendar_days"])),
    )

    state = dict(prior_state)
    emitted_signal: str | None = None
    for row in frame.to_dict("records"):
        trade_date = str(row["trade_date"])
        if state["last_processed_trade_date"] and trade_date <= state["last_processed_trade_date"]:
            continue
        signal = advance_state(state, trade_date, float(row["close"]), timing)
        if signal is not None and trade_date == target_api_date:
            emitted_signal = signal

    if state["last_processed_trade_date"] != target_api_date:
        raise ValueError("目标日期没有推进理论策略状态")
    if emitted_signal is None and state["last_signal_trade_date"] == target_api_date:
        emitted_signal = state["last_signal"]

    latest_close = float(frame.iloc[-1]["close"])
    strategy_state = {
        "date": target_date,
        "system_id": SYSTEM_ID,
        "artifact": "strategy_state",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_state": prior_state_source,
        "state": state,
    }
    signal_facts = {
        "date": target_date,
        "system_id": SYSTEM_ID,
        "artifact": "signal_facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instrument": instrument,
        "market": {
            "trade_date": target_api_date,
            "close": latest_close,
            "source_data_start_date": str(frame.iloc[0]["trade_date"]),
        },
        "strategy_position": state["strategy_position"],
        "signal": emitted_signal,
        "next_trading_action": action_tomorrow(emitted_signal, state["strategy_position"]),
        "state_anchors": {
            "peak": state["peak"] if state["peak"] else None,
            "trough": state["trough"],
            "buy_trough": state["buy_trough"],
            "last_sell_peak": state["last_sell_peak"],
        },
        "parameters": {
            "confirmation_days": timing["confirmation_days"],
            "stop_loss_enabled": timing["stop_loss_enabled"],
            "chase_enabled": timing["chase_enabled"],
            "order_amount": timing["order_amount"],
            "execution_timing": timing["execution_timing"],
        },
    }

    if args.dry_run:
        print(json.dumps({"strategy_state": strategy_state, "signal_facts": signal_facts}, ensure_ascii=False, indent=2))
        return
    output_dir = process_dir(target_date)
    write_json(output_dir / runtime["strategy_state_file"], strategy_state)
    write_json(output_dir / runtime["signal_facts_file"], signal_facts)
    print(json.dumps({"strategy_state": str(output_dir / runtime["strategy_state_file"]), "signal_facts": str(output_dir / runtime["signal_facts_file"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()