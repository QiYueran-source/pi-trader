#!/usr/bin/env python3
"""股票基础数据 CLI。"""

from __future__ import annotations

import click

from common import (
    create_client,
    emit_frame,
    execute_query,
    normalize_date,
    output_options,
    resolve_date_range,
)


@click.group()
def cli() -> None:
    """查询股票列表、日线行情和财务指标。"""


@cli.command("list")
@click.option("--exchange", default="", help="交易所代码：SSE、SZSE、BSE；默认全部")
@click.option(
    "--list-status",
    type=click.Choice(("L", "D", "P"), case_sensitive=False),
    default="L",
    show_default=True,
    help="上市状态：上市、退市、暂停上市",
)
@output_options
def list_stocks(exchange, list_status, fields, output_format, output, limit) -> None:
    """获取股票基础列表。"""
    client = create_client()
    params = {"exchange": exchange, "list_status": list_status}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.stock_basic(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("daily")
@click.option("--code", "-c", required=True, help="完整股票代码，例如 000001.SZ")
@click.option("--start-date", help="开始日期，YYYYMMDD 或 YYYY-MM-DD")
@click.option("--end-date", help="结束日期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def daily(code, start_date, end_date, fields, output_format, output, limit) -> None:
    """获取股票日线行情。"""
    start_date, end_date = resolve_date_range(start_date, end_date)
    client = create_client()
    params = {"ts_code": code, "start_date": start_date, "end_date": end_date}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.daily(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("financial")
@click.option("--code", "-c", required=True, help="完整股票代码，例如 000001.SZ")
@click.option("--period", help="报告期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def financial(code, period, fields, output_format, output, limit) -> None:
    """获取股票财务指标。"""
    client = create_client()
    params = {"ts_code": code}
    normalized_period = normalize_date(period, "period")
    if normalized_period:
        params["period"] = normalized_period
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.fina_indicator(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


if __name__ == "__main__":
    cli()