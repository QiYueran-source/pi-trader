#!/usr/bin/env python3
"""按涨停、回调均线和反弹窗口筛选候选股。"""

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

from runtime_support import load_selection_config, normalize_date, process_dir


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=os.sys.stderr, flush=True)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def get_limit_pct(code: str) -> float:
    if code.endswith(".BJ"):
        return 29.5
    if code.startswith(("30", "68")):
        return 19.5
    return 9.8


def fetch_daily(client, trade_days: list[str]) -> pd.DataFrame:
    frames = []
    for index, trade_date in enumerate(trade_days):
        if index == 0 or (index + 1) % 5 == 0:
            log(f"拉取日线 {index + 1}/{len(trade_days)}: {trade_date}")
        daily = client.daily(
            trade_date=trade_date,
            fields="ts_code,trade_date,close,high,vol,pct_chg",
        )
        if daily is not None and not daily.empty:
            frames.append(daily)
        time.sleep(0.3)

    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    for column in ("close", "high", "vol", "pct_chg"):
        result[column] = result[column].astype(float)
    result["trade_date"] = result["trade_date"].astype(str)
    return result


def fetch_stock_info(client, codes: list[str]) -> dict[str, dict[str, str]]:
    result = {}
    for start in range(0, len(codes), 800):
        stocks = client.stock_basic(
            ts_code=",".join(codes[start : start + 800]),
            fields="ts_code,name,industry",
        )
        if stocks is None or stocks.empty:
            continue
        for _, row in stocks.iterrows():
            result[str(row["ts_code"])] = {
                "name": str(row["name"]),
                "industry": str(row["industry"] or ""),
            }
    return result


def calculate_ma(closes: list[float], period: int) -> float:
    return sum(closes[-period:]) / period


def passes_pullback_filter(records: pd.DataFrame, period: int, rebound_window: int) -> tuple[bool, float, int | None]:
    closes = records["close"].astype(float).tolist()
    if len(closes) < period:
        return False, 0.0, None

    current_close = closes[-1]
    current_ma = calculate_ma(closes, period)
    if current_close < current_ma:
        return False, current_ma, None

    last_below_index = None
    for index in range(period - 1, len(closes)):
        moving_average = calculate_ma(closes[: index + 1], period)
        if closes[index] < moving_average:
            last_below_index = index

    if last_below_index is None:
        return True, current_ma, None

    bounceback_days = len(closes) - 1 - last_below_index
    if bounceback_days > rebound_window:
        return False, current_ma, bounceback_days

    recovered_without_rebreak = all(
        closes[index] >= calculate_ma(closes[: index + 1], period)
        for index in range(last_below_index + 1, len(closes))
    )
    return recovered_without_rebreak, current_ma, bounceback_days


def build_candidate(code: str, records: pd.DataFrame, board_dates: list[str], info: dict, config: dict) -> dict | None:
    records = records.sort_values("trade_date")
    passed, moving_average, bounceback_days = passes_pullback_filter(
        records,
        config["pullback_ma_period"],
        config["rebound_window_days"],
    )
    if not passed:
        return None

    current_close = float(records.iloc[-1]["close"])
    board_records = records[records["trade_date"].isin(board_dates)]
    peak = float(board_records["high"].max()) if not board_records.empty else current_close
    return {
        "code": code,
        "name": info.get("name", ""),
        "industry": info.get("industry", ""),
        "board_count": len(board_dates),
        "board_dates": board_dates,
        "current_close": round(current_close, 3),
        "pullback_ma": round(moving_average, 3),
        "pullback_pct": round((current_close - peak) / peak * 100, 2),
        "bounceback_days": bounceback_days,
    }


def parse_industries(value: str | None) -> set[str] | None:
    if not value:
        return None
    industries = json.loads(value) if value.lstrip().startswith("[") else value.split(",")
    return {item.strip() for item in industries if item.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="热门板块回调低吸 · 候选股筛选")
    parser.add_argument("--date", help="目标日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--industry", help="行业名称，逗号分隔或 JSON 数组")
    parser.add_argument("--output", help="输出文件名，默认 full_market_candidate.json")
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON，不写入过程资料")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_selection_config()
    target_date, _ = normalize_date(args.date)
    client = create_client()
    start_date = (
        datetime.strptime(target_date, "%Y%m%d")
        - timedelta(days=(config["limit_up_window_days"] + config["pullback_ma_period"]) * 3)
    ).strftime("%Y%m%d")
    trade_days = get_trade_days(client, start_date, target_date)
    window_days = set(trade_days[-config["limit_up_window_days"] :])
    daily = fetch_daily(client, trade_days)
    if daily.empty:
        raise RuntimeError("未获取到日线数据")

    candidates = []
    limit_up_codes = set()
    grouped = daily.groupby("ts_code")
    for code, records in grouped:
        board_dates = sorted(
            records.loc[
                records["trade_date"].isin(window_days)
                & (records["pct_chg"] >= get_limit_pct(code)),
                "trade_date",
            ].tolist()
        )
        if config["min_limit_up_count"] <= len(board_dates) <= config["max_limit_up_count"]:
            limit_up_codes.add(code)
            candidates.append((code, records, board_dates))

    info = fetch_stock_info(client, sorted(limit_up_codes))
    industries = parse_industries(args.industry)
    result = []
    for code, records, board_dates in candidates:
        candidate = build_candidate(code, records, board_dates, info.get(code, {}), config)
        if candidate and (industries is None or candidate["industry"] in industries):
            result.append(candidate)
    result.sort(key=lambda item: item["pullback_pct"])
    payload = {
        "date": target_date,
        "params": config,
        "stats": {
            "total_limit_up_stocks": len(limit_up_codes),
            "final_candidates": len(result),
        },
        "candidates": result,
    }

    if not args.dry_run:
        save_json(process_dir(target_date) / (args.output or "full_market_candidate.json"), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()