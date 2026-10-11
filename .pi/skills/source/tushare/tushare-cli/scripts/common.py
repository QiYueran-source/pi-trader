#!/usr/bin/env python3
"""Tushare CLI 共享环境、日期与输出能力。"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, TypeVar

import click
import pandas as pd
import tushare as ts

SKILL_DIR = Path(__file__).resolve().parent.parent
T = TypeVar("T")


def load_skill_env() -> None:
    env_path = SKILL_DIR / ".env"
    if not env_path.exists():
        raise click.ClickException(f"缺少环境文件：{env_path}")

    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def create_client():
    load_skill_env()
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token or token == "your_tushare_token":
        raise click.ClickException("请在技能根目录 .env 中配置有效的 TUSHARE_TOKEN")
    return ts.pro_api(token)


def normalize_date(value: str | None, option_name: str) -> str | None:
    if value is None:
        return None

    for date_format in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).strftime("%Y%m%d")
        except ValueError:
            continue
    raise click.BadParameter(
        "日期格式必须是 YYYYMMDD 或 YYYY-MM-DD",
        param_hint=f"--{option_name}",
    )


def resolve_date_range(
    start_date: str | None,
    end_date: str | None,
    *,
    default_days: int = 30,
) -> tuple[str, str]:
    normalized_end = normalize_date(end_date, "end-date") or date.today().strftime("%Y%m%d")
    normalized_start = normalize_date(start_date, "start-date")
    if normalized_start is None:
        end_value = datetime.strptime(normalized_end, "%Y%m%d").date()
        normalized_start = (end_value - timedelta(days=default_days)).strftime("%Y%m%d")
    if normalized_start > normalized_end:
        raise click.UsageError("--start-date 不能晚于 --end-date")
    return normalized_start, normalized_end


def execute_query(query: Callable[[], T]) -> T:
    try:
        return query()
    except click.ClickException:
        raise
    except Exception as error:
        raise click.ClickException(f"Tushare 查询失败：{error}") from error


def emit_frame(
    data: pd.DataFrame,
    *,
    output_format: str,
    output: Path | None,
    limit: int | None,
) -> None:
    if limit is not None:
        data = data.head(limit)

    if output_format == "json":
        content = data.to_json(orient="records", force_ascii=False, indent=2)
    elif output_format == "csv":
        content = data.to_csv(index=False)
    else:
        content = data.to_string(index=False)

    if output is None:
        click.echo(content)
        return

    output.write_text(content + ("\n" if content else ""), encoding="utf-8")
    click.echo(f"已写入 {len(data)} 行：{output}", err=True)


def output_options(function: Callable[..., T]) -> Callable[..., T]:
    options = (
        click.option("--fields", help="逗号分隔的 Tushare 返回字段"),
        click.option(
            "--format",
            "output_format",
            type=click.Choice(("table", "json", "csv"), case_sensitive=False),
            default="table",
            show_default=True,
        ),
        click.option("--output", type=click.Path(path_type=Path, dir_okay=False)),
        click.option("--limit", type=click.IntRange(min=1)),
    )
    for option in reversed(options):
        function = option(function)
    return function