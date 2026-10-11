#!/usr/bin/env python3
"""评估持仓的开盘信号、审慎标签与日线退出风险。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts

from runtime_support import latest_snapshot, load_risk_config, normalize_date, process_dir

BEARISH_OPENING_SIGNALS = {"weak_distribution", "weak_rebound", "rapid_drop"}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON 文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 文件无效 {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象: {path}")
    return value


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_positions(path: Path) -> dict[str, float]:
    raw_positions = load_json(path)
    positions = {}
    for code, buy_price in raw_positions.items():
        if not isinstance(code, str) or not code:
            raise ValueError("持仓代码必须是非空字符串")
        if isinstance(buy_price, bool) or not isinstance(buy_price, (int, float)) or buy_price <= 0:
            raise ValueError(f"positions.{code}: 必须为正数买入价")
        positions[code] = float(buy_price)
    return positions


def create_client():
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def get_trade_days(client, start_date: str, end_date: str) -> list[str]:
    calendar = client.trade_cal(
        exchange="SSE",
        start_date=start_date,
        end_date=end_date,
        fields="cal_date,is_open",
    )
    if calendar is None or calendar.empty:
        return []
    return sorted(calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist())


def fetch_daily_records(client, codes: list[str], trade_days: list[str]) -> dict[str, list[dict]]:
    frames = []
    for index, trade_date in enumerate(trade_days):
        if index == 0 or (index + 1) % 5 == 0:
            log(f"拉取日线 {index + 1}/{len(trade_days)}: {trade_date}")
        daily = client.daily(trade_date=trade_date, fields="ts_code,trade_date,open,close")
        if daily is not None and not daily.empty:
            frames.append(daily.loc[daily["ts_code"].isin(codes)])
        time.sleep(0.3)
    if not frames:
        return {}

    records = pd.concat(frames, ignore_index=True)
    records["open"] = records["open"].astype(float)
    records["close"] = records["close"].astype(float)
    records["trade_date"] = records["trade_date"].astype(str)
    return {
        code: group.sort_values("trade_date").to_dict("records")
        for code, group in records.groupby("ts_code")
    }


def fetch_names(client, codes: list[str]) -> dict[str, str]:
    stocks = client.stock_basic(ts_code=",".join(codes), fields="ts_code,name")
    if stocks is None or stocks.empty:
        return {}
    return {str(row["ts_code"]): str(row["name"]) for _, row in stocks.iterrows()}


def moving_average(records: list[dict], period: int) -> float | None:
    if len(records) < period:
        return None
    return round(sum(float(item["close"]) for item in records[-period:]) / period, 3)


def classify_opening_signal(bars: pd.DataFrame, config: dict, reference_open: float | None = None) -> dict:
    if bars is None or bars.empty or "close" not in bars:
        return {"status": "unavailable", "signal": "unavailable"}

    time_column = "trade_time" if "trade_time" in bars else "trade_date"
    ordered_bars = bars.sort_values(time_column)
    closes = ordered_bars["close"].astype(float).tolist()
    first_open = float(ordered_bars.iloc[0].get("open", closes[0]))
    if reference_open is not None and reference_open > 0:
        reference = float(reference_open)
        if abs(first_open - reference) > max(0.01, reference * 0.005):
            log(f"开盘价口径偏差: 日线 open={reference} vs 分钟首根 open={first_open}")
    else:
        log("缺少日线 open，回退分钟首根 open 作为参考价")
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


TUSHARE_PROXY_SCRIPTS = Path(
    os.environ.get(
        "TUSHARE_PROXY_SCRIPTS",
        "/pi-trader/.pi/skills/source/tushare/tushare-proxy/scripts",
    )
)


def fetch_official_bars(client, code: str, opening: dict, directory_date: str):
    return client.stk_mins(
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )


def fetch_proxy_bars(code: str, opening: dict, directory_date: str) -> pd.DataFrame:
    """tushare-proxy promax 兜底；必须校验 trade_time 日期（代理有返回陈旧数据的前科）。"""
    if not TUSHARE_PROXY_SCRIPTS.is_dir():
        raise RuntimeError(f"tushare-proxy 技能目录不存在: {TUSHARE_PROXY_SCRIPTS}")
    if str(TUSHARE_PROXY_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(TUSHARE_PROXY_SCRIPTS))
    import ts_proxy  # 延迟导入：仅在需要兜底时加载

    frame = ts_proxy.get(
        "stk_mins",
        ts_code=code,
        freq=opening["bar_frequency"],
        start_date=f"{directory_date} {opening['start_time']}:00",
        end_date=f"{directory_date} {opening['end_time']}:00",
    )
    if frame is None or frame.empty:
        raise RuntimeError("promax 返回空数据")
    dates = {str(value)[:10] for value in frame["trade_time"]}
    if dates != {directory_date}:
        raise RuntimeError(f"promax 返回日期不符: {sorted(dates)} != {directory_date}")
    return frame


def fetch_opening_signal(
    client, code: str, target_date: str, config: dict, reference_open: float | None = None
) -> dict:
    """按 params 的 fallback_sources 顺序取开盘段；全部失败返回 unavailable，不抛异常。"""
    opening = config["opening_signal"]
    directory_date = datetime.strptime(target_date, "%Y%m%d").strftime("%Y-%m-%d")
    errors: list[str] = []
    for source in opening["fallback_sources"]:
        try:
            if source == "official":
                bars = fetch_official_bars(client, code, opening, directory_date)
            elif source == "promax":
                bars = fetch_proxy_bars(code, opening, directory_date)
            else:
                raise ValueError(f"未知数据源: {source}")
            signal = classify_opening_signal(bars, config, reference_open)
            if signal.get("signal") == "unavailable":
                errors.append(f"{source}: 空数据")
                log(f"开盘段 {source} 返回空({code})，继续降级")
                continue
            signal["source"] = source
            return signal
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
            log(f"开盘段数据源 {source} 失败({code}): {exc}")
    log(f"开盘段数据源全部失败({code}): {'; '.join(errors)}")
    return {
        "status": "unavailable",
        "signal": "unavailable",
        "source": "unavailable",
        "errors": errors,
    }


def load_snapshot_positions(
    target_date: str,
    filename: str,
    trade_days: list[str],
    lookback_days: int,
) -> dict:
    found = latest_snapshot(target_date, filename, trade_days, lookback_days)
    if not found:
        return {}
    path, _ = found
    snapshot = load_json(path)
    positions = snapshot.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError(f"状态快照 positions 必须是对象: {path}")
    return positions


def tag_is_active(tag: dict | None, target_date: str) -> bool:
    return bool(tag and tag.get("expire_date", "") >= target_date)


def expire_date(target_date: str, trade_days: list[str], valid_days: int) -> str:
    current_index = trade_days.index(target_date)
    expiry_index = min(current_index + valid_days - 1, len(trade_days) - 1)
    return trade_days[expiry_index]


def transition_prudent_tag(
    current_tag: dict | None,
    opening_signal: dict,
    target_date: str,
    trade_days: list[str],
    config: dict,
) -> dict | None:
    active_tag = current_tag if tag_is_active(current_tag, target_date) else None
    signal = opening_signal["signal"]
    should_refresh = config["prudent_tag"]["refresh_on_bearish_signal"] and signal in BEARISH_OPENING_SIGNALS
    if not should_refresh:
        return active_tag

    return {
        "created_date": target_date,
        "expire_date": expire_date(
            target_date,
            trade_days,
            config["prudent_tag"]["valid_trading_days"],
        ),
        "signal": signal,
    }


def evaluate_risk(
    buy_price: float,
    records: list[dict],
    prudent_tag: dict | None,
    prior_state: dict,
    target_date: str,
    trade_days: list[str],
    config: dict,
) -> tuple[dict, dict]:
    exit_rules = config["exit_rules"]
    ma5_rule = exit_rules["ma5"]
    ma10_rule = exit_rules["ma10"]
    close = float(records[-1]["close"])
    ma5 = moving_average(records, ma5_rule["period"])
    ma10 = moving_average(records, ma10_rule["period"])
    state = dict(prior_state)

    if ma10 is not None and close < ma10:
        return (
            {
                "action": "liquidate",
                "reason": "below_ma10",
                "daily": {"ma5": ma5, "ma10": ma10},
            },
            state,
        )
    if close <= buy_price * (1 - exit_rules["hard_stop_loss_pct"]):
        return (
            {
                "action": "liquidate",
                "reason": "hard_stop_loss",
                "daily": {"ma5": ma5, "ma10": ma10},
            },
            state,
        )
    if ma5 is None or close >= ma5:
        state.pop("ma5_below_since", None)
        return (
            {
                "action": "hold",
                "reason": "no_risk_trigger",
                "daily": {"ma5": ma5, "ma10": ma10},
            },
            state,
        )

    first_below_date = state.get("ma5_below_since", target_date)
    state["ma5_below_since"] = first_below_date
    observed_days = len([day for day in trade_days if first_below_date <= day <= target_date])
    observation_days = (
        ma5_rule["prudent_observation_days"]
        if tag_is_active(prudent_tag, target_date)
        else ma5_rule["normal_observation_days"]
    )
    action = "reduce" if observed_days > observation_days else "observe"
    reason = "below_ma5" if action == "reduce" else "ma5_observation"
    return (
        {
            "action": action,
            "reason": reason,
            "daily": {"ma5": ma5, "ma10": ma10},
        },
        state,
    )


def build_risk_row(
    code: str,
    name: str,
    buy_price: float,
    records: list[dict],
    opening_signal: dict,
    prudent_tag: dict | None,
    assessment: dict,
) -> dict:
    close = float(records[-1]["close"])
    return {
        "code": code,
        "name": name,
        "buy_price": buy_price,
        "close": round(close, 3),
        "pnl_pct": round((close - buy_price) / buy_price * 100, 2),
        "signal_date": records[-1]["trade_date"],
        "opening": opening_signal,
        "prudent_tag": prudent_tag,
        **assessment,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="热门板块回调低吸 · 持仓风控")
    parser.add_argument("--date", help="目标日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--positions", required=True, help="持仓 JSON：{代码: 买入价}")
    parser.add_argument("--output", help="输出文件名，默认 risk_signal.json")
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON，不写入过程资料")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_risk_config()
    target_date, _ = normalize_date(args.date)
    positions = load_positions(Path(args.positions))
    if not positions:
        output = {
            "date": target_date,
            "params": config,
            "data_sources": {},
            "stats": {"positions": 0, "evaluated": 0, "actions": 0, "hold": 0},
            "risk_actions": [],
            "holdings": [],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    client = create_client()
    start_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=70)).strftime("%Y%m%d")
    calendar_end_date = (
        datetime.strptime(target_date, "%Y%m%d")
        + timedelta(days=config["prudent_tag"]["valid_trading_days"] * 3)
    ).strftime("%Y%m%d")
    trade_days = get_trade_days(client, start_date, calendar_end_date)
    daily_trade_days = [day for day in trade_days if day <= target_date]
    if target_date not in daily_trade_days:
        raise RuntimeError(f"{target_date} 不是交易日")

    lookback_days = config["prudent_tag"]["snapshot_lookback_trading_days"]
    tags = load_snapshot_positions(target_date, config["prudent_tag"]["state_file"], trade_days, lookback_days)
    states = load_snapshot_positions(target_date, config["position_state"]["state_file"], trade_days, lookback_days)
    codes = list(positions)
    names = fetch_names(client, codes)
    records_by_code = fetch_daily_records(client, codes, daily_trade_days)

    rows = []
    next_tags = {}
    next_states = {}
    for code, buy_price in positions.items():
        records = records_by_code.get(code, [])
        if not records:
            log(f"跳过 {code}: 无日线数据")
            continue

        try:
            raw_open = records[-1].get("open")
            reference_open = float(raw_open) if raw_open is not None else None
            opening_signal = fetch_opening_signal(client, code, target_date, config, reference_open)
        except Exception as exc:  # noqa: BLE001
            log(f"开盘信号获取异常({code})，按 unavailable 处理: {exc}")
            opening_signal = {
                "status": "unavailable",
                "signal": "unavailable",
                "source": "unavailable",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        prudent_tag = transition_prudent_tag(tags.get(code), opening_signal, target_date, trade_days, config)
        assessment, state = evaluate_risk(
            buy_price,
            records,
            prudent_tag,
            states.get(code, {}),
            target_date,
            trade_days,
            config,
        )
        rows.append(build_risk_row(code, names.get(code, ""), buy_price, records, opening_signal, prudent_tag, assessment))
        next_states[code] = state
        if prudent_tag:
            next_tags[code] = prudent_tag
        time.sleep(5)

    risk_actions = [row for row in rows if row["action"] != "hold"]
    holdings = [row for row in rows if row["action"] == "hold"]
    output = {
        "date": target_date,
        "params": config,
        "data_sources": {row["code"]: row["opening"].get("source", "unknown") for row in rows},
        "stats": {
            "positions": len(positions),
            "evaluated": len(rows),
            "actions": len(risk_actions),
            "hold": len(holdings),
        },
        "risk_actions": risk_actions,
        "holdings": holdings,
    }
    if not args.dry_run:
        output_directory = process_dir(target_date)
        save_json(output_directory / (args.output or "risk_signal.json"), output)
        save_json(output_directory / config["prudent_tag"]["state_file"], {"date": target_date, "positions": next_tags})
        save_json(output_directory / config["position_state"]["state_file"], {"date": target_date, "positions": next_states})
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()