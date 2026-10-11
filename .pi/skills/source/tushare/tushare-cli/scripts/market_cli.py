#!/usr/bin/env python3
"""市场分类与跨境资金 CLI。"""

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
    """查询行业、概念板块和北向资金。"""


@cli.command("sectors")
@click.option(
    "--level",
    type=click.Choice(("L1", "L2", "L3"), case_sensitive=False),
    default="L1",
    show_default=True,
)
@click.option("--source", default="SW2021", show_default=True, help="行业分类来源")
@output_options
def sectors(level, source, fields, output_format, output, limit) -> None:
    """获取行业分类。"""
    client = create_client()
    params = {"level": level, "src": source}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.index_classify(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("sector-members")
@click.option("--code", "-c", required=True, help="行业指数代码")
@output_options
def sector_members(code, fields, output_format, output, limit) -> None:
    """获取行业指数成分股。"""
    client = create_client()
    params = {"index_code": code}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.index_member(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


@cli.command("concepts")
@click.option("--trade-date", required=True, help="交易日期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def concepts(trade_date, fields, output_format, output, limit) -> None:
    """获取指定交易日的概念板块列表。"""
    client = create_client()
    params = {"trade_date": normalize_date(trade_date, "trade-date")}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.concept(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)



@cli.command("northbound")
@click.option("--start-date", help="开始日期，YYYYMMDD 或 YYYY-MM-DD")
@click.option("--end-date", help="结束日期，YYYYMMDD 或 YYYY-MM-DD")
@output_options
def northbound(start_date, end_date, fields, output_format, output, limit) -> None:
    """获取沪深港通资金流向。"""
    start_date, end_date = resolve_date_range(start_date, end_date)
    client = create_client()
    params = {"start_date": start_date, "end_date": end_date}
    if fields:
        params["fields"] = fields
    data = execute_query(lambda: client.moneyflow_hsgt(**params))
    emit_frame(data, output_format=output_format, output=output, limit=limit)


if __name__ == "__main__":
    cli()