"""产物组装、落盘与 Markdown 渲染。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from functions.parameters import fail, parameter_metadata
from functions.paths import SYSTEM_ID, TEMPLATES_ROOT, load_process_document, logical_process_path, process_dir

def artifact(kind: str, directory_date: str, parameters: dict[str, dict[str, Any]], note: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": directory_date,
        "artifact": kind,
        "system_id": SYSTEM_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        **parameter_metadata(parameters),
        **payload,
    }

def render_artifact(directory_date: str, kind: str, document: dict[str, Any] | None, dry_run: bool) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    input_name, template_name, output_name = RENDER_TARGETS[kind]
    if document is None:
        document = load_process_document(directory_date, input_name)
    if not isinstance(document, dict):
        fail("document", "必须是 JSON 对象")
    if str(document.get("date")) != directory_date:
        fail("document.date", f"必须与 date 一致（{directory_date}）")
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES_ROOT)), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    markdown = environment.get_template(template_name).render(
        data=document,
        source_path=logical_process_path(directory_date, input_name),
        report_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"pi-trader:{SYSTEM_ID}:{directory_date}:{kind}").hex,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    logical_path = logical_process_path(directory_date, output_name)
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": kind, "date": directory_date, "logical_path": logical_path, "markdown": markdown}
    path = process_dir(directory_date, create=True) / output_name
    overwrote = path.is_file()
    path.write_text(markdown, encoding="utf-8")
    return {"ok": True, "artifact": kind, "date": directory_date, "logical_path": logical_path, "path": str(path), "overwrote": overwrote}

RENDER_TARGETS = {
    "candidates": ("full_market_candidate.json", "candidates.md.j2", "candidates.md"),
    "sector_heat": ("sector_heat.json", "sector_heat.md.j2", "sector_heat.md"),
    "entry_signal": ("entry_signal.json", "entry_signal.md.j2", "entry_signal.md"),
    "risk_signal": ("risk_signal.json", "risk_signal.md.j2", "risk_signal.md"),
}
