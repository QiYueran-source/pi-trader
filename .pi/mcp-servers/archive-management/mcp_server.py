#!/usr/bin/env python3
"""知识库日期文档归档 MCP。"""
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
DOC_SUFFIXES = {".md", ".yaml", ".yml", ".json"}
ARCHIVE_PREFIX = "archive"
REWRITE_GUARD = "\u0000archive-rewrite\u0000"


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


def docs() -> list[Path]:
    """knowledge 下可参与引用判定的文本文档。"""
    if not KNOWLEDGE_ROOT.is_dir():
        return []
    return [p for p in KNOWLEDGE_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in DOC_SUFFIXES]


def references(relative: str) -> list[str]:
    result = []
    for path in docs():
        rel = path.relative_to(KNOWLEDGE_ROOT).as_posix()
        if rel == relative:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if relative not in text:
            continue
        # 已改写为 archive/<relative> 的提及不再算引用（与 rewrite_references 同一口径）
        if relative in text.replace(f"{ARCHIVE_PREFIX}/{relative}", REWRITE_GUARD):
            result.append(rel)
    return result


def rewrite_references(relative: str, apply: bool = False) -> dict[str, Any]:
    """把 knowledge 文档中对 relative 的引用改写为 archive/<relative>。

    只做精确路径字符串替换：跳过被引用文件自身，跳过已带 archive/ 前缀的写法，
    默认只预览（apply=False），不修改正文。
    """
    source_path(relative)
    token = f"{ARCHIVE_PREFIX}/{relative}"
    files: list[dict[str, Any]] = []
    total = 0
    for path in docs():
        rel = path.relative_to(KNOWLEDGE_ROOT).as_posix()
        if rel == relative:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if relative not in text:
            continue
        guarded = text.replace(token, REWRITE_GUARD)
        count = guarded.count(relative)
        if count == 0:
            continue
        sample_before = sample_after = ""
        for line in guarded.splitlines():
            if relative in line:
                sample_before = line.strip()[:200]
                sample_after = line.replace(relative, token).strip()[:200]
                break
        if apply:
            new_text = guarded.replace(relative, token).replace(REWRITE_GUARD, token)
            tmp = path.with_name(path.name + ".rewrite-tmp")
            tmp.write_text(new_text, encoding="utf-8")
            os.replace(tmp, path)
        files.append({"path": rel, "occurrences": count,
                      "sample_before": sample_before, "sample_after": sample_after})
        total += count
    return {"ok": True, "path": relative, "replacement": token, "applied": apply,
            "files": files, "files_changed": len(files), "replacements": total}


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


def move(relative: str, rewrite: bool = False) -> dict[str, Any]:
    info = preview(relative)
    if info.get("target_exists"):
        return {"ok": False, **info}
    rewrite_info = None
    if info.get("references"):
        if not rewrite:
            return {"ok": False, **info}
        # 先改写引用（只改正文里的路径字符串），复查归零后再移动
        rewrite_info = rewrite_references(relative, apply=True)
        info = preview(relative)
        if info.get("references"):
            return {"ok": False, "reason": "references_remain", "source": relative,
                    "remaining": info["references"], "rewrite": rewrite_info}
    if not info.get("ok"):
        return {"ok": False, **info}
    source = source_path(relative)
    target = ARCHIVE_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    result = {"ok": True, "source": relative, "target": target.relative_to(ARCHIVE_ROOT).as_posix()}
    if rewrite_info:
        result["rewrite"] = rewrite_info
    return result


def run_batch(before_date: str, rewrite: bool = False, dry_run: bool = True,
              include_paths: bool = False) -> dict[str, Any]:
    """批量归档：候选 → 预览 →（可选改写引用）→ 移动 → 清理空目录。"""
    items = candidates(before_date)
    planned: list[str] = []
    skipped: Counter[str] = Counter()
    rewrite_files = rewrite_tokens = 0
    for item in items:
        rel = item["path"]
        info = preview(rel)
        if info.get("target_exists"):
            skipped["target_exists"] += 1
            continue
        if not info.get("ok") and not info.get("references"):
            skipped[info.get("reason", "unknown")] += 1
            continue
        if info.get("references") and not rewrite:
            skipped["references"] += 1
            continue
        if dry_run:
            if info.get("references"):
                preview_rw = rewrite_references(rel, apply=False)
                if preview_rw["files_changed"] == 0:
                    skipped["references_remain"] += 1
                    continue
                rewrite_files += preview_rw["files_changed"]
                rewrite_tokens += preview_rw["replacements"]
            planned.append(rel)
            continue
        result = move(rel, rewrite=rewrite)
        if result.get("ok"):
            planned.append(rel)
            if result.get("rewrite"):
                rewrite_files += result["rewrite"]["files_changed"]
                rewrite_tokens += result["rewrite"]["replacements"]
        else:
            skipped["move_failed:" + str(result.get("reason") or result.get("error") or "unknown")] += 1
    cleaned = {"count": 0, "skipped": []}
    if not dry_run:
        cleaned = cleanup_empty_dirs(dry_run=False)
    summary = {"ok": True, "before_date": before_date, "dry_run": dry_run,
               "rewrite_references": rewrite, "candidates": len(items),
               "archived": len(planned), "skipped": dict(skipped),
               "rewrite": {"files": rewrite_files, "replacements": rewrite_tokens},
               "empty_dirs_removed": cleaned["count"], "empty_dirs_skipped": cleaned["skipped"],
               "sample": planned[:10]}
    if include_paths:
        summary["paths"] = planned
    return summary


