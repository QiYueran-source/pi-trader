#!/usr/bin/env python3
"""基于Agent的ETF轮动体系（system-id: agent_etf_rotation_system）MCP 服务入口。

一个体系一个服务：`system.yml`、`params/` 与 `templates/` 都在本目录内，目录名即 `system-id`。
注册见 `.pi/mcp.json` 的 `agent-etf-rotation-system`。

口径：本体系**没有机械计算**——环境评估、候选比较、调仓判断与风控审查由 Agent 依知识库
`规则库/` 执行（`决策协议.md` 为判定入口）。本服务只提供运行契约、参数校验与复盘渲染，
不获取行情、不查询账户、不做判定、不写计划。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parents[4]
SYSTEM_ROOT = Path(__file__).resolve().parent
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "基于Agent的ETF轮动体系"
SYSTEM_VERSION = "v1"
PARAMETER_FILES = ("runtime",)
CONTENT_ROOT_NAMES = ("knowledge", "archive")
REVIEW_ARTIFACTS = ("review",)
if not (SYSTEM_ROOT / "system.yml").is_file():
    raise RuntimeError(f"体系运行定义缺失：{SYSTEM_ROOT / 'system.yml'}")


def load_env() -> None:
    env_file = REPO_ROOT / ".pi/mcp-servers/tushare/.env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    else:
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYY-MM-DD 或 YYYYMMDD：{value}") from exc
    return parsed.strftime("%Y%m%d"), parsed.strftime("%Y-%m-%d")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON 文件不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效：{path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象：{path}")
    return value


def fail(field: str, message: str) -> None:
    raise ValueError(f"字段 {field}: {message}")


def require_fields(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(field, "必须是 JSON 对象")
    missing = sorted(item for item in expected if item not in value)
    if missing:
        fail(field, f"缺少字段：{', '.join(missing)}")
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(field, "必须是非空字符串")
    return value


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        fail(field, "必须是布尔值")
    return value


def require_integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(field, f"必须是不小于 {minimum} 的整数")
    return value


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        fail(field, "必须是数组")
    return value


def require_string_list(value: Any, field: str) -> list[str]:
    for index, item in enumerate(require_list(value, field)):
        if not isinstance(item, str) or not item.strip():
            fail(f"{field}[{index}]", "必须是非空字符串")
    return list(value)


def load_parameters() -> dict[str, dict[str, Any]]:
    parameters = {name: read_json(PARAMS_ROOT / f"{name}.json") for name in PARAMETER_FILES}
    validate_parameters(parameters)
    return parameters


def validate_parameters(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(parameters) != set(PARAMETER_FILES):
        raise ValueError(f"参数文件必须为：{', '.join(PARAMETER_FILES)}")
    runtime = parameters["runtime"]
    require_fields(
        runtime,
        {
            "schema_version",
            "process_root",
            "plan_root",
            "review_root",
            "directory_date_format",
            "trading_day_only",
            "process_file",
            "review_file",
            "render_artifacts",
            "trading_calendar_lookback_days",
        },
        "runtime",
    )
    version = runtime["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        fail("runtime.schema_version", "必须是不小于 1 的整数")
    for field in ("process_root", "plan_root", "review_root", "process_file", "review_file"):
        require_string(runtime[field], f"runtime.{field}")
    if runtime["process_root"] not in {"knowledge", "knowledge/交易/过程资料"} and not str(runtime["process_root"]).startswith("knowledge/"):
        fail("runtime.process_root", "必须以 knowledge 开头（物理落盘根）")
    if runtime["directory_date_format"] != "%Y-%m-%d":
        fail("runtime.directory_date_format", "必须为 %Y-%m-%d")
    require_bool(runtime["trading_day_only"], "runtime.trading_day_only")
    require_integer(runtime["trading_calendar_lookback_days"], "runtime.trading_calendar_lookback_days", 1)
    artifacts = require_string_list(runtime["render_artifacts"], "runtime.render_artifacts")
    if tuple(artifacts) != REVIEW_ARTIFACTS:
        fail("runtime.render_artifacts", f"必须为 {list(REVIEW_ARTIFACTS)}")
    return {"valid": True, "files": list(PARAMETER_FILES)}


def parameter_metadata(parameters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    encoded = json.dumps(parameters, ensure_ascii=False, sort_keys=True).encode()
    return {
        "parameter_version": SYSTEM_VERSION,
        "parameter_hash": hashlib.sha256(encoded).hexdigest(),
        "schema_versions": {name: parameters[name]["schema_version"] for name in PARAMETER_FILES},
    }


def logical_root(field: str) -> str:
    raw = str(read_json(PARAMS_ROOT / "runtime.json")[field])
    return raw.split("/", 1)[1] if raw.startswith("knowledge/") else raw


def logical_process_root() -> str:
    return logical_root("process_root")


def process_dir(directory_date: str) -> Path:
    return REPO_ROOT / "knowledge" / logical_process_root() / directory_date / SYSTEM_NAME


def review_dir(directory_date: str) -> Path:
    return REPO_ROOT / "knowledge" / logical_root("review_root") / directory_date


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


TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(
        name="get_manifest",
        description="查看基于Agent的ETF轮动体系的运行定义、支持的操作与产物契约。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="validate_parameters",
        description="校验本体系的运行契约参数（params/runtime.json；本体系无判定阈值参数）。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="render",
        description="按运行定义模板渲染交易复盘（内容由调用端以 document 提供；dry_run 只返回全文不落盘）。",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "artifact": {"type": "string", "enum": ["review"]},
                "date": {"type": "string"},
                "document": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["system_id", "artifact", "date", "document"],
        },
    ),
]

server = Server("agent-etf-rotation-system")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": ["render"]}]}
        elif name in {"get_manifest", "validate_parameters", "render"} and args.get("system_id") != SYSTEM_ID:
            raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
        elif name == "get_manifest":
            result = {
                "system_id": SYSTEM_ID,
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "maturity": "观察体系",
                "system_root": str(SYSTEM_ROOT),
                "parameter_root": str(PARAMS_ROOT),
                "template_root": str(TEMPLATES_ROOT),
                "operations": ["render"],
                "computes_facts": False,
                "process_output": {"logical_root": f"{logical_process_root()}/{{date}}/{SYSTEM_NAME}", "physical_root": "knowledge", "artifacts": [read_json(PARAMS_ROOT / "runtime.json")["process_file"]]},
                "plan_output": f"{logical_root('plan_root')}/{{date}}/{SYSTEM_NAME}_交易计划.md",
                "review_output": f"{logical_root('review_root')}/{{date}}/{read_json(PARAMS_ROOT / 'runtime.json')['review_file']}",
                "boundaries": {"computes_facts": False, "queries_account": False, "real_order": "forbidden", "modifies_rules": False, "writes_plan": False},
            }
        elif name == "validate_parameters":
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "render":
            _, directory_date = normalize_date(args["date"])
            if args.get("artifact") != "review":
                raise ValueError(f"不支持的渲染目标：{args.get('artifact')}")
            document = normalize_review_document(args.get("document"), directory_date)
            result = render_review(document, dry_run=bool(args.get("dry_run", False)))
        else:
            raise ValueError(f"未知工具：{name}")
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


async def list_tools_legacy() -> list[Tool]:
    return list_tools_result()


async def call_tool_legacy(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    return call_tool_result(name, arguments)


if hasattr(server, "list_tools") and hasattr(server, "call_tool"):
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list_tools_result()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return call_tool_result(name, arguments)
else:
    async def list_tools(_context: Any, _params: Any) -> Any:
        from mcp.types import ListToolsResult
        return ListToolsResult(tools=TOOLS)

    async def call_tool(_context: Any, params: Any) -> Any:
        from mcp.types import CallToolResult
        content = call_tool_result(params.name, params.arguments or {})
        return CallToolResult(content=content)

    server = Server("agent-etf-rotation-system", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
