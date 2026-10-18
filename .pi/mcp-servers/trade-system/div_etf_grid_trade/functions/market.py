"""tushare 客户端与行情取样、涨跌停与连跌口径。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from functions.paths import REPO_ROOT, load_env


def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()


def fetch_fund_daily(pro: Any, code: str, api_date: str, calendar_days: int) -> list[dict[str, Any]]:
    end = datetime.strptime(api_date, "%Y%m%d")
    frame = pro.fund_daily(
        ts_code=code,
        start_date=(end - timedelta(days=calendar_days)).strftime("%Y%m%d"),
        end_date=api_date,
        fields="trade_date,close,high,low,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {code} 的行情")
    rows = []
    for row in frame.sort_values("trade_date").to_dict("records"):
        rows.append({key: (str(row[key]) if key == "trade_date" else float(row[key])) for key in ("trade_date", "close", "high", "low", "vol", "amount")})
    if rows[-1]["trade_date"] != api_date:
        raise ValueError(f"{code} 的目标日期没有行情：{api_date}")
    return rows


def fetch_market_daily(pro: Any, api_date: str) -> list[dict[str, Any]]:
    frame = pro.daily(trade_date=api_date, fields="ts_code,pct_chg")
    if frame is None or frame.empty:
        raise ValueError(f"无 {api_date} 全市场日线数据")
    return frame.to_dict("records")


def board_limit_ratio(code: str) -> float:
    raw = code.split(".", 1)[0]
    if code.endswith(".BJ") or raw.startswith(("8", "4", "92")):
        return 0.30
    if raw.startswith(("30", "68")):
        return 0.20
    return 0.10


def is_limit_up(code: str, pct_change: float) -> bool:
    return pct_change / 100 >= board_limit_ratio(code) - 0.002


def is_limit_down(code: str, pct_change: float) -> bool:
    return pct_change / 100 <= -(board_limit_ratio(code) - 0.002)


def consecutive_down(rows: list[dict[str, Any]]) -> tuple[int, float]:
    days = 0
    cumulative = 0.0
    for index in range(len(rows) - 1, 0, -1):
        current = float(rows[index]["close"])
        previous = float(rows[index - 1]["close"])
        if current >= previous:
            break
        days += 1
        cumulative = 1 - (1 - cumulative) * current / previous
    return days, cumulative


def average_range(rows: list[dict[str, Any]], window: int) -> float:
    values = []
    for index in range(1, len(rows)):
        previous = float(rows[index - 1]["close"])
        if previous > 0:
            values.append((float(rows[index]["high"]) - float(rows[index]["low"])) / previous)
    values = values[-window:]
    return sum(values) / len(values) if values else 0.0
