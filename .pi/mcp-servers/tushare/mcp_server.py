#!/usr/bin/env python3
"""统一 Tushare 数据 MCP。

官方 Tushare 用于常规数据，分钟数据在官方失败后按配置降级到代理。
密钥从本文件所在目录的 .env 读取，不通过 MCP 工具返回。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

MCP_DIR = Path(__file__).resolve().parent
ENV_FILE = MCP_DIR / ".env"


def load_env(path: Path) -> None:
    """读取 MCP 私有环境文件，不覆盖 Compose 显式注入的变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


load_env(ENV_FILE)

STOCK_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d")


def result_ok(api: str, source: str, request: dict[str, Any], data: list[dict[str, Any]], warnings_: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "api": api,
        "source": source,
        "fallback_used": source == "proxy",
        "request": request,
        "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "row_count": len(data),
        "data_status": "ok" if data else "source_empty",
        "warnings": warnings_ or [],
        "data": data,
    }


def result_error(api: str, request: dict[str, Any], error_type: str, message: str, source: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "api": api,
        "source": source,
        "request": request,
        "error": {"type": error_type, "message": message},
        "data": [],
    }


def normalize_date(value: str, name: str) -> str:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"{name} 必须是 YYYYMMDD 或 YYYY-MM-DD")


def normalize_code(value: str) -> str:
    code = value.strip().upper()
    if not STOCK_CODE_RE.fullmatch(code):
        raise ValueError(f"证券代码必须包含 .SH、.SZ 或 .BJ 后缀：{value}")
    return code


def request_dates(start_date: str, end_date: str) -> tuple[str, str]:
    start = normalize_date(start_date, "start_date")
    end = normalize_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    return start, end


def records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "where") and hasattr(frame, "to_dict"):
        frame = frame.where(frame.notna(), None)
        return frame.to_dict("records")
    return list(frame)


def official_call(api: str, **params: Any) -> list[dict[str, Any]]:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("当前 Python 环境未安装 tushare") from exc
    pro = ts.pro_api(token)
    method = getattr(pro, api)
    return records_from_frame(method(**params))


