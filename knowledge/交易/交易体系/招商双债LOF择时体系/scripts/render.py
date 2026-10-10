#!/opt/hermes/.venv/bin/python3
"""严格渲染招商双债 LOF 的当日信号报告。"""

from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, TemplateNotFound

from runtime_support import SYSTEM_DIR, SYSTEM_ID, load_parameters, normalize_date, process_dir, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="招商双债 LOF 信号报告渲染")
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
    _, target_date = normalize_date(args.date)
    runtime = load_parameters()["runtime"]
    directory = process_dir(target_date)
    signal_path = directory / runtime["signal_facts_file"]
    state_path = directory / runtime["strategy_state_file"]
    signal = read_json(signal_path)
    state = read_json(state_path)
    if signal.get("date") != target_date or state.get("date") != target_date:
        raise ValueError("信号或策略状态日期与渲染日期不一致")

    environment = Environment(
        loader=FileSystemLoader(SYSTEM_DIR / "templates"),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    try:
        markdown = environment.get_template("signal_report.md.j2").render(
            signal=signal,
            state=state,
            report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"hermes:{SYSTEM_ID}:{target_date}").hex,
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except TemplateNotFound as exc:
        raise ValueError("信号报告模板不存在") from exc
    except TemplateError as exc:
        raise ValueError(f"信号报告渲染失败: {exc}") from exc

    output_path = directory / runtime["report_file"]
    write_text(output_path, markdown)
    print(output_path)


if __name__ == "__main__":
    main()