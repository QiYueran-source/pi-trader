"""产物组装、落盘与 Markdown 渲染。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from functions.parameters import parameter_metadata
from functions.paths import PARAMS_ROOT, SYSTEM_ID, SYSTEM_NAME, SYSTEM_VERSION, TEMPLATES_ROOT, logical_process_root, process_dir, read_json

def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": directory_date,
        "system_id": SYSTEM_ID,
        "artifact": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": SYSTEM_VERSION,
        **parameter_metadata(parameters),
        **payload,
    }

def write_artifact(document: dict[str, Any], filename: str) -> str:
    path = process_dir(document["date"]) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)

def render_artifact(document: dict[str, Any], state_document: dict[str, Any] | None = None) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    runtime = read_json(PARAMS_ROOT / "runtime.json")
    if str(document.get("artifact")) != "signal_facts":
        raise ValueError(f"不支持的渲染目标：{document.get('artifact')}")
    output_name = str(runtime["report_file"])
    if state_document is None:
        candidate = process_dir(document["date"]) / str(runtime["strategy_state_file"])
        if not candidate.is_file():
            raise ValueError(f"缺少同日策略状态，无法渲染报告：{candidate}")
        state_document = read_json(candidate)
    source_path = f"{logical_process_root()}/{document['date']}/{SYSTEM_NAME}/{runtime['signal_facts_file']}"
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(f"{output_name}.j2").render(
        signal=document,
        state=state_document,
        source_path=source_path,
        report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{document['date']}:{output_name}").hex,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    path = process_dir(document["date"]) / output_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {"path": str(path), "artifact": "signal_report", "system_id": SYSTEM_ID, "date": document["date"]}
