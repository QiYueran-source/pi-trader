#!/usr/bin/env python3
"""热门板块回调低吸体系（system-id: hot_sector_pullback_system）MCP 服务入口。

一个体系一个服务：入口只做工具注册与路由，实现见 `functions/`；`params/` 与 `templates/` 都在本目录内，
目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `hot-sector-pullback-system`。
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

from functions.artifacts import RENDER_TARGETS, artifact, render_artifact  # noqa: E402
from functions.parameters import fail, load_parameters, parameter_metadata, validate_parameters  # noqa: E402
from functions.market import fetch_trade_calendar, get_client  # noqa: E402
from functions.paths import BENCHMARK_INDEX, OPERATIONS, PARAMS_ROOT, SYSTEM_ID, SYSTEM_NAME, SYSTEM_ROOT, SYSTEM_VERSION, TEMPLATES_ROOT, logical_root, normalize_date, read_json  # noqa: E402
from functions.signals import op_entry_signal, op_risk_signal  # noqa: E402
from functions.selection import op_select_candidates  # noqa: E402
from functions.sector_heat import op_sector_heat  # noqa: E402

def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    operation = arguments.get("operation")
    if operation not in OPERATIONS:
        raise ValueError(f"operation 必须是 {' / '.join(OPERATIONS)}")
    target_api_date, directory_date = normalize_date(arguments.get("date"))
    dry_run = bool(arguments.get("dry_run", False))
    raw_industries = arguments.get("industries")
    industries = None
    if raw_industries is not None:
        if not isinstance(raw_industries, list) or not all(isinstance(item, str) and item.strip() for item in raw_industries):
            fail("industries", "必须是字符串数组")
        industries = [item.strip() for item in raw_industries]
    if operation == "select_candidates":
        return op_select_candidates(target_api_date, directory_date, industries, parameters, dry_run)
    if operation == "sector_heat":
        return op_sector_heat(target_api_date, directory_date, parameters, dry_run)
    if operation == "entry_signal":
        return op_entry_signal(target_api_date, directory_date, industries, parameters, dry_run)
    positions = arguments.get("positions")
    if positions is not None and not isinstance(positions, dict):
        fail("positions", "必须是 JSON 对象（代码 → 买入价）")
    return op_risk_signal(target_api_date, directory_date, positions, parameters, dry_run)


TOOLS = [
    Tool(name="list_systems", description="列出本服务实现的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(
        name="get_manifest",
        description="查看热门板块回调低吸体系的运行定义、支持的操作与产物契约。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="validate_parameters",
        description="校验本体系参数（selection / sector_heat / entry / risk / runtime）。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="is_trading_day",
        description="判断指定日期（默认今天）是否为交易日；数据源 tushare.trade_cal（SSE），本服务自带判断，不依赖其它 MCP。",
        inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "date": {"type": "string"}}, "required": ["system_id"]},
    ),
    Tool(
        name="calculate",
        description="计算候选（select_candidates）、板块热度与全市场板块环境（sector_heat）、建仓信号（entry_signal）或持仓风控（risk_signal）；dry_run 只返回结果不落盘。",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "operation": {"type": "string", "enum": list(OPERATIONS)},
                "date": {"type": "string"},
                "industries": {"type": "array", "items": {"type": "string"}},
                "positions": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["system_id", "operation", "date"],
        },
    ),
    Tool(
        name="render",
        description="把当日过程资料渲染为 Markdown（candidates / sector_heat / entry_signal / risk_signal）。",
        inputSchema={
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "artifact": {"type": "string", "enum": list(RENDER_TARGETS)},
                "date": {"type": "string"},
                "document": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["system_id", "artifact", "date"],
        },
    ),
]


server = Server("hot-sector-pullback-system")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": list(OPERATIONS)}]}
        elif name in {"get_manifest", "validate_parameters", "is_trading_day", "calculate", "render"} and args.get("system_id") != SYSTEM_ID:
            raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
        elif name == "get_manifest":
            runtime = read_json(PARAMS_ROOT / "runtime.json")
            result = {
                "system_id": SYSTEM_ID,
                "name": SYSTEM_NAME,
                "version": SYSTEM_VERSION,
                "maturity": "观察体系",
                "system_root": str(SYSTEM_ROOT),
                "parameter_root": str(PARAMS_ROOT),
                "template_root": str(TEMPLATES_ROOT),
                "operations": list(OPERATIONS),
                "computes_facts": True,
                "process_output": {
                    "logical_root": f"{logical_root('process_root')}/{{date}}/{SYSTEM_NAME}",
                    "physical_root": "knowledge",
                    "artifacts": [
                        "full_market_candidate.json",
                        "hottest_industry_candidate.json",
                        "sector_environment.json",
                        "sector_heat.json",
                        "entry_signal.json",
                        "risk_signal.json",
                        "positions.json",
                        "state.json",
                        "prudent_tags.json",
                    ],
                },
                "plan_output": f"{logical_root('plan_root')}/{{date}}/{SYSTEM_NAME}_交易计划.md",
                "review_output": f"{logical_root('review_root')}/{{date}}/{SYSTEM_NAME}_复盘.md",
                "fact_sources": {
                    "daily": "tushare pro_api daily（全市场按 trade_date）",
                    "index": f"tushare index_daily（{BENCHMARK_INDEX}）",
                    "minutes": "tushare stk_mins（5min 开盘段，唯一通道；原 promax 兜底已删除）",
                },
                "boundaries": {
                    "computes_facts": True,
                    "queries_account": False,
                    "real_order": "forbidden",
                    "modifies_parameters": False,
                    "writes_plan": False,
                    "cross_system_reads": "none",
                },
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
        elif name == "calculate":
            result = tool_calculate(args)
        elif name == "render":
            artifact = args.get("artifact")
            if artifact not in RENDER_TARGETS:
                raise ValueError(f"不支持的渲染目标：{artifact}")
            _, directory_date = normalize_date(args.get("date"))
            document = args.get("document")
            if document is not None and not isinstance(document, dict):
                fail("document", "必须是 JSON 对象")
            result = render_artifact(directory_date, artifact, document, bool(args.get("dry_run", False)))
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

    server = Server("hot-sector-pullback-system", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
