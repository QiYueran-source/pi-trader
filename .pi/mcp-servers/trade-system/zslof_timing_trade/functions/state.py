"""理论状态：初始状态、最近先前过程日读取（knowledge 优先、archive 兜底）与逐日推进。"""

from __future__ import annotations

from typing import Any

from functions.paths import PARAMS_ROOT, SYSTEM_NAME, logical_process_root, process_roots, read_json

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

def state_lookup(target_directory_date: str) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    """读取最近先前过程日的理论状态：knowledge 优先、archive 兜底。"""
    state_file = str(read_json(PARAMS_ROOT / "runtime.json")["strategy_state_file"])
    root_relative = logical_process_root()
    for root, location in process_roots():
        if not root.is_dir():
            continue
        dates = sorted(
            (item.name for item in root.iterdir() if item.is_dir() and item.name < target_directory_date),
            reverse=True,
        )
        for directory_date in dates:
            candidate = root / directory_date / SYSTEM_NAME / state_file
            if not candidate.is_file():
                continue
            document = read_json(candidate)
            state = document.get("state")
            if not isinstance(state, dict):
                raise ValueError(f"策略状态缺少 state 对象：{candidate}")
            logical = f"{root_relative}/{directory_date}/{SYSTEM_NAME}/{state_file}"
            info = {"location": location, "directory_date": directory_date, "physical_path": str(candidate)}
            return {**initial_state(), **state}, logical, info
    return initial_state(), None, {"location": None, "directory_date": None, "physical_path": None}

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
