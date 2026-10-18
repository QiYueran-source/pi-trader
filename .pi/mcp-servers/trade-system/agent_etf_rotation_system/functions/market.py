"""tushare 客户端与交易日历。"""

from __future__ import annotations

import os
from typing import Any

from functions.paths import load_env

def get_client() -> Any:
    """本服务自带的 tushare 客户端（token 读 `.pi/mcp-servers/tushare/.env`）。"""
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()

def fetch_trade_calendar(pro: Any, api_date: str) -> dict[str, Any]:
    """单日交易日历：是否开市与上一交易日（来源 tushare.trade_cal，SSE）。"""
    frame = pro.trade_cal(exchange="SSE", start_date=api_date, end_date=api_date, fields="exchange,cal_date,is_open,pretrade_date")
    if frame is None or frame.empty:
        raise ValueError(f"未获取到交易日历：{api_date}")
    record = frame.to_dict("records")[0]
    previous = record.get("pretrade_date")
    return {"is_open": int(record["is_open"]) == 1, "pretrade_date": str(previous) if previous else None}
