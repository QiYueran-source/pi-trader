"""建仓信号、开盘段形态、审慎标签与持仓风控。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
import time

from functions.artifacts import RENDER_TARGETS, RENDER_TARGETS, artifact
from functions.market import daily_window_start, fetch_daily_market, fetch_trade_days, get_client
from functions.parameters import fail, require_string
from functions.paths import RISK_SLEEP_SECONDS, latest_snapshot, load_process_document, logical_process_path, normalize_date, process_dir, read_json, resolve_process_file, write_json
from functions.selection import build_signal, moving_average

def signalize(
    daily_by_code: dict[str, Any],
    candidates: list[dict[str, Any]],
    target_api_date: str,
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for candidate in candidates:
        records = daily_by_code.get(candidate["code"])
        if records is None:
            continue
        records = records.loc[records["trade_date"] <= target_api_date]
        signal = build_signal(candidate, records, entry)
        if signal:
            signals.append(signal)
    signals.sort(key=lambda item: item["volume_ratio"], reverse=True)
    return signals

def fetch_official_bars(client: Any, code: str, opening: dict[str, Any], directory_date: str) -> Any:
    return client.stk_mins(
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )

def classify_opening_signal(bars: Any, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    import pandas as pd
    if bars is None or (isinstance(bars, pd.DataFrame) and bars.empty) or "close" not in bars:
        return {"status": "unavailable", "signal": "unavailable"}
    time_column = "trade_time" if "trade_time" in bars else "trade_date"
    ordered = bars.sort_values(time_column)
    closes = [float(value) for value in ordered["close"].tolist()]
    first_open = float(ordered.iloc[0].get("open", closes[0]))
    if reference_open is not None and reference_open > 0:
        reference = float(reference_open)
    else:
        reference = first_open
    low = min(closes)
    high = max(closes)
    last_close = closes[-1]
    low_index = closes.index(low)
    high_index = closes.index(high)
    rapid_drop_pct = config["opening_signal"]["rapid_drop_pct"]
    if low <= reference * (1 - rapid_drop_pct):
        signal = "rapid_drop"
    elif high_index < low_index and high > reference and last_close < reference:
        signal = "weak_distribution"
    elif low_index < high_index and low < reference and last_close < reference:
        signal = "weak_rebound"
    elif high_index < low_index and low >= reference:
        signal = "strong_continuation"
    elif low_index < high_index and last_close >= reference:
        signal = "strong_recovery"
    else:
        signal = "neutral"
    return {
        "status": "ok",
        "signal": signal,
        "reference_price": round(reference, 3),
        "last_close": round(last_close, 3),
        "low": round(low, 3),
        "high": round(high, 3),
        "bars": len(closes),
    }

def fetch_opening_signal(client: Any, code: str, target_api_date: str, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    """开盘段信号：只取 official（client.stk_mins）。原 promax 兜底已于 2026-10-18 删除。"""
    opening = config["opening_signal"]
    directory_date = normalize_date(target_api_date)[1]
    errors: list[str] = []
    try:
        bars = fetch_official_bars(code, opening, directory_date)
        signal = classify_opening_signal(bars, config, reference_open)
        if signal.get("signal") != "unavailable":
            signal["source"] = "official"
            return signal
        errors.append("official: 空数据")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"official: {type(exc).__name__}: {exc}")
    return {"status": "unavailable", "signal": "unavailable", "source": "unavailable", "errors": errors}

def tag_is_active(tag: dict[str, Any] | None, target_api_date: str) -> bool:
    return bool(tag and tag.get("expire_date", "") >= target_api_date)

def tag_expire_date(target_api_date: str, trade_days: list[str], valid_days: int) -> str:
    index = trade_days.index(target_api_date)
    return trade_days[min(index + valid_days - 1, len(trade_days) - 1)]

def transition_prudent_tag(
    current_tag: dict[str, Any] | None,
    opening_signal: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    active = current_tag if tag_is_active(current_tag, target_api_date) else None
    should_refresh = config["prudent_tag"]["refresh_on_bearish_signal"] and opening_signal["signal"] in BEARISH_OPENING_SIGNALS
    if not should_refresh:
        return active
    return {
        "created_date": target_api_date,
        "expire_date": tag_expire_date(target_api_date, trade_days, config["prudent_tag"]["valid_trading_days"]),
        "signal": opening_signal["signal"],
    }

def evaluate_risk(
    buy_price: float,
    records: list[dict[str, Any]],
    prudent_tag: dict[str, Any] | None,
    prior_state: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    exits = config["exit_rules"]
    ma5_rule = exits["ma5"]
    ma10_rule = exits["ma10"]
    closes = [float(item["close"]) for item in records]
    close = closes[-1]
    ma5 = moving_average(closes, ma5_rule["period"])
    ma10 = moving_average(closes, ma10_rule["period"])
    state = dict(prior_state)
    if ma10 is not None and close < ma10:
        return {"action": "liquidate", "reason": "below_ma10", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3)}}, state
    if close <= buy_price * (1 - exits["hard_stop_loss_pct"]):
        return {"action": "liquidate", "reason": "hard_stop_loss", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}}, state
    daily = {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}
    if ma5 is None or close >= ma5:
        state.pop("ma5_below_since", None)
        return {"action": "hold", "reason": "no_risk_trigger", "daily": daily}, state
    first_below_date = state.get("ma5_below_since", target_api_date)
    state["ma5_below_since"] = first_below_date
    observed_days = len([day for day in trade_days if first_below_date <= day <= target_api_date])
    observation_days = (
        ma5_rule["prudent_observation_days"] if tag_is_active(prudent_tag, target_api_date) else ma5_rule["normal_observation_days"]
    )
    action = "reduce" if observed_days > observation_days else "observe"
    reason = "below_ma5" if action == "reduce" else "ma5_observation"
    return {"action": action, "reason": reason, "daily": daily}, state

def load_snapshot_positions(target_api_date: str, filename: str, trade_days: list[str], lookback_days: int) -> dict[str, Any]:
    found = latest_snapshot(target_api_date, filename, trade_days, lookback_days)
    if not found:
        return {}
    path, _ = found
    snapshot = read_json(path)
    positions = snapshot.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError(f"状态快照 positions 必须是对象：{path}")
    return positions

def op_entry_signal(
    target_api_date: str,
    directory_date: str,
    industries: list[str] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    source_file = "hottest_industry_candidate.json" if industries else "full_market_candidate.json"
    candidate_document = load_process_document(directory_date, source_file)
    candidates = candidate_document.get("candidates", [])
    entry = parameters["entry"]
    client = get_client()
    required_days = max(entry["volume_average_period"], entry["breakout_ma_period"])
    trade_days = fetch_trade_days(client, daily_window_start(target_api_date, required_days * 3), target_api_date)
    daily = fetch_daily_market(client, trade_days, fields="ts_code,trade_date,close,vol")
    if daily.empty:
        raise RuntimeError("未获取到建仓信号所需日线数据")
    daily_by_code = {str(code): records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    signals = signalize(daily_by_code, candidates, target_api_date, entry)
    payload = artifact(
        "entry_signal",
        directory_date,
        parameters,
        (
            f"条件＝收盘 > MA{entry['breakout_ma_period']} 且 量 ≥ {entry['volume_multiplier']}×{entry['volume_average_period']} 日均量（含当日）；"
            f"输入＝{source_file}（{len(candidates)} 只候选）。"
        ),
        {
            "source": logical_process_path(directory_date, source_file),
            "params": {key: value for key, value in entry.items() if key != "schema_version"},
            "stats": {
                "total_candidates": len(candidates),
                "with_daily_data": sum(1 for item in candidates if item["code"] in daily_by_code),
                "signals": len(signals),
            },
            "signals": signals,
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "entry_signal", "date": directory_date, "document": payload}
    path = write_json(process_dir(directory_date, create=True) / "entry_signal.json", payload)
    return {"ok": True, "artifact": "entry_signal", "date": directory_date, "path": path, "logical_path": logical_process_path(directory_date, "entry_signal.json"), "stats": payload["stats"]}

def op_risk_signal(
    target_api_date: str,
    directory_date: str,
    positions: dict[str, Any] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    config = parameters["risk"]
    if positions is None:
        path = resolve_process_file(directory_date, "positions.json")
        positions = read_json(path) if path is not None else {}
    cleaned: dict[str, float] = {}
    for code, buy_price in positions.items():
        require_string(code, "positions 代码")
        if isinstance(buy_price, bool) or not isinstance(buy_price, (int, float)) or buy_price <= 0:
            fail(f"positions.{code}", "必须为正数买入价")
        cleaned[str(code)] = float(buy_price)

    if not cleaned:
        payload = artifact(
            "risk_signal",
            directory_date,
            parameters,
            "空仓契约：无持仓时不继承旧快照，state/prudent_tags 置为空仓位结构。",
            {
                "params": {key: value for key, value in config.items() if key != "schema_version"},
                "data_sources": {},
                "stats": {"positions": 0, "evaluated": 0, "actions": 0, "hold": 0},
                "risk_actions": [],
                "holdings": [],
            },
        )
        if dry_run:
            return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
        directory = process_dir(directory_date, create=True)
        paths = [
            write_json(directory / "risk_signal.json", payload),
            write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / "positions.json", {}),
        ]
        return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "stats": payload["stats"]}

    client = get_client()
    start_date = (datetime.strptime(target_api_date, "%Y%m%d") - timedelta(days=70)).strftime("%Y%m%d")
    calendar_end = (datetime.strptime(target_api_date, "%Y%m%d") + timedelta(days=config["prudent_tag"]["valid_trading_days"] * 3)).strftime("%Y%m%d")
    trade_days = fetch_trade_days(client, start_date, calendar_end)
    daily_trade_days = [day for day in trade_days if day <= target_api_date]
    if target_api_date not in daily_trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无风控事实")
    lookback = config["prudent_tag"]["snapshot_lookback_trading_days"]
    prior_tags = load_snapshot_positions(target_api_date, config["prudent_tag"]["state_file"], trade_days, lookback)
    prior_states = load_snapshot_positions(target_api_date, config["position_state"]["state_file"], trade_days, lookback)

    stocks = client.stock_basic(ts_code=",".join(cleaned), fields="ts_code,name")
    name_by_code: dict[str, str] = {}
    if stocks is not None and not stocks.empty:
        name_by_code = {str(row["ts_code"]): str(row["name"]) for _, row in stocks.iterrows()}

    daily = fetch_daily_market(client, daily_trade_days, fields="ts_code,trade_date,open,close")
    records_by_code: dict[str, list[dict[str, Any]]] = {}
    if not daily.empty:
        filtered = daily.loc[daily["ts_code"].isin(list(cleaned))]
        records_by_code = {
            str(code): group.sort_values("trade_date").to_dict("records")
            for code, group in filtered.groupby("ts_code")
        }

    rows: list[dict[str, Any]] = []
    next_tags: dict[str, Any] = {}
    next_states: dict[str, Any] = {}
    for code, buy_price in cleaned.items():
        records = records_by_code.get(code, [])
        if not records:
            continue
        try:
            raw_open = records[-1].get("open")
            reference_open = float(raw_open) if raw_open is not None else None
            opening_signal = fetch_opening_signal(client, code, target_api_date, config, reference_open)
        except Exception as exc:  # noqa: BLE001
            opening_signal = {
                "status": "unavailable",
                "signal": "unavailable",
                "source": "unavailable",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        prudent_tag = transition_prudent_tag(prior_tags.get(code), opening_signal, target_api_date, trade_days, config)
        assessment, state = evaluate_risk(buy_price, records, prudent_tag, prior_states.get(code, {}), target_api_date, trade_days, config)
        closes = [float(item["close"]) for item in records]
        rows.append(
            {
                "code": code,
                "name": name_by_code.get(code, ""),
                "buy_price": buy_price,
                "close": round(closes[-1], 3),
                "pnl_pct": round((closes[-1] - buy_price) / buy_price * 100, 2),
                "signal_date": records[-1]["trade_date"],
                "opening": opening_signal,
                "prudent_tag": prudent_tag,
                **assessment,
            }
        )
        next_states[code] = state
        if prudent_tag:
            next_tags[code] = prudent_tag
        time.sleep(RISK_SLEEP_SECONDS)

    risk_actions = [row for row in rows if row["action"] != "hold"]
    holdings = [row for row in rows if row["action"] == "hold"]
    payload = artifact(
        "risk_signal",
        directory_date,
        parameters,
        "三层风控：开盘信号（5min 开盘段，参考价＝当日开盘）→ 审慎标签（3 交易日）→ 日线退出（MA5 跌破观察/减半、MA10 跌破清仓、硬止损 5%）。",
        {
            "params": {key: value for key, value in config.items() if key != "schema_version"},
            "data_sources": {row["code"]: row["opening"].get("source", "unknown") for row in rows},
            "stats": {
                "positions": len(cleaned),
                "evaluated": len(rows),
                "actions": len(risk_actions),
                "hold": len(holdings),
            },
            "risk_actions": risk_actions,
            "holdings": holdings,
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
    directory = process_dir(directory_date, create=True)
    paths = [
        write_json(directory / "risk_signal.json", payload),
        write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": next_tags}),
        write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": next_states}),
        write_json(directory / "positions.json", cleaned),
    ]
    return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "logical_paths": [logical_process_path(directory_date, "risk_signal.json")], "stats": payload["stats"]}

BEARISH_OPENING_SIGNALS = {"weak_distribution", "weak_rebound", "rapid_drop"}


def fetch_official_bars(client: Any, code: str, opening: dict[str, Any], directory_date: str) -> Any:
    return client.stk_mins(
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )


def classify_opening_signal(bars: Any, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    import pandas as pd
    if bars is None or (isinstance(bars, pd.DataFrame) and bars.empty) or "close" not in bars:
        return {"status": "unavailable", "signal": "unavailable"}
    time_column = "trade_time" if "trade_time" in bars else "trade_date"
    ordered = bars.sort_values(time_column)
    closes = [float(value) for value in ordered["close"].tolist()]
    first_open = float(ordered.iloc[0].get("open", closes[0]))
    if reference_open is not None and reference_open > 0:
        reference = float(reference_open)
    else:
        reference = first_open
    low = min(closes)
    high = max(closes)
    last_close = closes[-1]
    low_index = closes.index(low)
    high_index = closes.index(high)
    rapid_drop_pct = config["opening_signal"]["rapid_drop_pct"]
    if low <= reference * (1 - rapid_drop_pct):
        signal = "rapid_drop"
    elif high_index < low_index and high > reference and last_close < reference:
        signal = "weak_distribution"
    elif low_index < high_index and low < reference and last_close < reference:
        signal = "weak_rebound"
    elif high_index < low_index and low >= reference:
        signal = "strong_continuation"
    elif low_index < high_index and last_close >= reference:
        signal = "strong_recovery"
    else:
        signal = "neutral"
    return {
        "status": "ok",
        "signal": signal,
        "reference_price": round(reference, 3),
        "last_close": round(last_close, 3),
        "low": round(low, 3),
        "high": round(high, 3),
        "bars": len(closes),
    }


def fetch_opening_signal(client: Any, code: str, target_api_date: str, config: dict[str, Any], reference_open: float | None = None) -> dict[str, Any]:
    """开盘段信号：只取 official（client.stk_mins）。原 promax 兜底已于 2026-10-18 删除。"""
    opening = config["opening_signal"]
    directory_date = normalize_date(target_api_date)[1]
    errors: list[str] = []
    try:
        bars = fetch_official_bars(code, opening, directory_date)
        signal = classify_opening_signal(bars, config, reference_open)
        if signal.get("signal") != "unavailable":
            signal["source"] = "official"
            return signal
        errors.append("official: 空数据")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"official: {type(exc).__name__}: {exc}")
    return {"status": "unavailable", "signal": "unavailable", "source": "unavailable", "errors": errors}


def tag_is_active(tag: dict[str, Any] | None, target_api_date: str) -> bool:
    return bool(tag and tag.get("expire_date", "") >= target_api_date)


def tag_expire_date(target_api_date: str, trade_days: list[str], valid_days: int) -> str:
    index = trade_days.index(target_api_date)
    return trade_days[min(index + valid_days - 1, len(trade_days) - 1)]


def transition_prudent_tag(
    current_tag: dict[str, Any] | None,
    opening_signal: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    active = current_tag if tag_is_active(current_tag, target_api_date) else None
    should_refresh = config["prudent_tag"]["refresh_on_bearish_signal"] and opening_signal["signal"] in BEARISH_OPENING_SIGNALS
    if not should_refresh:
        return active
    return {
        "created_date": target_api_date,
        "expire_date": tag_expire_date(target_api_date, trade_days, config["prudent_tag"]["valid_trading_days"]),
        "signal": opening_signal["signal"],
    }


def evaluate_risk(
    buy_price: float,
    records: list[dict[str, Any]],
    prudent_tag: dict[str, Any] | None,
    prior_state: dict[str, Any],
    target_api_date: str,
    trade_days: list[str],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    exits = config["exit_rules"]
    ma5_rule = exits["ma5"]
    ma10_rule = exits["ma10"]
    closes = [float(item["close"]) for item in records]
    close = closes[-1]
    ma5 = moving_average(closes, ma5_rule["period"])
    ma10 = moving_average(closes, ma10_rule["period"])
    state = dict(prior_state)
    if ma10 is not None and close < ma10:
        return {"action": "liquidate", "reason": "below_ma10", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3)}}, state
    if close <= buy_price * (1 - exits["hard_stop_loss_pct"]):
        return {"action": "liquidate", "reason": "hard_stop_loss", "daily": {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}}, state
    daily = {"ma5": round(ma5, 3) if ma5 is not None else None, "ma10": round(ma10, 3) if ma10 is not None else None}
    if ma5 is None or close >= ma5:
        state.pop("ma5_below_since", None)
        return {"action": "hold", "reason": "no_risk_trigger", "daily": daily}, state
    first_below_date = state.get("ma5_below_since", target_api_date)
    state["ma5_below_since"] = first_below_date
    observed_days = len([day for day in trade_days if first_below_date <= day <= target_api_date])
    observation_days = (
        ma5_rule["prudent_observation_days"] if tag_is_active(prudent_tag, target_api_date) else ma5_rule["normal_observation_days"]
    )
    action = "reduce" if observed_days > observation_days else "observe"
    reason = "below_ma5" if action == "reduce" else "ma5_observation"
    return {"action": action, "reason": reason, "daily": daily}, state


def load_snapshot_positions(target_api_date: str, filename: str, trade_days: list[str], lookback_days: int) -> dict[str, Any]:
    found = latest_snapshot(target_api_date, filename, trade_days, lookback_days)
    if not found:
        return {}
    path, _ = found
    snapshot = read_json(path)
    positions = snapshot.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError(f"状态快照 positions 必须是对象：{path}")
    return positions


def op_risk_signal(
    target_api_date: str,
    directory_date: str,
    positions: dict[str, Any] | None,
    parameters: dict[str, dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    config = parameters["risk"]
    if positions is None:
        path = resolve_process_file(directory_date, "positions.json")
        positions = read_json(path) if path is not None else {}
    cleaned: dict[str, float] = {}
    for code, buy_price in positions.items():
        require_string(code, "positions 代码")
        if isinstance(buy_price, bool) or not isinstance(buy_price, (int, float)) or buy_price <= 0:
            fail(f"positions.{code}", "必须为正数买入价")
        cleaned[str(code)] = float(buy_price)

    if not cleaned:
        payload = artifact(
            "risk_signal",
            directory_date,
            parameters,
            "空仓契约：无持仓时不继承旧快照，state/prudent_tags 置为空仓位结构。",
            {
                "params": {key: value for key, value in config.items() if key != "schema_version"},
                "data_sources": {},
                "stats": {"positions": 0, "evaluated": 0, "actions": 0, "hold": 0},
                "risk_actions": [],
                "holdings": [],
            },
        )
        if dry_run:
            return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
        directory = process_dir(directory_date, create=True)
        paths = [
            write_json(directory / "risk_signal.json", payload),
            write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": {}}),
            write_json(directory / "positions.json", {}),
        ]
        return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "stats": payload["stats"]}

    client = get_client()
    start_date = (datetime.strptime(target_api_date, "%Y%m%d") - timedelta(days=70)).strftime("%Y%m%d")
    calendar_end = (datetime.strptime(target_api_date, "%Y%m%d") + timedelta(days=config["prudent_tag"]["valid_trading_days"] * 3)).strftime("%Y%m%d")
    trade_days = fetch_trade_days(client, start_date, calendar_end)
    daily_trade_days = [day for day in trade_days if day <= target_api_date]
    if target_api_date not in daily_trade_days:
        raise ValueError(f"{directory_date} 不是交易日，无风控事实")
    lookback = config["prudent_tag"]["snapshot_lookback_trading_days"]
    prior_tags = load_snapshot_positions(target_api_date, config["prudent_tag"]["state_file"], trade_days, lookback)
    prior_states = load_snapshot_positions(target_api_date, config["position_state"]["state_file"], trade_days, lookback)

    stocks = client.stock_basic(ts_code=",".join(cleaned), fields="ts_code,name")
    name_by_code: dict[str, str] = {}
    if stocks is not None and not stocks.empty:
        name_by_code = {str(row["ts_code"]): str(row["name"]) for _, row in stocks.iterrows()}

    daily = fetch_daily_market(client, daily_trade_days, fields="ts_code,trade_date,open,close")
    records_by_code: dict[str, list[dict[str, Any]]] = {}
    if not daily.empty:
        filtered = daily.loc[daily["ts_code"].isin(list(cleaned))]
        records_by_code = {
            str(code): group.sort_values("trade_date").to_dict("records")
            for code, group in filtered.groupby("ts_code")
        }

    rows: list[dict[str, Any]] = []
    next_tags: dict[str, Any] = {}
    next_states: dict[str, Any] = {}
    for code, buy_price in cleaned.items():
        records = records_by_code.get(code, [])
        if not records:
            continue
        try:
            raw_open = records[-1].get("open")
            reference_open = float(raw_open) if raw_open is not None else None
            opening_signal = fetch_opening_signal(client, code, target_api_date, config, reference_open)
        except Exception as exc:  # noqa: BLE001
            opening_signal = {
                "status": "unavailable",
                "signal": "unavailable",
                "source": "unavailable",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        prudent_tag = transition_prudent_tag(prior_tags.get(code), opening_signal, target_api_date, trade_days, config)
        assessment, state = evaluate_risk(buy_price, records, prudent_tag, prior_states.get(code, {}), target_api_date, trade_days, config)
        closes = [float(item["close"]) for item in records]
        rows.append(
            {
                "code": code,
                "name": name_by_code.get(code, ""),
                "buy_price": buy_price,
                "close": round(closes[-1], 3),
                "pnl_pct": round((closes[-1] - buy_price) / buy_price * 100, 2),
                "signal_date": records[-1]["trade_date"],
                "opening": opening_signal,
                "prudent_tag": prudent_tag,
                **assessment,
            }
        )
        next_states[code] = state
        if prudent_tag:
            next_tags[code] = prudent_tag
        time.sleep(RISK_SLEEP_SECONDS)

    risk_actions = [row for row in rows if row["action"] != "hold"]
    holdings = [row for row in rows if row["action"] == "hold"]
    payload = artifact(
        "risk_signal",
        directory_date,
        parameters,
        "三层风控：开盘信号（5min 开盘段，参考价＝当日开盘）→ 审慎标签（3 交易日）→ 日线退出（MA5 跌破观察/减半、MA10 跌破清仓、硬止损 5%）。",
        {
            "params": {key: value for key, value in config.items() if key != "schema_version"},
            "data_sources": {row["code"]: row["opening"].get("source", "unknown") for row in rows},
            "stats": {
                "positions": len(cleaned),
                "evaluated": len(rows),
                "actions": len(risk_actions),
                "hold": len(holdings),
            },
            "risk_actions": risk_actions,
            "holdings": holdings,
        },
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "risk_signal", "date": directory_date, "document": payload}
    directory = process_dir(directory_date, create=True)
    paths = [
        write_json(directory / "risk_signal.json", payload),
        write_json(directory / config["prudent_tag"]["state_file"], {"date": target_api_date, "positions": next_tags}),
        write_json(directory / config["position_state"]["state_file"], {"date": target_api_date, "positions": next_states}),
        write_json(directory / "positions.json", cleaned),
    ]
    return {"ok": True, "artifact": "risk_signal", "date": directory_date, "paths": paths, "logical_paths": [logical_process_path(directory_date, "risk_signal.json")], "stats": payload["stats"]}


RENDER_TARGETS = {
    "candidates": ("full_market_candidate.json", "candidates.md.j2", "candidates.md"),
    "sector_heat": ("sector_heat.json", "sector_heat.md.j2", "sector_heat.md"),
    "entry_signal": ("entry_signal.json", "entry_signal.md.j2", "entry_signal.md"),
    "risk_signal": ("risk_signal.json", "risk_signal.md.j2", "risk_signal.md"),
}
