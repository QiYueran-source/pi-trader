#!/usr/bin/env python3
"""采集红利科创 ETF 双网格的日频风险事实，不产生交易决策。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime_support import SYSTEM_ID, artifact_path, load_parameter, load_parameters, logical_path, normalize_date, read_json, tushare_client, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格风险事实采集")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--positions", help="持仓事实 JSON；缺省时按空仓处理")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


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
    positions = dict(positions)
    cash = document.get("cash")
    if isinstance(cash, (int, float)) and not isinstance(cash, bool):
        positions["cash"] = float(cash)
    return positions, logical_path(path)


def resolve_price_boundary(instrument_id: str, risk: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """v4：价格边界直接取自 params/risk.json#price_boundary（不再依赖网格校准产物）。"""
    by_instrument = risk["price_boundary"]["by_instrument"]
    if instrument_id not in by_instrument:
        raise ValueError(f"risk.price_boundary.by_instrument 缺少 {instrument_id}")
    boundary = by_instrument[instrument_id]
    return boundary, f"params/risk.json#price_boundary.by_instrument.{instrument_id}"


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


def collect_facts(rows: list[dict[str, float | str]], risk: dict[str, Any], boundary: dict[str, Any], position: dict[str, Any], nav_amount: float, nav_source: str) -> dict[str, Any]:
    latest = rows[-1]
    previous_close = float(rows[-2]["close"]) if len(rows) > 1 else float(latest["close"])
    close = float(latest["close"])
    daily_change = close / previous_close - 1 if previous_close else 0.0
    window = int(risk["volatility"]["average_range_window_trading_days"])
    volume_window = rows[-window:]
    average_volume = sum(float(row["vol"]) for row in volume_window) / len(volume_window)
    volume_ratio = float(latest["vol"]) / average_volume if average_volume else 0.0
    down_days, down_loss = consecutive_down(rows)
    average_range_ratio = average_range(rows, window)
    lower_boundary = float(boundary["lower_boundary"])
    upper_boundary = float(boundary["upper_boundary"])
    shares = int(position.get("shares", 0)) if isinstance(position, dict) else 0
    market_value = float(position.get("market_value_amount", shares * close)) if isinstance(position, dict) else 0.0
    weight = market_value / nav_amount if nav_amount else 0.0
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
        "price_boundary_reference": {
            "reference_price": float(boundary["reference_price"]),
            "lower_boundary": lower_boundary,
            "upper_boundary": upper_boundary,
        },
        "position": {
            "shares": shares,
            "market_value_amount": round(market_value, 2),
            "leg_weight": round(weight, 8),
            "weight_base": "system_nav",
            "nav_amount": round(nav_amount, 2),
            "nav_source": nav_source,
        },
        "threshold_hits": {
            "below_price_boundary": close <= lower_boundary,
            "above_price_boundary": close >= upper_boundary,
            "consecutive_down": down_days >= int(anomalies["consecutive_down_trading_days"]) and down_loss >= float(anomalies["consecutive_down_loss_ratio"]),
            "sharp_drop_with_volume": daily_change <= -float(anomalies["sharp_drop_ratio"]) and volume_ratio >= float(anomalies["sharp_drop_volume_ratio"]),
            "sharp_rise_notice": daily_change >= float(anomalies["sharp_rise_notice_ratio"]),
            "sharp_rise_take_profit_notice": daily_change >= float(anomalies["sharp_rise_take_profit_notice_ratio"]),
        },
    }


def system_nav(positions: dict[str, Any], instruments: dict[str, Any], closes: dict[str, float]) -> tuple[float, str]:
    """体系口径总资产 = 双标的持仓市值 + 体系现金（缺现金时回退名义资金池）。"""
    market_value = 0.0
    for instrument_id, instrument in instruments["instruments"].items():
        shares = int(positions.get(instrument_id, {}).get("shares", 0) or 0)
        market_value += shares * closes.get(instrument_id, 0.0)
    cash = positions.get("cash")
    if isinstance(cash, (int, float)) and not isinstance(cash, bool):
        return market_value + float(cash), "positions.cash"
    return market_value + float(instruments["account"]["total_capital_amount"]), "instruments.account.total_capital_amount"


def main() -> None:
    args = parse_args()
    api_date, directory_date = normalize_date(args.date)
    parameters = load_parameters()
    risk = parameters["risk"]
    instruments = parameters["instruments"]
    regulator = parameters["regulator"]
    positions, position_source = load_positions(args.positions)
    pro = tushare_client()

    rows_by_instrument: dict[str, list[dict[str, float | str]]] = {}
    for instrument_id in risk["scope"]["instrument_ids"]:
        rows_by_instrument[instrument_id] = fetch_daily(pro, instruments["instruments"][instrument_id]["ts_code"], api_date)
    closes = {instrument_id: float(rows[-1]["close"]) for instrument_id, rows in rows_by_instrument.items()}
    nav_amount, nav_source = system_nav(positions, instruments, closes)

    facts = {}
    for instrument_id, rows in rows_by_instrument.items():
        boundary, boundary_source = resolve_price_boundary(instrument_id, risk)
        facts[instrument_id] = collect_facts(rows, risk, boundary, positions.get(instrument_id, {}), nav_amount, nav_source)
        facts[instrument_id]["price_boundary_reference"]["source"] = boundary_source

    output = {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": "risk_facts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameter_schema_version": risk["schema_version"],
        "version": regulator["version"],
        "positions_source": position_source,
        "facts": facts,
        "note": "v4：采集双标的；价格边界取自 params/risk.json#price_boundary（不再依赖网格校准产物）；资本约束见 params/regulator.json#capital_guard。",
    }
    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    path = artifact_path(directory_date, "risk_facts.json")
    write_json(path, output)
    print(path)


if __name__ == "__main__":
    main()