def dir_date(relative_parts: tuple[str, ...]) -> str | None:
    """目录自身或其父级中的 YYYY-MM-DD 部分。"""
    for part in relative_parts:
        if DATE_RE.fullmatch(part):
            try:
                date.fromisoformat(part)
                return part
            except ValueError:
                return None
    return None


def cleanup_empty_dirs(dry_run: bool = True) -> dict[str, Any]:
    """删除归档后遗留的空日期目录。

    只删除同时满足以下条件的目录，任一不满足则跳过：
    1. 位于 knowledge 内、自身或父级为合法 YYYY-MM-DD 目录；
    2. 完全为空（不含文件、子目录或隐藏文件）；
    3. 在 archive 下存在同相对路径的目录（证明确实是归档后的空壳）；
    4. 日期早于今天（避免与当天正在写入的任务竞争）；
    5. 不涉及「归档」目录与 .abstract。
    """
    removed: list[str] = []
    skipped: list[dict[str, str]] = []
    if not KNOWLEDGE_ROOT.is_dir():
        return {"ok": True, "dry_run": dry_run, "count": 0, "removed": [], "skipped": []}
    today = date.today().isoformat()
    dirs = [p for p in KNOWLEDGE_ROOT.rglob("*") if p.is_dir()]
    # 自底向上：先清掉深层空目录，父目录可能在随后一轮变为空
    for path in sorted(dirs, key=lambda p: len(p.relative_to(KNOWLEDGE_ROOT).parts), reverse=True):
        rel = path.relative_to(KNOWLEDGE_ROOT)
        parts = rel.parts
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
        if not (ARCHIVE_ROOT / rel).is_dir():
            skipped.append({"path": rel.as_posix(), "reason": "no_archive_counterpart"})
            continue
        if doc_date >= today:
            skipped.append({"path": rel.as_posix(), "reason": "not_older_than_today"})
            continue
        if dry_run:
            removed.append(rel.as_posix())
            continue
        try:
            path.rmdir()
            removed.append(rel.as_posix())
        except OSError as exc:
            skipped.append({"path": rel.as_posix(), "reason": f"rmdir_failed: {exc}"})
    return {"ok": True, "dry_run": dry_run, "count": len(removed), "removed": removed, "skipped": skipped}


TOOLS = [
    Tool(name="archive_list_candidates", description="列出超过指定日期的日期型知识文档。默认 30 天前。", inputSchema={"type":"object","properties":{"before_date":{"type":"string","description":"YYYY-MM-DD"}}}),
    Tool(name="archive_preview", description="预览归档路径、目标冲突和引用关系。", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"相对 knowledge 的路径"}},"required":["path"]}),
    Tool(name="archive_move", description="移动一个日期型文档到根目录 archive。默认拒绝被引用的文件；将 rewrite_references 设为 true 时先改写引用再移动。", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"相对 knowledge 的路径"},"rewrite_references":{"type":"boolean","description":"默认 false；true 则先把引用改写为 archive/<path> 再移动"}},"required":["path"]}),
    Tool(name="archive_rewrite_references", description="把 knowledge 文档中对某个已知档路径的引用改写为 archive/<path>。只做精确路径替换，默认只预览。", inputSchema={"type":"object","properties":{"path":{"type":"string","description":"相对 knowledge 的路径"},"apply":{"type":"boolean","description":"默认 false 只预览；true 才写入"}},"required":["path"]}),
    Tool(name="archive_run", description="批量归档：候选→预览→（可选改写引用）→移动→清理空目录。默认只干跑预览，返回汇总统计。", inputSchema={"type":"object","properties":{"before_date":{"type":"string","description":"YYYY-MM-DD，归档此日期及更早的日期型文档"},"rewrite_references":{"type":"boolean","description":"默认 false：被引用的文件跳过；true：先改写引用再归档"},"dry_run":{"type":"boolean","description":"默认 true 只预览，不移动不修改"},"include_paths":{"type":"boolean","description":"默认 false 只返回样例；true 返回完整待处理清单"}},"required":["before_date"]}),
    Tool(name="archive_cleanup_empty_dirs", description="删除归档后遗留的空日期目录；仅删除空目录且须有 archive 对应目录，默认只预览。这一步只清理空壳，不需要用户确认。", inputSchema={"type":"object","properties":{"dry_run":{"type":"boolean","description":"默认 true 只返回待删清单；设为 false 才真正删除"}}}),
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
            result = move(args["path"], bool(args.get("rewrite_references", False)))
        elif name == "archive_rewrite_references":
            result = rewrite_references(args["path"], bool(args.get("apply", False)))
        elif name == "archive_run":
            result = run_batch(args["before_date"], bool(args.get("rewrite_references", False)),
                               bool(args.get("dry_run", True)), bool(args.get("include_paths", False)))
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
