#!/usr/bin/env python3
"""计算指定交易日的双标的网格参数，并写入日期化过程资料。"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any

import tushare as ts

from runtime_support import SYSTEM_ID, artifact_path, load_parameters, normalize_date, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格参数计算")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def tushare_client() -> Any:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def fetch_daily(pro: Any, ts_code: str, api_date: str, calendar_days: int) -> list[dict[str, float | str]]:
    end = datetime.strptime(api_date, "%Y%m%d")
    start = end - __import__("datetime").timedelta(days=calendar_days)
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=start.strftime("%Y%m%d"),
        end_date=api_date,
        fields="ts_code,trade_date,close,high,low,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情")
    rows = frame.sort_values("trade_date").to_dict("records")
    return [
        {
            "trade_date": str(row["trade_date"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "vol": float(row["vol"]),
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


def maximum_drawdown_ratio(rows: list[dict[str, float | str]]) -> float:
    peak = 0.0
    maximum_drawdown = 0.0
    for row in rows:
        close = float(row["close"])
        peak = max(peak, close)
        if peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - close) / peak)
    return maximum_drawdown


def calculate_grid(instrument_id: str, instrument: dict[str, Any], spec: dict[str, Any], rows: list[dict[str, float | str]], window_days: int, minimum_step_ratio: float) -> dict[str, Any]:
    window = rows[-window_days:]
    if len(window) < window_days:
        raise ValueError(f"{instrument_id} 行情不足 {window_days} 个交易日")
    drawdown_ratio = maximum_drawdown_ratio(window)
    buy_step_ratio = max(drawdown_ratio * float(spec["drawdown_coefficient"]), minimum_step_ratio)
    sell_step_ratio = 1 / (1 - buy_step_ratio) - 1
    latest = window[-1]
    return {
        "instrument_id": instrument_id,
        "ts_code": instrument["ts_code"],
        "name": instrument["name"],
        "source_data": {
            "start_trade_date": window[0]["trade_date"],
            "end_trade_date": latest["trade_date"],
            "trading_days": len(window),
        },
        "latest_close": latest["close"],
        "maximum_drawdown_ratio": round(drawdown_ratio, 8),
        "drawdown_coefficient": spec["drawdown_coefficient"],
        "buy_step_ratio": round(buy_step_ratio, 8),
        "sell_step_ratio": round(sell_step_ratio, 8),
        "buy_confirmation_rebound_ratio": round(buy_step_ratio * float(spec["buy_confirmation_rebound_ratio"]), 8),
        "sell_confirmation_pullback_ratio": round(sell_step_ratio * float(spec["sell_confirmation_pullback_ratio"]), 8),
        "buy_shares": spec["buy_shares"],
        "sell_shares": spec["sell_shares"],
    }


def main() -> None:
    args = parse_args()
    api_date, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    grid_config = parameters["grid"]
    instruments = parameters["instruments"]["instruments"]
    calibration = grid_config["calibration"]
    pro = tushare_client()

    results = {}
    for instrument_id, instrument in instruments.items():
        rows = fetch_daily(
            pro,
            instrument["ts_code"],
            api_date,
            calibration["fetch_lookback_calendar_days"],
        )
        # 窗口支持 per-grid 覆盖（如红利10日/双创22日），缺省回退全局配置
        grid_spec = grid_config["grids"][instrument_id]
        window_days = int(grid_spec.get("step_window_trading_days", calibration["step_window_trading_days"]))
        results[instrument_id] = calculate_grid(
            instrument_id,
            instrument,
            grid_spec,
            rows,
            window_days,
            float(calibration["minimum_step_ratio"]),
        )

    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "grid_parameters",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameter_schema_version": grid_config["schema_version"],
        "formula": grid_config["step_formula"],
        "grids": results,
    }
    if args.dry_run:
        print(__import__("json").dumps(output, ensure_ascii=False, indent=2))
        return

    path = artifact_path(directory_date, "grid_parameters.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()