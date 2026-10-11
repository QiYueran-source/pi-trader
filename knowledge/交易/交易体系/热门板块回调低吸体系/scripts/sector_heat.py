#!/usr/bin/env python3
"""计算候选行业的涨停、连板和技术热度事实。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts

from runtime_support import load_sector_heat_config, normalize_date, process_dir


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


def get_limit_pct(code: str) -> float:
    if code.endswith(".BJ"):
        return 29.5
    if code.startswith(("30", "68")):
        return 19.5
    return 9.8


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
        daily = client.daily(
            trade_date=trade_date,
            fields="ts_code,trade_date,close,vol,pct_chg",
        )
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
    for field in ("close", "vol", "pct_chg"):
        result[field] = result[field].astype(float)
    return result


def fetch_stock_info(client) -> tuple[dict[str, str], dict[str, str]]:
    stocks = client.stock_basic(fields="ts_code,name,industry")
    if stocks is None or stocks.empty:
        return {}, {}
    industry_by_code = {
        str(row["ts_code"]): str(row["industry"] or "")
        for _, row in stocks.iterrows()
    }
    name_by_code = {
        str(row["ts_code"]): str(row["name"])
        for _, row in stocks.iterrows()
    }
    return industry_by_code, name_by_code


def consecutive_limit_up(records: pd.DataFrame, code: str) -> int:
    count = 0
    for _, row in records.sort_values("trade_date", ascending=False).iterrows():
        if float(row["pct_chg"]) < get_limit_pct(code):
            break
        count += 1
    return count


def build_board_dimensions(
    daily: pd.DataFrame,
    target_date: str,
    candidate_sectors: list[str],
    industry_by_code: dict[str, str],
    name_by_code: dict[str, str],
) -> tuple[list[dict], dict, list[dict], dict[str, int]]:
    limit_up_count = defaultdict(int)
    board_tiers = defaultdict(lambda: defaultdict(int))
    highest_count = 0
    highest_code = ""
    highest_sector = ""

    for code, records in daily.groupby("ts_code"):
        records = records.sort_values("trade_date")
        today = records.loc[records["trade_date"] == target_date]
        if today.empty:
            continue

        sector = industry_by_code.get(code, "")
        if sector in candidate_sectors and float(today.iloc[-1]["pct_chg"]) >= get_limit_pct(code):
            limit_up_count[sector] += 1

        board_count = consecutive_limit_up(records, code)
        if board_count > highest_count:
            highest_count = board_count
            highest_code = code
            highest_sector = sector
        if sector in candidate_sectors and board_count > 0:
            tier = "board_6_plus" if board_count >= 6 else f"board_{board_count}"
            board_tiers[sector][tier] += 1

    ranking = [
        {"sector": sector, "limit_up_count": limit_up_count[sector]}
        for sector in candidate_sectors
    ]
    ranking.sort(key=lambda item: item["limit_up_count"], reverse=True)
    tiers = []
    for sector in candidate_sectors:
        tiers.append(
            {
                "sector": sector,
                **{f"board_{level}": board_tiers[sector][f"board_{level}"] for level in range(1, 6)},
                "board_6_plus": board_tiers[sector]["board_6_plus"],
            }
        )

    highest = {
        "count": highest_count,
        "code": highest_code,
        "name": name_by_code.get(highest_code, ""),
        "sector": highest_sector,
    }
    return ranking, highest, tiers, dict(limit_up_count)


def moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def build_technical_pattern(
    daily: pd.DataFrame,
    candidate_sectors: list[str],
    industry_by_code: dict[str, str],
    config: dict,
    limit_up_count: dict[str, int],
) -> list[dict]:
    short_period, long_period = config["trend_ma_periods"]
    volume_window = config["volume_ratio_window_days"]
    patterns = []

    daily_with_sector = daily.assign(sector=daily["ts_code"].map(industry_by_code))
    for sector in candidate_sectors:
        sector_daily = daily_with_sector.loc[daily_with_sector["sector"] == sector]
        grouped = sector_daily.groupby("trade_date", sort=True)
        pct_changes = grouped["pct_chg"].mean().astype(float).tolist()
        volumes = grouped["vol"].sum().astype(float).tolist()
        short_ma = moving_average(pct_changes, short_period)
        long_ma = moving_average(pct_changes, long_period)
        prior_volumes = volumes[-volume_window - 1 : -1]
        volume_ratio = (
            volumes[-1] / (sum(prior_volumes) / len(prior_volumes))
            if len(prior_volumes) == volume_window and sum(prior_volumes) > 0
            else None
        )
        patterns.append(
            {
                "sector": sector,
                "limit_up_count": limit_up_count.get(sector, 0),
                "short_ma_pct": round(short_ma, 2) if short_ma is not None else None,
                "long_ma_pct": round(long_ma, 2) if long_ma is not None else None,
                "short_ma_gt_long_ma": short_ma > long_ma if short_ma is not None and long_ma is not None else None,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
                "valid": long_ma is not None,
            }
        )
    return patterns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="热门板块回调低吸 · 板块热度分析")
    parser.add_argument("--date", help="目标日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--input", help="候选股 JSON，默认当天 full_market_candidate.json")
    parser.add_argument("--output", help="输出文件名，默认 sector_heat.json")
    parser.add_argument("--dry-run", action="store_true", help="只输出 JSON，不写入过程资料")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_sector_heat_config()
    target_date, _ = normalize_date(args.date)
    output_directory = process_dir(target_date)
    input_path = Path(args.input) if args.input else output_directory / "full_market_candidate.json"
    candidates = load_json(input_path).get("candidates", [])
    candidate_sectors = sorted({item["industry"] for item in candidates if item.get("industry")})

    if not candidate_sectors:
        payload = {
            "date": target_date,
            "params": config,
            "stats": {"total_candidates": len(candidates), "candidate_sectors": 0, "max_board_count": 0},
            "candidate_sectors": [],
            "dimensions": {"limit_up_ranking": [], "highest_board": {}, "board_tiers": [], "technical_pattern": []},
        }
    else:
        client = create_client()
        max_period = max(config["trend_ma_periods"])
        daily = fetch_daily(client, target_date, (config["limit_up_window_days"] + max_period) * 3)
        daily = normalize_daily(daily)
        if daily.empty:
            raise RuntimeError("未获取到板块热度所需日线数据")

        industry_by_code, name_by_code = fetch_stock_info(client)
        ranking, highest, tiers, limit_up_count = build_board_dimensions(
            daily,
            target_date,
            candidate_sectors,
            industry_by_code,
            name_by_code,
        )
        technical_pattern = build_technical_pattern(
            daily,
            candidate_sectors,
            industry_by_code,
            config,
            limit_up_count,
        )
        payload = {
            "date": target_date,
            "params": config,
            "stats": {
                "total_candidates": len(candidates),
                "candidate_sectors": len(candidate_sectors),
                "max_board_count": highest["count"],
            },
            "candidate_sectors": candidate_sectors,
            "dimensions": {
                "limit_up_ranking": ranking,
                "highest_board": highest,
                "board_tiers": tiers,
                "technical_pattern": technical_pattern,
            },
        }

    if not args.dry_run:
        save_json(output_directory / (args.output or "sector_heat.json"), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()