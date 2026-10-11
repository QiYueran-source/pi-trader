#!/usr/bin/env python3
"""知识库日期文档归档 MCP。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", "/pi-trader/knowledge")).resolve()
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/pi-trader/archive")).resolve()
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def source_path(relative: str) -> Path:
    path = (KNOWLEDGE_ROOT / relative).resolve()
    if path == KNOWLEDGE_ROOT or KNOWLEDGE_ROOT not in path.parents:
        raise ValueError("源路径必须位于 knowledge 目录内")
    if "归档" in path.relative_to(KNOWLEDGE_ROOT).parts:
        raise ValueError("已归档路径不能再次归档")
    return path


def date_part(path: Path) -> str | None:
    for part in path.relative_to(KNOWLEDGE_ROOT).parts[:-1]:
        if DATE_RE.fullmatch(part):
            try:
                date.fromisoformat(part)
                return part
            except ValueError:
                return None
    return None


def candidates(cutoff: str) -> list[dict[str, Any]]:
    limit = date.fromisoformat(cutoff)
    result = []
    if not KNOWLEDGE_ROOT.is_dir():
        return result
    for path in KNOWLEDGE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(KNOWLEDGE_ROOT)
        if "归档" in rel.parts or ".abstract" in rel.parts:
            continue
        doc_date = date_part(path)
        if not doc_date or date.fromisoformat(doc_date) > limit:
            continue
        result.append({"path": rel.as_posix(), "date": doc_date, "size": path.stat().st_size})
    return sorted(result, key=lambda item: (item["date"], item["path"]))


def references(relative: str) -> list[str]:
    result = []
    if not KNOWLEDGE_ROOT.is_dir():
        return result
    for path in KNOWLEDGE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".json"}:
            continue
        try:
            if relative in path.read_text(encoding="utf-8") and path.relative_to(KNOWLEDGE_ROOT).as_posix() != relative:
                result.append(path.relative_to(KNOWLEDGE_ROOT).as_posix())
        except (OSError, UnicodeDecodeError):
            continue
    return result


def preview(relative: str) -> dict[str, Any]:
    source = source_path(relative)
    if not source.is_file():
        return {"ok": False, "path": relative, "reason": "source_not_found"}
    doc_date = date_part(source)
    if not doc_date:
        return {"ok": False, "path": relative, "reason": "not_date_based_document"}
    target = ARCHIVE_ROOT / relative
    refs = references(relative)
    return {"ok": not target.exists() and not refs, "source": relative,
            "target": target.relative_to(ARCHIVE_ROOT).as_posix(),
            "target_exists": target.exists(), "references": refs,
            "requires_reference_update": bool(refs)}


def move(relative: str) -> dict[str, Any]:
    info = preview(relative)
    if not info["ok"]:
        return {"ok": False, **info}
    source = source_path(relative)
    target = ARCHIVE_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return {"ok": True, "source": relative, "target": target.relative_to(ARCHIVE_ROOT).as_posix()}


TOOLS = [
    Tool(name="archive_list_candidates", description="列出超过指定日期的日期型知识文档。默认 30 天前。", inputSchema={"type":"object","properties":{"before_date":{"type":"string","description":"YYYY-MM-DD"}}}),
    Tool(name="archive_preview", description="预览归档路径、目标冲突和引用关系。", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"相对 knowledge 的路径"}},"required":["path"]}),
    Tool(name="archive_move", description="移动一个无引用冲突的日期型文档到根目录 archive。", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"相对 knowledge 的路径"}},"required":["path"]}),
]
server = Server("archive-management")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "archive_list_candidates":
            before = args.get("before_date", (date.today() - timedelta(days=30)).isoformat())
            result = {"before_date": before, "candidates": candidates(before)}
        elif name == "archive_preview":
            result = preview(args["path"])
        elif name == "archive_move":
            result = move(args["path"])
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
