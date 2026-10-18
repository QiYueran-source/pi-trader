#!/usr/bin/env python3
"""招商双债LOF择时体系（system-id: zslof_timing_trade）MCP 服务入口。

一个体系一个服务：入口只做工具注册与路由，实现见 `functions/`；`system.yml`、`params/` 与
`templates/` 都在本目录内，目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `zslof-timing-trade`。

口径：收盘确认的机械波段择时；状态从过程资料「最近先前过程日」读取
（`knowledge/` 优先、`archive/` 兜底），推进与判定按体系 `择时参数.md` 的协议。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402（自举后才能导入 functions）

from functions.artifacts import render_artifact, write_artifact  # noqa: E402
from functions.parameters import load_parameters, parameter_metadata, validate_parameters  # noqa: E402
from functions.paths import PARAMS_ROOT, SYSTEM_ID, SYSTEM_NAME, SYSTEM_ROOT, SYSTEM_VERSION, TEMPLATES_ROOT, logical_process_root, normalize_date, process_dir, read_json  # noqa: E402
from functions.signals import calculate_signal, replay_check  # noqa: E402


def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    operation = arguments.get("operation")
    if operation == "signal":
        document = calculate_signal(arguments["date"], parameters)
    elif operation == "replay_check":
        return replay_check(arguments["date"], parameters)
    else:
        raise ValueError("operation 必须是 signal 或 replay_check")
    if bool(arguments.get("dry_run", False)):
        return document
    paths = {
        "strategy_state": write_artifact(document["strategy_state"], str(parameters["runtime"]["strategy_state_file"])),
        "signal_facts": write_artifact(document["signal_facts"], str(parameters["runtime"]["signal_facts_file"])),
    }
    return {**document, "output_paths": paths}


TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_manifest", description="查看招商双债LOF择时体系运行定义和支持的操作。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="validate_parameters", description="校验本体系当前参数。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="calculate", description="计算当日收盘信号与理论状态（signal），或从锚日重放校验（replay_check）；signal 默认写入过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "operation": {"type": "string", "enum": ["signal", "replay_check"]}, "date": {"type": "string"}, "dry_run": {"type": "boolean"}}, "required": ["system_id", "operation", "date"]}),
    Tool(name="render", description="把当日信号事实渲染为可读信号报告。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "artifact": {"type": "string", "enum": ["signal_report"]}, "date": {"type": "string"}, "document": {"type": "object"}, "state": {"type": "object"}}, "required": ["system_id", "artifact", "date"]}),
]


server = Server("zslof-timing-trade")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": ["signal", "replay_check"]}]}
        elif name == "get_manifest":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = {
                "system_id": SYSTEM_ID,
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "system_root": str(SYSTEM_ROOT),
                "parameter_root": str(PARAMS_ROOT),
                "template_root": str(TEMPLATES_ROOT),
                "operations": ["signal", "replay_check"],
                "writes_to": f"knowledge/{logical_process_root()}/{{date}}/{SYSTEM_NAME}",
                "boundaries": {"queries_account": False, "real_order": "forbidden", "writes_plan": False},
            }
        elif name == "validate_parameters":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "calculate":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = tool_calculate(args)
        elif name == "render":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            _, directory_date = normalize_date(args["date"])
            if args.get("artifact") != "signal_report":
                raise ValueError(f"不支持的渲染目标：{args.get('artifact')}")
            document = args.get("document")
            if document is None:
                runtime = read_json(PARAMS_ROOT / "runtime.json")
                document = read_json(process_dir(directory_date) / str(runtime["signal_facts_file"]))
            if not isinstance(document, dict):
                raise ValueError("document 必须是 JSON 对象")
            if document.get("date") != directory_date:
                raise ValueError("document.date 与 date 不一致")
            result = render_artifact(document, args.get("state"))
        else:
            raise ValueError(f"未知工具：{name}")
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


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

    server = Server("zslof-timing-trade", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
