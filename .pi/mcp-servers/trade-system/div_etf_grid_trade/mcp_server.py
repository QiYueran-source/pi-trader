#!/usr/bin/env python3
"""红利科创 ETF 双网格体系（system-id: div_etf_grid_trade）MCP 服务入口。

一个体系一个服务：入口、实现模块（`functions/`）、`system.yml`、`params/` 与 `templates/` 都在本目录内，
目录名即 `system-id`。注册见 `.pi/mcp.json` 的 `div-etf-grid-trade`。
本文件只做工具注册与路由，实现见 `functions/`。
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from functions.artifacts import render_artifact, write_artifact
from functions.facts import regulator_facts, risk_facts, sector_facts
from functions.parameters import load_parameters, parameter_metadata, validate_parameters
from functions.paths import (  # noqa: E402  （需先自举 sys.path）
    PARAMS_ROOT,
    SYSTEM_ID,
    SYSTEM_NAME,
    SYSTEM_ROOT,
    TEMPLATES_ROOT,
    normalize_date,
    process_dir,
    read_json,
)


def tool_calculate(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = load_parameters()
    validate_parameters(parameters)
    operation = arguments.get("operation")
    if operation == "risk_facts":
        result = risk_facts(arguments["date"], parameters, arguments.get("positions"))
    elif operation == "regulator_facts":
        result = regulator_facts(arguments["date"], parameters, arguments.get("positions"), arguments.get("human_review"), bool(arguments.get("skip_emotion", False)))
    elif operation == "sector_facts":
        result = sector_facts(arguments["date"], parameters)
    else:
        raise ValueError("operation 必须是 risk_facts、regulator_facts 或 sector_facts")
    if not arguments.get("dry_run", False):
        path = write_artifact(result, f"{operation}.json")
        result["output_path"] = path
    return result


TOOLS = [
    Tool(name="list_systems", description="列出已注册的交易体系。", inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_manifest", description="查看红利科创 ETF 双网格体系运行定义和支持的操作。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="validate_parameters", description="校验指定交易体系当前参数。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}}, "required": ["system_id"]}),
    Tool(name="calculate", description="计算双网格风险事实、调节器事实或板块事实；默认写入日期化过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "operation": {"type": "string", "enum": ["risk_facts", "regulator_facts", "sector_facts"]}, "date": {"type": "string"}, "positions": {"type": "object", "required": ["positions", "cash"]}, "human_review": {"type": "object"}, "skip_emotion": {"type": "boolean"}, "dry_run": {"type": "boolean"}}, "required": ["system_id", "operation", "date"]}),
    Tool(name="render", description="渲染已生成的双网格 JSON 事实为 Markdown；`document` 省略时按 `date` + `artifact` 读同日过程资料。", inputSchema={"type": "object", "properties": {"system_id": {"type": "string"}, "artifact": {"type": "string", "enum": ["risk_facts", "sector_facts", "regulator_facts"]}, "date": {"type": "string"}, "document": {"type": "object"}}, "required": ["system_id", "artifact", "date"]}),
]


server = Server("div-etf-grid-trade")


def list_tools_result() -> list[Tool]:
    return TOOLS


def call_tool_result(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "list_systems":
            result = {"systems": [{"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "operations": ["risk_facts", "regulator_facts", "sector_facts"]}]}
        elif name == "get_manifest":
            if args.get("system_id") != SYSTEM_ID:
                raise ValueError(f"当前 MCP 不支持体系：{args.get('system_id')}")
            result = {"system_id": SYSTEM_ID, "name": SYSTEM_NAME, "system_root": str(SYSTEM_ROOT), "parameter_root": str(PARAMS_ROOT), "template_root": str(TEMPLATES_ROOT), "operations": ["risk_facts", "regulator_facts", "sector_facts"], "writes_to": "knowledge/交易/过程资料/{date}/红利科创ETF双网格体系", "expansion": {"declaration": "regulator.scaling", "note": "每个量吃哪些倍数由 params/regulator.json#scaling 声明：买入档距=防守×资金且受档距上限；卖出档距=防守且无上限；买卖份数=防守份数倍数并按 100 份向下取整", "multiplier_sources": {"defense": "regulator.defense_levels[].step_multiplier / shares_multiplier", "capital": "regulator.capital_guard.tiers[].step_multiplier"}}, "defense_levels": {"levels": sorted(name for name, spec in load_parameters()["regulator"]["defense_levels"].items() if isinstance(spec, dict)), "scope": "体系级 human_review.level，可用 human_review.per_leg 按腿覆盖（缺省沿用体系档）", "output_fields": ["defense.requested_level", "defense.requested_per_leg", "defense.effective_levels", "legs[].defense_level"]}, "reserve_shares": "regulator.reserve_shares（enabled=true 时持仓 ≤ 保底下限即停卖该腿，产物给 sell_disabled_reason=reserve_floor）", "leg_effective_fields": ["buy_step_ratio", "buy_raw_step_ratio", "step_cap", "capped", "buy_shares", "buy_enabled", "sell_step_ratio", "sell_raw_step_ratio", "sell_shares", "sell_enabled", "sell_disabled_reason", "reserve_floor"]}
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
            document = args.get("document")
            if document is None:
                document = read_json(process_dir(directory_date) / f"{args['artifact']}.json")
            if not isinstance(document, dict):
                raise ValueError("document 必须是 JSON 对象")
            if document.get("date") != directory_date:
                raise ValueError("document.date 与 date 不一致")
            result = render_artifact(args["artifact"], document)
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

    server = Server(
        "div-etf-grid-trade",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
