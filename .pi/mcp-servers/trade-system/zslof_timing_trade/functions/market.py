"""行情客户端与日线取数。"""

from __future__ import annotations

import os
from typing import Any

from functions.paths import load_env

def get_client() -> Any:
    load_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()

def fetch_daily(pro: Any, ts_code: str, start_api_date: str, target_api_date: str) -> list[dict[str, Any]]:
    frame = pro.fund_daily(
        ts_code=ts_code,
        start_date=start_api_date,
        end_date=target_api_date,
        fields="ts_code,trade_date,close,pre_close,vol,amount",
    )
    if frame is None or frame.empty:
        raise ValueError(f"未获取到 {ts_code} 的行情：{start_api_date}~{target_api_date}")
    rows = []
    for record in sorted(frame.to_dict("records"), key=lambda item: str(item["trade_date"])):
        rows.append({
            "trade_date": str(record["trade_date"]),
            "close": float(record["close"]),
            "pre_close": float(record["pre_close"]) if record.get("pre_close") is not None else None,
            "vol": float(record["vol"]) if record.get("vol") is not None else None,
        })
    if rows[-1]["trade_date"] != target_api_date:
        raise ValueError(f"目标日期没有行情数据：{target_api_date}")
    return rows


def fetch_trade_calendar(pro: Any, api_date: str) -> dict[str, Any]:
    """单日交易日历：是否开市与上一交易日（来源 tushare.trade_cal，SSE）。"""
    frame = pro.trade_cal(exchange="SSE", start_date=api_date, end_date=api_date, fields="exchange,cal_date,is_open,pretrade_date")
    if frame is None or frame.empty:
        raise ValueError(f"未获取到交易日历：{api_date}")
    record = frame.to_dict("records")[0]
    previous = record.get("pretrade_date")
    return {"is_open": int(record["is_open"]) == 1, "pretrade_date": str(previous) if previous else None}
