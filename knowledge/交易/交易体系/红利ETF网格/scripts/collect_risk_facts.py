#!/opt/hermes/.venv/bin/python3
"""采集红利 ETF 网格的日频风险事实，不产生交易决策。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tushare as ts

from runtime_support import SYSTEM_ID, artifact_path, latest_prior_artifact, load_parameters, normalize_date, read_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利 ETF 网格风险事实采集")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--positions", help="持仓事实 JSON；缺省时按空仓处理")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def tushare_client() -> Any:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    ts.set_token(token)
    return ts.pro_api()


def fetch_daily(pro: Any, ts_code: str, api_date: str, calendar_days: int = 90) -> list[dict[str, float | str]]:
    end = datetime.strptime(api_date, "%Y%m%d")
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=(end - timedelta(days=calendar_days)).strftime("%Y%m%d"),
        end_date=api_date,
        fields="trade_date,close,high,low,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情")
    return [
        {
            "trade_date": str(row["trade_date"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "vol": float(row["vol"]),
            "amount": float(row["amount"]),
        }
        for row in frame.sort_values("trade_date").to_dict("records")
    ]


def load_positions(path: str | None) -> tuple[dict[str, Any], str]:
    if path is None:
        return {}, "not_provided"
    document = read_json(Path(path))
    positions = document.get("positions")
    if not isinstance(positions, dict):
        raise ValueError("持仓事实必须包含 positions 对象")
    return positions, str(Path(path))


def resolve_grid_parameters(directory_date: str) -> tuple[dict[str, Any], str]:
    current = artifact_path(directory_date, "grid_parameters.json")
    path = current if current.is_file() else latest_prior_artifact(directory_date, "grid_parameters.json")
    if path is None:
        raise ValueError("缺少当日或前序 grid_parameters.json，无法确定风险基准")
    return read_json(path), str(path)


def consecutive_down(rows: list[dict[str, float | str]]) -> tuple[int, float]:
    days = 0
    cumulative_loss = 0.0
    for index in range(len(rows) - 1, 0, -1):
        current = float(rows[index]["close"])
        previous = float(rows[index - 1]["close"])
        if current >= previous:
            break
        days += 1
        cumulative_loss = 1 - (1 - cumulative_loss) * (current / previous)
    return days, cumulative_loss


def average_range(rows: list[dict[str, float | str]], window: int) -> float:
    ranges = []
    for index in range(1, len(rows)):
        previous_close = float(rows[index - 1]["close"])
        if previous_close > 0:
            ranges.append((float(rows[index]["high"]) - float(rows[index]["low"])) / previous_close)
    selected = ranges[-window:]
    return sum(selected) / len(selected) if selected else 0.0


def collect_facts(rows: list[dict[str, float | str]], calibration: dict[str, Any], risk: dict[str, Any], position: dict[str, Any], total_capital_amount: int) -> dict[str, Any]:
    latest = rows[-1]
    previous_close = float(rows[-2]["close"]) if len(rows) > 1 else float(latest["close"])
    close = float(latest["close"])
    daily_change = close / previous_close - 1 if previous_close else 0.0
    volume_window = rows[-risk["volatility"]["average_range_window_trading_days"]:]
    average_volume = sum(float(row["vol"]) for row in volume_window) / len(volume_window)
    volume_ratio = float(latest["vol"]) / average_volume if average_volume else 0.0
    down_days, down_loss = consecutive_down(rows)
    average_range_ratio = average_range(rows, risk["volatility"]["average_range_window_trading_days"])
    baseline_close = float(calibration["grids"]["dividend"]["latest_close"])
    lower_boundary = baseline_close * (1 - float(risk["price_boundary"]["lower_deviation_ratio"]))
    upper_boundary = baseline_close * (1 + float(risk["price_boundary"]["upper_deviation_ratio"]))
    shares = int(position.get("shares", 0)) if isinstance(position, dict) else 0
    market_value = float(position.get("market_value_amount", shares * close)) if isinstance(position, dict) else 0.0
    position_ratio = market_value / total_capital_amount
    anomalies = risk["market_anomalies"]
    return {
        "market": {
            "trade_date": latest["trade_date"],
            "close": close,
            "daily_change_ratio": round(daily_change, 8),
            "volume_ratio": round(volume_ratio, 8),
            "average_range_ratio": round(average_range_ratio, 8),
            "consecutive_down_trading_days": down_days,
            "consecutive_down_loss_ratio": round(down_loss, 8),
        },
        "calibration_reference": {
            "latest_close": baseline_close,
            "lower_boundary": round(lower_boundary, 8),
            "upper_boundary": round(upper_boundary, 8),
        },
        "position": {
            "shares": shares,
            "market_value_amount": round(market_value, 2),
            "position_ratio": round(position_ratio, 8),
        },
        "threshold_hits": {
            "below_price_boundary": close <= lower_boundary,
            "above_price_boundary": close >= upper_boundary,
            "position_fuse": position_ratio >= float(risk["capital_constraints"]["position_fuse_ratio"]),
            "consecutive_down": down_days >= int(anomalies["consecutive_down_trading_days"]) and down_loss >= float(anomalies["consecutive_down_loss_ratio"]),
            "sharp_drop_with_volume": daily_change <= -float(anomalies["sharp_drop_ratio"]) and volume_ratio >= float(anomalies["sharp_drop_volume_ratio"]),
            "sharp_rise_notice": daily_change >= float(anomalies["sharp_rise_notice_ratio"]),
            "sharp_rise_take_profit_notice": daily_change >= float(anomalies["sharp_rise_take_profit_notice_ratio"]),
        },
    }


def main() -> None:
    args = parse_args()
    api_date, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    risk = parameters["risk"]
    instruments = parameters["instruments"]
    positions, position_source = load_positions(args.positions)
    calibration, calibration_source = resolve_grid_parameters(directory_date)
    pro = tushare_client()

    facts = {}
    for instrument_id in risk["scope"]["instrument_ids"]:
        rows = fetch_daily(pro, instruments["instruments"][instrument_id]["ts_code"], api_date)
        facts[instrument_id] = collect_facts(
            rows,
            calibration,
            risk,
            positions.get(instrument_id, {}),
            instruments["account"]["total_capital_amount"],
        )

    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "risk_facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameter_schema_version": risk["schema_version"],
        "positions_source": position_source,
        "calibration_source": calibration_source,
        "facts": facts,
    }
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "risk_facts.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()