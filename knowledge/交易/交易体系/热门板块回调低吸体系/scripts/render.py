#!/usr/bin/env python3
"""将指定日期的过程资料 JSON 严格渲染为 Markdown。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, TemplateNotFound

from runtime_support import SYSTEM_DIR, normalize_date, process_dir

SYSTEM_ID = "hot_sector_pullback_system"

RENDER_TARGETS = {
    "candidates": {
        "input_filename": "full_market_candidate.json",
        "template_filename": "candidates.md.j2",
        "output_filename": "candidates.md",
    },
    "sector_heat": {
        "input_filename": "sector_heat.json",
        "template_filename": "sector_heat.md.j2",
        "output_filename": "sector_heat.md",
    },
    "entry_signal": {
        "input_filename": "entry_signal.json",
        "template_filename": "entry_signal.md.j2",
        "output_filename": "entry_signal.md",
    },
    "risk_signal": {
        "input_filename": "risk_signal.json",
        "template_filename": "risk_signal.md.j2",
        "output_filename": "risk_signal.md",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="过程资料 JSON → Markdown")
    parser.add_argument(
        "--template",
        "--templates",
        dest="template",
        required=True,
        choices=sorted(RENDER_TARGETS),
        help="渲染目标",
    )
    parser.add_argument("--date", help="过程资料日期，支持 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--input", help="调试模式的 JSON 输入路径")
    parser.add_argument("--output", help="调试模式的 Markdown 输出路径")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    has_input = args.input is not None
    has_output = args.output is not None

    if has_input != has_output:
        raise ValueError("调试模式下 --input 与 --output 必须成对提供")
    if has_input:
        return Path(args.input), Path(args.output)
    if args.date is None:
        raise ValueError("标准模式必须提供 --date")

    api_date, _ = normalize_date(args.date)
    target = RENDER_TARGETS[args.template]
    directory = process_dir(api_date)
    return directory / target["input_filename"], directory / target["output_filename"]


def load_document(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"渲染输入不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"渲染输入 JSON 无效 {path}: {exc.msg}") from exc

    if not isinstance(document, dict):
        raise ValueError(f"渲染输入必须是 JSON 对象: {path}")
    return document


def render_document(template_name: str, document: dict, source_path: Path, report_uuid: str) -> str:
    environment = Environment(
        loader=FileSystemLoader(SYSTEM_DIR / "templates"),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    try:
        template = environment.get_template(template_name)
        return template.render(
            data=document,
            source_path=str(source_path),
            report_uuid=report_uuid,
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except TemplateNotFound as exc:
        raise ValueError(f"渲染模板不存在: {template_name}") from exc
    except TemplateError as exc:
        raise ValueError(f"模板渲染失败 {template_name}: {exc}") from exc


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, path)


def main() -> None:
    args = parse_args()
    input_path, output_path = resolve_paths(args)
    target = RENDER_TARGETS[args.template]
    document = load_document(input_path)
    markdown = render_document(
        target["template_filename"],
        document,
        input_path,
        uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{document['date']}:{args.template}").hex,
    )
    write_atomically(output_path, markdown)
    print(output_path)


if __name__ == "__main__":
    main()