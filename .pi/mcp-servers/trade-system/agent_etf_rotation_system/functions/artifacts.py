"""复盘文档规范化与渲染落盘。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from functions.parameters import fail, load_parameters, parameter_metadata, require_fields, require_list, require_string, require_string_list
from functions.paths import SYSTEM_ID, TEMPLATES_ROOT, logical_root, review_dir

def normalize_review_document(document: Any, directory_date: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        fail("document", "必须是 JSON 对象")
    require_fields(document, {"date", "summary", "trade_summary", "holdings", "market", "improvements", "decision_refs"}, "document")
    if document["date"] != directory_date:
        fail("document.date", f"必须与 date 一致（{directory_date}）")
    normalized = {
        "date": directory_date,
        "summary": require_string(document["summary"], "document.summary"),
        "trade_summary": require_string(document["trade_summary"], "document.trade_summary"),
        "holdings": require_string_list(document["holdings"], "document.holdings"),
        "market": require_string_list(document["market"], "document.market"),
        "improvements": require_string_list(document["improvements"], "document.improvements"),
        "decision_refs": require_string_list(document["decision_refs"], "document.decision_refs"),
        "signal_check": require_string_list(document.get("signal_check", []), "document.signal_check"),
        "risk_state": "",
        "exec_review": [],
    }
    if document.get("risk_state") is not None:
        normalized["risk_state"] = require_string(document["risk_state"], "document.risk_state")
    rows = document.get("exec_review", [])
    for index, row in enumerate(require_list(rows, "document.exec_review")):
        require_fields(row, {"item", "value"}, f"document.exec_review[{index}]")
        normalized["exec_review"].append(
            {
                "item": require_string(row["item"], f"document.exec_review[{index}].item"),
                "value": require_string(row["value"], f"document.exec_review[{index}].value"),
            }
        )
    if not normalized["exec_review"]:
        fail("document.exec_review", "至少需要一行（计划动作 / 实际执行 / 偏差 / 执行评价）")
    return normalized

def render_review(document: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    parameters = load_parameters()
    runtime = parameters["runtime"]
    directory_date = document["date"]
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATES_ROOT)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    markdown = environment.get_template("review.md.j2").render(document=document)
    logical_path = f"{logical_root('review_root')}/{directory_date}/{runtime['review_file']}"
    if dry_run:
        return {"ok": True, "dry_run": True, "artifact": "review", "system_id": SYSTEM_ID, "date": directory_date, "logical_path": logical_path, "markdown": markdown}
    path = review_dir(directory_date) / str(runtime["review_file"])
    overwrote = path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {
        "ok": True,
        "artifact": "review",
        "system_id": SYSTEM_ID,
        "date": directory_date,
        "logical_path": logical_path,
        "path": str(path),
        "overwrote": overwrote,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **parameter_metadata(parameters),
    }
