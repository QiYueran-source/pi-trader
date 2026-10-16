#!/usr/bin/env python3
"""严格将指定日期的红利科创 ETF 双网格过程资料渲染为 Markdown。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, TemplateNotFound

from runtime_support import SYSTEM_DIR, artifact_path, normalize_date

RENDER_TARGETS = {
    "grid_parameters": ("grid_parameters.json", "grid_parameters.md.j2", "grid_parameters.md"),
    "risk_facts": ("risk_facts.json", "risk_facts.md.j2", "risk_facts.md"),
    "sector_facts": ("sector_facts.json", "sector_facts.md.j2", "sector_facts.md"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="红利科创 ETF 双网格过程资料渲染")
    parser.add_argument("--template", required=True, choices=sorted(RENDER_TARGETS), help="渲染目标")
    parser.add_argument("--date", required=True, help="过程资料日期，YYYY-MM-DD 或 YYYYMMDD")
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, path)


def main() -> None:
    args = parse_args()
    _, directory_date = normalize_date(args.date)
    input_filename, template_filename, output_filename = RENDER_TARGETS[args.template]
    input_path = artifact_path(directory_date, input_filename)
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"渲染输入不存在: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"渲染输入 JSON 无效: {input_path}") from exc

    environment = Environment(
        loader=FileSystemLoader(SYSTEM_DIR / "templates"),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    try:
        markdown = environment.get_template(template_filename).render(
            data=document,
            source_path=str(input_path),
            report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:div_etf_grid_trade:{directory_date}:{args.template}").hex,
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except TemplateNotFound as exc:
        raise ValueError(f"渲染模板不存在: {template_filename}") from exc
    except TemplateError as exc:
        raise ValueError(f"模板渲染失败: {exc}") from exc

    output_path = artifact_path(directory_date, output_filename)
    write_text(output_path, markdown)
    print(output_path)


if __name__ == "__main__":
    main()