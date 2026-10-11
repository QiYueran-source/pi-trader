#!/usr/bin/env python3
"""基金与 ETF 数据 CLI。"""

from __future__ import annotations

import click

from common import create_client, emit_frame, execute_query, output_options, resolve_date_range


@click.group()
def cli() -> None:
    """查询基金列表、ETF 行情、净值和基金经理。"""


@cli.command("list")
@click.option(
    "--market",
    type=click.Choice(("E", "O"), case_sensitive=False),
    default="E",
    show_default=True,
    help="市场类型：E 场内、O 场外",
)
@click.option("--status", default="L", show_default=True, help="基金状态")
@output_options
def list_funds(market, status, fields, output_format, output, limit) -> None:
    """获取基金基础列表。"""
    client = create_client()
    params = {"market": market, "status": status}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.fund_basic(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


def query_by_date_range(endpoint, code, start_date, end_date, fields):
    start_date, end_date = resolve_date_range(start_date, end_date)
    params = {"ts_code": code, "start_date": start_date, "end_date": end_date}
    if fields:
        params["fields"] = fields
    return execute_query(lambda: endpoint(**params))


@cli.command("daily")
@click.option("--code", "-c", required=True, help="完整基金代码，例如 588000.SH")
@click.option("--start-date", help="开始日期，YYYYMMDD 或 YYYY-MM-DD")
@click.option("--end-date", help="结束日期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def daily(code, start_date, end_date, fields, output_format, output, limit) -> None:
    """获取 ETF 或场内基金日线行情。"""
    client = create_client()
    data = query_by_date_range(client.fund_daily, code, start_date, end_date, fields)
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("nav")
@click.option("--code", "-c", required=True, help="完整基金代码，例如 110011.OF")
@click.option("--start-date", help="开始日期，YYYYMMDD 或 YYYY-MM-DD")
@click.option("--end-date", help="结束日期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def nav(code, start_date, end_date, fields, output_format, output, limit) -> None:
    """获取基金净值。"""
    client = create_client()
    data = query_by_date_range(client.fund_nav, code, start_date, end_date, fields)
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("manager")
@click.option("--code", "-c", help="完整基金代码")
@click.option("--name", help="基金经理姓名")
@output_options
def manager(code, name, fields, output_format, output, limit) -> None:
    """获取基金经理记录。"""
    client = create_client()
    params = {}
    if code:
        params["ts_code"] = code
    if name:
        params["name"] = name
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.fund_manager(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


if __name__ == "__main__":
    cli()