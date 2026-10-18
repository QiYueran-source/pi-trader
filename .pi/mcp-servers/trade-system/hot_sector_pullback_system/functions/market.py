"""tushare 客户端、交易日历、日线/指数取数与窗口计算。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
import time

from functions.paths import DAILY_SLEEP_SECONDS, load_env

def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()

def fetch_trade_days(client: Any, start_date: str, end_date: str) -> list[str]:
    calendar = client.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, fields="cal_date,is_open")
    if calendar is None or calendar.empty:
        return []
    return sorted(calendar.loc[calendar["is_open"] == 1, "cal_date"].astype(str).tolist())

def fetch_trade_calendar(client: Any, api_date: str) -> dict[str, Any]:
    """单日交易日历：是否开市与上一交易日（来源 tushare.trade_cal，SSE）。"""
    frame = client.trade_cal(exchange="SSE", start_date=api_date, end_date=api_date, fields="exchange,cal_date,is_open,pretrade_date")
    if frame is None or frame.empty:
        raise ValueError(f"未获取到交易日历：{api_date}")
    record = frame.to_dict("records")[0]
    previous = record.get("pretrade_date")
    return {"is_open": int(record["is_open"]) == 1, "pretrade_date": str(previous) if previous else None}

def fetch_daily_market(client: Any, trade_days: list[str], fields: str) -> Any:
    import pandas as pd
    frames = []
    for trade_date in trade_days:
        frame = client.daily(trade_date=trade_date, fields=fields)
        if frame is not None and not frame.empty:
            frames.append(frame)
        time.sleep(DAILY_SLEEP_SECONDS)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["trade_date"] = result["trade_date"].astype(str)
    for column in ("open", "high", "close", "vol", "amount", "pct_chg"):
        if column in result.columns:
            result[column] = result[column].astype(float)
    return result

def fetch_stock_info(client: Any) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    stocks = client.stock_basic(fields="ts_code,name,industry,list_date")
    if stocks is None or stocks.empty:
        return {}, {}, {}
    industry_by_code: dict[str, str] = {}
    name_by_code: dict[str, str] = {}
    list_date_by_code: dict[str, str] = {}
    for _, row in stocks.iterrows():
        code = str(row["ts_code"])
        industry_by_code[code] = str(row["industry"] or "")
        name_by_code[code] = str(row["name"])
        list_date_by_code[code] = str(row["list_date"] or "")
    return industry_by_code, name_by_code, list_date_by_code

def fetch_index_pct(client: Any, ts_code: str, target_api_date: str) -> float | None:
    try:
        frame = client.index_daily(ts_code=ts_code, trade_date=target_api_date)
    except Exception:  # noqa: BLE001
        return None
    if frame is None or frame.empty or "pct_chg" not in frame:
        return None
    return round(float(frame.iloc[0]["pct_chg"]), 4)

def daily_window_start(target_api_date: str, calendar_days: int) -> str:
    return (datetime.strptime(target_api_date, "%Y%m%d") - timedelta(days=calendar_days)).strftime("%Y%m%d")

def market_daily_start(target_api_date: str, parameters: dict[str, dict[str, Any]]) -> str:
    selection = parameters["selection"]
    sector_heat = parameters["sector_heat"]
    calendar_days = (
        max(
            selection["limit_up_window_days"] + selection["pullback_ma_period"],
            sector_heat["limit_up_window_days"] + max(sector_heat["trend_ma_periods"]) + sector_heat["volume_ratio_window_days"],
        )
        * 3
    )
    return daily_window_start(target_api_date, calendar_days)
