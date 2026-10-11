#!/usr/bin/env python3
"""判断指定交易日是否应执行网格参数校准。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import tushare as ts

from runtime_support import SYSTEM_ID, artifact_path, load_parameters, normalize_date, latest_prior_artifact, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格调参检查")
    parser.add_argument("--date", required=True, help="检查日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--force", action="store_true", help="显式要求调参")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def tushare_client() -> Any:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def is_trading_day(pro: Any, value: datetime) -> bool:
    api_date = value.strftime("%Y%m%d")
    frame = pro.trade_cal(exchange="SSE", start_date=api_date, end_date=api_date, fields="is_open")
    return frame is not None and not frame.empty and int(frame.iloc[0]["is_open"]) == 1


def main() -> None:
    args = parse_args()
    _, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    schedule = parameters["grid"]["calibration"]["schedule"]
    run_date = datetime.strptime(directory_date, "%Y-%m-%d")
    pro = tushare_client()
    today_is_trading = is_trading_day(pro, run_date)
    next_day_is_trading = is_trading_day(pro, run_date + timedelta(days=1))
    previous = latest_prior_artifact(directory_date, "grid_parameters.json")

    if args.force:
        should_calibrate, reason = True, "explicit_manual_request"
    elif previous is None:
        should_calibrate, reason = True, "no_prior_grid_parameters"
    elif today_is_trading and not next_day_is_trading:
        should_calibrate, reason = True, "weekly_last_trading_day"
    else:
        should_calibrate, reason = False, "schedule_not_triggered"

    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "calibration_check",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schedule": schedule,
        "today_is_trading_day": today_is_trading,
        "next_calendar_day_is_trading_day": next_day_is_trading,
        "latest_prior_grid_parameters": str(previous) if previous else None,
        "should_calibrate": should_calibrate,
        "reason": reason,
    }
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "calibration_check.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()