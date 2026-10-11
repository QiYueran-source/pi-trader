#!/usr/bin/env python3
"""基于候选股、均线突破和放量条件生成建仓信号。"""

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

from runtime_support import load_entry_config, normalize_date, process_dir


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_client():
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def fetch_daily(client, target_date: str, days_back: int) -> pd.DataFrame:
    start_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=days_back)).strftime("%Y%m%d")
    calendar = client.trade_cal(
        exchange="SSE",
        start_date=start_date,
        end_date=target_date,
        fields="cal_date,is_open",
    )
    trade_days = calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist()
    frames = []
    for index, trade_date in enumerate(trade_days):
        if index == 0 or (index + 1) % 5 == 0:
            log(f"拉取日线 {index + 1}/{len(trade_days)}: {trade_date}")
        daily = client.daily(trade_date=trade_date, fields="ts_code,trade_date,close,vol")
        if daily is not None and not daily.empty:
            frames.append(daily)
        time.sleep(0.3)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str)
    result["close"] = result["close"].astype(float)
    result["vol"] = result["vol"].astype(float)
    return result


def moving_average(values: list[float], period: int) -> float:
    return sum(values[-period:]) / period


def build_signal(candidate: dict, records: pd.DataFrame, config: dict) -> dict | None:
    required_days = max(config["volume_average_period"], config["breakout_ma_period"])
    if len(records) < required_days:
        return None

    closes = records["close"].tolist()
    volumes = records["vol"].tolist()
    breakout_ma = moving_average(closes, config["breakout_ma_period"])
    volume_ma = moving_average(volumes, config["volume_average_period"])
    close = closes[-1]
    volume = volumes[-1]
    if close <= breakout_ma or volume <= config["volume_multiplier"] * volume_ma:
        return None

    latest = records.iloc[-1]
    return {
        "code": candidate["code"],
        "name": candidate["name"],
        "industry": candidate["industry"],
        "board_count": candidate["board_count"],
        "board_dates": candidate["board_dates"],
        "pullback_pct": candidate["pullback_pct"],
        "signal_date": str(latest["trade_date"]),
        "close": round(close, 3),
        "breakout_ma": round(breakout_ma, 3),
        "breakout_above_pct": round((close - breakout_ma) / breakout_ma * 100, 2),
        "volume": int(volume),
        "volume_ma": int(volume_ma),
        "volume_ratio": round(volume / volume_ma, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="热门板块回调低吸 · 建仓信号检测")
    parser.add_argument("--date", help="目标日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--input", help="候选股 JSON，默认当天 full_market_candidate.json")
    parser.add_argument("--output", help="输出文件名，默认 entry_signal.json")
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON，不写入过程资料")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_entry_config()
    target_date, _ = normalize_date(args.date)
    output_directory = process_dir(target_date)
    input_path = Path(args.input) if args.input else output_directory / "full_market_candidate.json"
    candidates = load_json(input_path).get("candidates", [])

    client = create_client()
    required_days = max(config["volume_average_period"], config["breakout_ma_period"])
    daily = fetch_daily(client, target_date, required_days * 3)
    daily = normalize_daily(daily)
    if daily.empty:
        raise RuntimeError("未获取到建仓信号所需日线数据")

    signals = []
    daily_by_code = {code: records.sort_values("trade_date") for code, records in daily.groupby("ts_code")}
    for candidate in candidates:
        records = daily_by_code.get(candidate["code"])
        if records is None:
            continue
        records = records.loc[records["trade_date"] <= target_date]
        signal = build_signal(candidate, records, config)
        if signal:
            signals.append(signal)
    signals.sort(key=lambda item: item["volume_ratio"], reverse=True)

    payload = {
        "date": target_date,
        "source": str(input_path),
        "params": config,
        "stats": {
            "total_candidates": len(candidates),
            "with_daily_data": len(daily_by_code),
            "signals": len(signals),
        },
        "signals": signals,
    }
    if not args.dry_run:
        save_json(output_directory / (args.output or "entry_signal.json"), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()