#!/usr/bin/env python3
"""草稿箱管理 MCP。"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

SCRATCH_ROOT = Path(os.getenv("SCRATCH_ROOT", "/pi-trader/.scratch-space")).resolve()


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def safe_path(relative: str) -> Path:
    path = (SCRATCH_ROOT / relative).resolve()
    if path != SCRATCH_ROOT and SCRATCH_ROOT not in path.parents:
        raise ValueError("路径必须位于 .scratch-space 内")
    return path


def stale(before: str) -> list[dict[str, Any]]:
    cutoff = datetime.fromisoformat(before)
    result = []
    if not SCRATCH_ROOT.is_dir():
        return result
    for path in SCRATCH_ROOT.rglob("*"):
        if not path.is_file() or path.name == ".gitignore":
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified < cutoff:
            result.append({"path": path.relative_to(SCRATCH_ROOT).as_posix(), "modified": modified.isoformat(timespec="seconds"), "size": path.stat().st_size})
    return sorted(result, key=lambda item: item["modified"])


TOOLS = [
    Tool(name="scratch_list", description="列出草稿箱文件。", inputSchema={"type":"object","properties":{}}),
    Tool(name="scratch_preview_cleanup", description="预览超过 7 天的草稿。", inputSchema={"type":"object","properties":{"before":{"type":"string","description":"ISO 时间，可选"}}}),
    Tool(name="scratch_cleanup", description="删除超过 7 天的草稿。", inputSchema={"type":"object","properties":{"before":{"type":"string","description":"ISO 时间，可选"}}}),
]
server = Server("scratch-space-management")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        before = args.get("before", (datetime.now() - timedelta(days=7)).isoformat())
        if name == "scratch_list":
            result = {"files": stale(datetime.now().isoformat())}  # replaced below
            result["files"] = [{"path": p.relative_to(SCRATCH_ROOT).as_posix(), "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"), "size": p.stat().st_size} for p in SCRATCH_ROOT.rglob("*") if p.is_file() and p.name != ".gitignore"] if SCRATCH_ROOT.is_dir() else []
        elif name == "scratch_preview_cleanup":
            result = {"before": before, "files": stale(before)}
        elif name == "scratch_cleanup":
            items = stale(before)
            deleted = []
            for item in items:
                path = safe_path(item["path"])
                path.unlink()
                deleted.append(item["path"])
            result = {"before": before, "deleted": deleted, "count": len(deleted)}
        else:
            raise ValueError(f"未知工具：{name}")
    except (KeyError, ValueError, OSError) as exc:
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=dump(result))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
