"""产物落盘与 Markdown 渲染。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from functions.parameters import parameter_metadata
from functions.paths import SYSTEM_ID, SYSTEM_NAME, TEMPLATES_ROOT, process_dir


def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    return {"date": directory_date, "system_id": SYSTEM_ID, "artifact": kind, "generated_at": datetime.now(timezone.utc).isoformat(), "version": parameters["regulator"].get("version", "unknown"), **parameter_metadata(parameters), **payload}


def write_artifact(document: dict[str, Any], filename: str) -> str:
    path = process_dir(document["date"]) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def render_artifact(kind: str, document: dict[str, Any]) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    mapping = {"risk_facts": "risk_facts.md.j2", "sector_facts": "sector_facts.md.j2", "regulator_facts": "regulator_facts.md.j2"}
    if kind not in mapping:
        raise ValueError(f"不支持的渲染目标：{kind}")
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(mapping[kind]).render(data=document, source_path=f"交易/过程资料/{document['date']}/{SYSTEM_NAME}/{kind}.json", report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{document['date']}:{kind}").hex, updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    path = process_dir(document["date"]) / f"{kind}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {"path": str(path), "artifact": kind, "system_id": SYSTEM_ID, "date": document["date"]}
