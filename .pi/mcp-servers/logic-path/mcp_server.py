#!/usr/bin/env python3
"""动态知识逻辑路径 MCP 服务。

逻辑路径不包含 knowledge/ 或 archive/ 前缀；服务在两棵物理树中解析同一个逻辑路径，
并拒绝路径穿越、物理前缀和重复文件。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", "/pi-trader/knowledge")).resolve()
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/pi-trader/archive")).resolve()


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_logical_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("logical_path 必须是非空字符串")
    logical = value.strip()
    if "\\" in logical:
        raise ValueError("logical_path 必须使用 POSIX 路径分隔符")
    if logical.startswith(("/", "knowledge/", "archive/")):
        raise ValueError("logical_path 不得以 /、knowledge/ 或 archive/ 开头")
    parts = logical.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("logical_path 不得包含空路径段、`.` 或 `..`")
    if any("\x00" in part for part in parts):
        raise ValueError("logical_path 不得包含 NUL 字符")
    return logical


def candidate(root: Path, logical: str) -> Path:
    path = (root / logical).resolve()
    if not _inside(path, root):
        raise ValueError("logical_path 超出受控根目录")
    return path


def resolve_path(logical_path: Any, require_file: bool = True) -> dict[str, Any]:
    logical = validate_logical_path(logical_path)
    locations: list[dict[str, str]] = []
    for name, root in (("knowledge", KNOWLEDGE_ROOT), ("archive", ARCHIVE_ROOT)):
        path = candidate(root, logical)
        exists = path.is_file() if require_file else path.exists()
        if exists:
            locations.append({
                "location": name,
                "physical_path": f"{name}/{logical}",
                "absolute_path": str(path),
            })

    if len(locations) == 0:
        status = "not_found"
    elif len(locations) == 1:
        status = "unique"
    else:
        status = "duplicate"

    result: dict[str, Any] = {
        "ok": status == "unique",
        "logical_path": logical,
        "status": status,
        "locations": locations,
    }
    if status == "unique":
        result.update(locations[0])
    return result


def validate_path(logical_path: Any, require_exists: bool = True) -> dict[str, Any]:
    logical = validate_logical_path(logical_path)
    result: dict[str, Any] = {
        "ok": True,
        "logical_path": logical,
        "format": "valid",
    }
    if require_exists:
        resolved = resolve_path(logical)
        result["status"] = resolved["status"]
        result["locations"] = resolved["locations"]
        result["ok"] = resolved["status"] == "unique"
        if result["ok"]:
            result.update({
                "location": resolved["location"],
                "physical_path": resolved["physical_path"],
            })
    return result


def audit_paths(paths: Any) -> dict[str, Any]:
    if not isinstance(paths, list):
        raise ValueError("logical_paths 必须是数组")
    results: list[dict[str, Any]] = []
    counts = {"unique": 0, "not_found": 0, "duplicate": 0, "invalid": 0}
    for value in paths:
        try:
            result = resolve_path(value)
        except ValueError as exc:
            result = {"ok": False, "logical_path": value, "status": "invalid", "error": str(exc), "locations": []}
        counts[result["status"]] += 1
        results.append(result)
    return {"ok": counts["not_found"] == 0 and counts["duplicate"] == 0 and counts["invalid"] == 0,
            "total": len(results), "counts": counts, "results": results}


TOOLS = [
    Tool(
        name="logic_path_resolve",
        description="解析动态知识逻辑路径，同时检查 knowledge 和 archive，返回 unique、not_found 或 duplicate。",
        inputSchema={
            "type": "object",
            "properties": {"logical_path": {"type": "string"}},
            "required": ["logical_path"],
        },
    ),
    Tool(
        name="logic_path_validate",
        description="校验动态知识逻辑路径格式，并可要求其唯一解析到一个文件。",
        inputSchema={
            "type": "object",
            "properties": {
                "logical_path": {"type": "string"},
                "require_exists": {"type": "boolean", "default": True},
            },
            "required": ["logical_path"],
        },
    ),
    Tool(
        name="logic_path_audit",
        description="批量审计动态知识逻辑路径的格式和双头解析结果。",
        inputSchema={
            "type": "object",
            "properties": {
                "logical_paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["logical_paths"],
        },
    ),
]

server = Server("logic-path")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "logic_path_resolve":
            result = resolve_path(args["logical_path"])
        elif name == "logic_path_validate":
            result = validate_path(args["logical_path"], bool(args.get("require_exists", True)))
        elif name == "logic_path_audit":
            result = audit_paths(args["logical_paths"])
        else:
            raise ValueError(f"未知工具：{name}")
    except (KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "error": {"type": "invalid_request", "message": str(exc)}}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": {"type": "internal_error", "message": str(exc)}}
    return [TextContent(type="text", text=dump(result))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
