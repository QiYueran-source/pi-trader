#!/usr/bin/env python3
"""知识库日期文档归档 MCP：发现候选、移动文件、清理归档遗留空目录。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", "/pi-trader/knowledge")).resolve()
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/pi-trader/archive")).resolve()
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SUMMARY_RE = re.compile(r"^摘要_(\d{4}-\d{2}-\d{2})\.md$")


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def source_path(relative: str) -> Path:
    path = (KNOWLEDGE_ROOT / relative).resolve()
    if path == KNOWLEDGE_ROOT or KNOWLEDGE_ROOT not in path.parents:
        raise ValueError("源路径必须位于 knowledge 目录内")
    if "归档" in path.relative_to(KNOWLEDGE_ROOT).parts:
        raise ValueError("已归档路径不能再次归档")
    return path


def valid_date(value: str) -> bool:
    if not DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def date_part(path: Path) -> str | None:
    """返回日期目录中的合法日期；摘要文件单独由 summary_date 处理。"""
    relative = path.relative_to(KNOWLEDGE_ROOT)
    for part in relative.parts[:-1]:
        if valid_date(part):
            return part
    return None


def summary_date(path: Path) -> str | None:
    relative = path.relative_to(KNOWLEDGE_ROOT)
    if len(relative.parts) != 2 or relative.parts[0] != "摘要":
        return None
    match = SUMMARY_RE.fullmatch(relative.name)
    if not match or not valid_date(match.group(1)):
        return None
    return match.group(1)


def document_date(path: Path) -> str | None:
    return date_part(path) or summary_date(path)


def is_candidate(path: Path, cutoff: date) -> tuple[bool, str | None]:
    doc_date = document_date(path)
    return bool(doc_date and date.fromisoformat(doc_date) <= cutoff), doc_date


def candidates(cutoff: str) -> list[dict[str, Any]]:
    limit = date.fromisoformat(cutoff)
    result: list[dict[str, Any]] = []
    if not KNOWLEDGE_ROOT.is_dir():
        return result
    for path in KNOWLEDGE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(KNOWLEDGE_ROOT)
        if "归档" in relative.parts or ".abstract" in relative.parts:
            continue
        matched, doc_date = is_candidate(path, limit)
        if not matched:
            continue
        result.append({
            "path": relative.as_posix(),
            "date": doc_date,
            "size": path.stat().st_size,
        })
    return sorted(result, key=lambda item: (item["date"], item["path"]))


def preview(relative: str) -> dict[str, Any]:
    source = source_path(relative)
    if not source.is_file():
        return {"ok": False, "path": relative, "reason": "source_not_found"}
    doc_date = document_date(source)
    if not doc_date:
        return {"ok": False, "path": relative, "reason": "not_date_based_document"}
    target = ARCHIVE_ROOT / relative
    return {
        "ok": not target.exists(),
        "source": relative,
        "target": relative,
        "target_exists": target.exists(),
        "date": doc_date,
    }


def move(relative: str) -> dict[str, Any]:
    info = preview(relative)
    if not info.get("ok"):
        return {"ok": False, **info}
    source = source_path(relative)
    target = ARCHIVE_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return {"ok": True, "source": relative, "target": relative}


def dir_date(relative_parts: tuple[str, ...]) -> str | None:
    for part in relative_parts:
        if valid_date(part):
            return part
    return None


def cleanup_empty_dirs(dry_run: bool = True) -> dict[str, Any]:
    """删除归档后遗留的空日期目录，不删除文件或 archive 内内容。"""
    removed: list[str] = []
    skipped: list[dict[str, str]] = []
    if not KNOWLEDGE_ROOT.is_dir():
        return {"ok": True, "dry_run": dry_run, "count": 0, "removed": [], "skipped": []}

    today = date.today().isoformat()
    dirs = [path for path in KNOWLEDGE_ROOT.rglob("*") if path.is_dir()]
    for path in sorted(dirs, key=lambda item: len(item.relative_to(KNOWLEDGE_ROOT).parts), reverse=True):
        relative = path.relative_to(KNOWLEDGE_ROOT)
        parts = relative.parts
        if "归档" in parts or ".abstract" in parts:
            continue
        doc_date = dir_date(parts)
        if not doc_date:
            continue
        try:
            if any(path.iterdir()):
                continue
        except OSError:
            continue
        if not (ARCHIVE_ROOT / relative).is_dir():
            skipped.append({"path": relative.as_posix(), "reason": "no_archive_counterpart"})
            continue
        if doc_date >= today:
            skipped.append({"path": relative.as_posix(), "reason": "not_older_than_today"})
            continue
        if dry_run:
            removed.append(relative.as_posix())
            continue
        try:
            path.rmdir()
            removed.append(relative.as_posix())
        except OSError as exc:
            skipped.append({"path": relative.as_posix(), "reason": f"rmdir_failed: {exc}"})
    return {
        "ok": True,
        "dry_run": dry_run,
        "count": len(removed),
        "removed": removed,
        "skipped": skipped,
    }


def run_batch(
    before_date: str | None = None,
    dry_run: bool = True,
    include_paths: bool = False,
) -> dict[str, Any]:
    before_date = before_date or (date.today() - timedelta(days=30)).isoformat()
    items = candidates(before_date)
    planned: list[dict[str, str]] = []
    skipped: Counter[str] = Counter()

    for item in items:
        relative = item["path"]
        info = preview(relative)
        if info.get("target_exists"):
            skipped["target_exists"] += 1
            continue
        if not info.get("ok"):
            skipped[str(info.get("reason", "unknown"))] += 1
            continue
        if dry_run:
            planned.append({"source": relative, "target": relative})
            continue
        try:
            result = move(relative)
        except OSError as exc:
            skipped[f"move_failed:{exc}"] += 1
            continue
        if result.get("ok"):
            planned.append({"source": relative, "target": relative})
        else:
            skipped[f"move_failed:{result.get('reason', 'unknown')}"] += 1

    cleaned = {"count": 0, "removed": [], "skipped": []}
    if not dry_run:
        cleaned = cleanup_empty_dirs(dry_run=False)

    summary: dict[str, Any] = {
        "ok": True,
        "before_date": before_date,
        "dry_run": dry_run,
        "candidates": len(items),
        "archived": len(planned),
        "skipped": dict(skipped),
        "empty_dirs_removed": cleaned["count"],
        "empty_dirs_skipped": cleaned["skipped"],
        "sample": planned[:10],
    }
    if include_paths:
        summary["paths"] = planned
    return summary


TOOLS = [
    Tool(
        name="archive_list_candidates",
        description="列出指定日期以前的日期型知识文档和每日摘要。默认 30 天前。",
        inputSchema={
            "type": "object",
            "properties": {"before_date": {"type": "string", "description": "YYYY-MM-DD"}},
        },
    ),
    Tool(
        name="archive_preview",
        description="预览一个日期型文档或每日摘要的归档目标和冲突情况。",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对 knowledge 的路径"}},
            "required": ["path"],
        },
    ),
    Tool(
        name="archive_move",
        description="移动一个日期型文档或每日摘要到根目录 archive，不覆盖已有文件。",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对 knowledge 的路径"}},
            "required": ["path"],
        },
    ),
    Tool(
        name="archive_run",
        description="批量发现并移动日期型文档和每日摘要，默认只干跑预览；实跑后清理遗留空日期目录。",
        inputSchema={
            "type": "object",
            "properties": {
                "before_date": {"type": "string", "description": "YYYY-MM-DD；不传则为 30 天前"},
                "dry_run": {"type": "boolean", "description": "默认 true 只预览；false 才移动文件"},
                "include_paths": {"type": "boolean", "description": "默认 false；true 返回完整清单"},
            },
        },
    ),
    Tool(
        name="archive_cleanup_empty_dirs",
        description="删除归档后遗留的空日期目录；默认只返回待删清单。",
        inputSchema={
            "type": "object",
            "properties": {"dry_run": {"type": "boolean", "description": "默认 true；false 才删除空目录"}},
        },
    ),
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
        elif name == "archive_run":
            result = run_batch(
                args.get("before_date"),
                bool(args.get("dry_run", True)),
                bool(args.get("include_paths", False)),
            )
        elif name == "archive_cleanup_empty_dirs":
            result = cleanup_empty_dirs(bool(args.get("dry_run", True)))
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