def proxy_call(api: str, **params: Any) -> list[dict[str, Any]]:
    url = os.getenv("TUSHARE_PROMAX_URL", "").strip()
    key = os.getenv("TUSHARE_PROMAX_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("TUSHARE_PROMAX_URL 或 TUSHARE_PROMAX_KEY 未配置")
    response = requests.get(
        f"{url.rstrip('/')}/{api}",
        params=params,
        headers={"X-API-Key": key},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"代理返回异常：{payload}")
    data = payload.get("data") or {}
    fields = data.get("fields", [])
    return [dict(zip(fields, row)) for row in data.get("items", [])]


def query_regular(api: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        data = official_call(api, **params)
        return result_ok(api, "official", params, data)
    except PermissionError as exc:
        return result_error(api, params, "permission", str(exc), "official")
    except Exception as exc:  # noqa: BLE001
        return result_error(api, params, "upstream_error", str(exc), "official")


def query_minutes(params: dict[str, Any]) -> dict[str, Any]:
    try:
        data = official_call("stk_mins", **params)
        if not data:
            return result_error("stk_mins", params, "source_empty", "官方接口未返回目标时段分钟数据", "official")
        return result_ok("stk_mins", "official", params, data)
    except Exception as official_error:  # noqa: BLE001
        try:
            data = proxy_call("stk_mins", **params)
            dates = {str(row.get("trade_time", ""))[:10].replace("-", "") for row in data}
            target = params["start_date"][:8]
            if dates and dates != {target}:
                return result_error("stk_mins", params, "date_mismatch", f"代理返回日期 {sorted(dates)}，目标日期为 {target}", "proxy")
            if not data:
                return result_error("stk_mins", params, "source_empty", "代理未返回目标时段分钟数据", "proxy")
            return result_ok("stk_mins", "proxy", params, data, [f"官方接口失败，已切换代理：{official_error}"])
        except Exception as proxy_error:  # noqa: BLE001
            return result_error("stk_mins", params, "all_sources_failed", f"official={official_error}; proxy={proxy_error}")


def tool_trade_calendar(arguments: dict[str, Any]) -> dict[str, Any]:
    start, end = request_dates(arguments["start_date"], arguments["end_date"])
    exchange = arguments.get("exchange", "SSE")
    return query_regular("trade_cal", {"exchange": exchange, "start_date": start, "end_date": end, "fields": "exchange,cal_date,is_open,pretrade_date"})


def tool_stock_daily(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(arguments["ts_code"])
    start, end = request_dates(arguments["start_date"], arguments["end_date"])
    return query_regular("daily", {"ts_code": code, "start_date": start, "end_date": end})


def tool_market_daily(arguments: dict[str, Any]) -> dict[str, Any]:
    trade_date = normalize_date(arguments["trade_date"], "trade_date")
    return query_regular("daily", {"trade_date": trade_date})


def tool_fund_daily(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(arguments["ts_code"])
    start, end = request_dates(arguments["start_date"], arguments["end_date"])
    return query_regular("fund_daily", {"ts_code": code, "start_date": start, "end_date": end})


def tool_fund_adj(arguments: dict[str, Any]) -> dict[str, Any]:
    """查询基金复权因子，供 ETF 回放和收益口径核验使用。"""
    code = normalize_code(arguments["ts_code"])
    start, end = request_dates(arguments["start_date"], arguments["end_date"])
    return query_regular("fund_adj", {"ts_code": code, "start_date": start, "end_date": end})


def tool_index_daily(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(arguments["ts_code"])
    start, end = request_dates(arguments["start_date"], arguments["end_date"])
    return query_regular("index_daily", {"ts_code": code, "start_date": start, "end_date": end})


def tool_stock_basic(arguments: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {"fields": "ts_code,name,industry,market,list_date"}
    if arguments.get("ts_code"):
        codes = [normalize_code(item) for item in arguments["ts_code"].split(",")]
        params["ts_code"] = ",".join(codes)
    return query_regular("stock_basic", params)


def tool_stock_minutes(arguments: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(arguments["ts_code"])
    start_date = arguments["start_date"]
    end_date = arguments["end_date"]
    if len(start_date) == 8:
        start_date = datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d")
    if len(end_date) == 8:
        end_date = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")
    return query_minutes({"ts_code": code, "freq": arguments.get("freq", "5min"), "start_date": start_date, "end_date": end_date})


_STRING_DATE = {"type": "string", "description": "YYYYMMDD 或 YYYY-MM-DD"}
_CODE = {"type": "string", "description": "带交易所后缀，如 600519.SH、000001.SZ、920002.BJ"}
_DATE_RANGE = {"type": "object", "properties": {"start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["start_date", "end_date"]}

_TOOLS = [
    Tool(name="get_trade_calendar", description="查询交易日历和前一交易日。", inputSchema={"type": "object", "properties": {"exchange": {"type": "string", "default": "SSE"}, "start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["start_date", "end_date"]}),
    Tool(name="get_stock_daily", description="查询单只股票的日线数据。股票代码必须带交易所后缀。", inputSchema={"type": "object", "properties": {"ts_code": _CODE, "start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["ts_code", "start_date", "end_date"]}),
    Tool(name="get_market_daily", description="查询指定交易日的全市场股票日线，适合涨停筛选。", inputSchema={"type": "object", "properties": {"trade_date": _STRING_DATE}, "required": ["trade_date"]}),
    Tool(name="get_fund_daily", description="查询 ETF 或基金日线，使用 fund_daily 而不是股票 daily。", inputSchema={"type": "object", "properties": {"ts_code": _CODE, "start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["ts_code", "start_date", "end_date"]}),
    Tool(name="get_fund_adj", description="查询 ETF 或基金复权因子，用于收益与除权口径核验。", inputSchema={"type": "object", "properties": {"ts_code": _CODE, "start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["ts_code", "start_date", "end_date"]}),
    Tool(name="get_index_daily", description="查询指数日线，如 399006.SZ、000001.SH、000688.SH。", inputSchema={"type": "object", "properties": {"ts_code": _CODE, "start_date": _STRING_DATE, "end_date": _STRING_DATE}, "required": ["ts_code", "start_date", "end_date"]}),
    Tool(name="get_stock_basic", description="查询股票名称、行业、市场和上市日期。", inputSchema={"type": "object", "properties": {"ts_code": {"type": "string", "description": "可选，逗号分隔的完整股票代码"}}}),
    Tool(name="get_stock_minutes", description="查询股票分钟线；官方失败后自动降级到代理，并返回实际来源。", inputSchema={"type": "object", "properties": {"ts_code": _CODE, "freq": {"type": "string", "enum": ["1min", "5min", "15min", "30min", "60min"], "default": "5min"}, "start_date": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}, "end_date": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}}, "required": ["ts_code", "start_date", "end_date"]}),
]

server = Server("tushare-data")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "get_trade_calendar": tool_trade_calendar,
        "get_stock_daily": tool_stock_daily,
        "get_market_daily": tool_market_daily,
        "get_fund_daily": tool_fund_daily,
        "get_fund_adj": tool_fund_adj,
        "get_index_daily": tool_index_daily,
        "get_stock_basic": tool_stock_basic,
        "get_stock_minutes": tool_stock_minutes,
    }
    try:
        if name not in handlers:
            output = {"ok": False, "error": {"type": "unknown_tool", "message": name}}
        else:
            output = handlers[name](arguments or {})
    except (KeyError, ValueError) as exc:
        output = {"ok": False, "error": {"type": "invalid_request", "message": str(exc)}, "data": []}
    except Exception as exc:  # noqa: BLE001
        output = {"ok": False, "error": {"type": "internal_error", "message": str(exc)}, "data": []}
    return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, default=str))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    asyncio.run(main())
