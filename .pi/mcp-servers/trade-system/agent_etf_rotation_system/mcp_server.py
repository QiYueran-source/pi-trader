#!/usr/bin/env python3
"""基于Agent的ETF轮动体系（system-id: agent_etf_rotation_system）MCP 服务入口。

一个体系一个服务：入口只做工具注册与路由，实现见 `functions/`；`params/` 与 `templates/` 都在本目录内，
目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `agent-etf-rotation-system`。

口径：本体系**没有机械计算**——环境评估、候选比较、调仓判断与风控审查由 Agent 依知识库
`规则库/` 执行（`决策协议.md` 为判定入口）。本服务提供运行契约、参数校验、交易日判断与复盘渲染，
不查询账户、不做交易判定、不写计划。
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

from functions.artifacts import normalize_review_document, render_review  # noqa: E402
from functions.market import fetch_trade_calendar, get_client  # noqa: E402
from functions.parameters import load_parameters, parameter_metadata, validate_parameters  # noqa: E402
from functions.paths import PARAMS_ROOT, SYSTEM_ID, SYSTEM_NAME, SYSTEM_ROOT, SYSTEM_VERSION, TEMPLATES_ROOT, logical_process_root, logical_root, normalize_date, read_json  # noqa: E402

TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(
        name="get_manifest",
        description="查看基于Agent的ETF轮动体系的运行定义、支持的操作与产物契约。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="validate_parameters",
        description="校验本体系的运行契约参数（params/runtime.json 路径与文件名；params/universe.json 候选池与费率；不含判定阈值）。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="is_trading_day",
        description="判断指定日期（默认今天）是否为交易日；数据源 tushare.trade_cal（SSE），本服务自带判断，不依赖其它 MCP。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "date": {"type": "string"}}, "required": ["system_id"]},
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
        elif name in {"get_manifest", "validate_parameters", "is_trading_day", "render"} and args.get("system_id") != SYSTEM_ID:
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
                "universe": {
                    "cash_substitute": read_json(PARAMS_ROOT / "universe.json")["cash_substitute"],
                    "instruments": read_json(PARAMS_ROOT / "universe.json")["instruments"],
                },
                "process_output": {"logical_root": f"{logical_process_root()}/{{date}}/{SYSTEM_NAME}", "physical_root": "knowledge", "artifacts": [read_json(PARAMS_ROOT / "runtime.json")["process_file"]]},
                "plan_output": f"{logical_root('plan_root')}/{{date}}/{SYSTEM_NAME}_交易计划.md",
                "review_output": f"{logical_root('review_root')}/{{date}}/{read_json(PARAMS_ROOT / 'runtime.json')['review_file']}",
                "boundaries": {"computes_facts": False, "queries_account": False, "real_order": "forbidden", "modifies_rules": False, "writes_plan": False},
            }
        elif name == "validate_parameters":
            parameters = load_parameters()
            result = {"system_id": SYSTEM_ID, **validate_parameters(parameters), **parameter_metadata(parameters)}
        elif name == "is_trading_day":
            api_date, directory_date = normalize_date(args.get("date"))
            calendar = fetch_trade_calendar(get_client(), api_date)
            result = {
                "ok": True,
                "system_id": SYSTEM_ID,
                "date": directory_date,
                "is_open": calendar["is_open"],
                "pretrade_date": calendar["pretrade_date"],
                "source": "tushare.trade_cal/SSE",
            }
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
