#!/usr/bin/env python3
"""跨文档待办索引 MCP。文件是事实来源，SQLite 只保存可重建的文件级索引。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", "/pi-trader/knowledge")).resolve()
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/pi-trader/archive")).resolve()
DB_PATH = Path(os.getenv("TODO_DB_PATH", "/pi-trader/database/todo_index.db")).resolve()
SHANGHAI = timezone(timedelta(hours=8))
CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\](?:\s+|$)")
ITEM_RE = re.compile(
    r"^\s*-\s*\[([ xX])\]\s+"
    r"(T-\d{4}-\d{2}-\d{2}-\d+)\s+｜\s*"
    r"([^｜]+?)\s+｜\s*([^｜]+?)\s+｜\s*(\S.*?)\s*$"
)

TOOLS = [
    Tool(
        name="todo_scan",
        description="扫描最近活跃文档和数据库中的非终态待办文件，幂等更新文件级索引。",
        inputSchema={"type": "object", "properties": {
            "roots": {"type": "array", "items": {"type": "string", "enum": ["knowledge", "archive"]}},
            "since_days": {"type": "integer", "minimum": 0, "default": 7},
            "dry_run": {"type": "boolean", "default": False},
        }},
    ),
    Tool(
        name="todo_list",
        description="查询待办文件级索引；返回的 path_rel 是不带 knowledge/archive 前缀的逻辑路径。",
        inputSchema={"type": "object", "properties": {
            "prefix": {"type": "string", "description": "逻辑路径前缀，不含 knowledge/ 或 archive/"},
            "state": {"type": "string", "enum": ["knowledge", "archive", "both", "gone"]},
            "open_only": {"type": "boolean", "default": True},
            "min_age_days": {"type": "integer", "minimum": 0},
            "sort": {"type": "string", "enum": ["age_desc", "open_count_desc", "path", "first_open_asc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        }},
    ),
    Tool(
        name="todo_stats",
        description="按路径前缀或体系汇总未结待办。",
        inputSchema={"type": "object", "properties": {
            "group_by": {"type": "string", "enum": ["prefix", "system"], "default": "prefix"},
            "top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
        }},
    ),
    Tool(
        name="todo_audit",
        description="按与扫描相同的纳入范围核对文件和数据库，只报告不修改。",
        inputSchema={"type": "object", "properties": {
            "date": {"type": "string", "description": "Asia/Shanghai 日期，默认今天"},
            "since_days": {"type": "integer", "minimum": 0, "default": 7},
            "roots": {"type": "array", "items": {"type": "string", "enum": ["knowledge", "archive"]}},
        }},
    ),
]
server = Server("todo-management")


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def today() -> date:
    return datetime.now(SHANGHAI).date()


def iso_today() -> str:
    return today().isoformat()


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS todo_files (
            path_rel TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK (state IN ('knowledge', 'archive')),
            open_count INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0,
            first_open_date TEXT,
            closed_at TEXT,
            last_scan_date TEXT NOT NULL
        );
        INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1')
            ON CONFLICT(key) DO NOTHING;
        """
    )
    return conn


def roots_for(names: Iterable[str] | None) -> dict[str, Path]:
    names = list(names or ("knowledge", "archive"))
    unknown = set(names) - {"knowledge", "archive"}
    if unknown:
        raise ValueError(f"roots 只能包含 knowledge/archive：{sorted(unknown)}")
    return {name: (KNOWLEDGE_ROOT if name == "knowledge" else ARCHIVE_ROOT) for name in names}


def logical_files(roots: dict[str, Path]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for state, root in roots.items():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                found[path.relative_to(root).as_posix()].add(state)
    return found


def physical_path(state: str, path_rel: str) -> Path:
    root = KNOWLEDGE_ROOT if state == "knowledge" else ARCHIVE_ROOT
    path = (root / path_rel).resolve()
    if root not in path.parents:
        raise ValueError("路径超出受管根目录")
    return path


def parse_file(path: Path) -> dict[str, Any]:
    open_count = total_count = unrecognized = 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"ok": False, "error": str(exc), "open_count": 0, "total_count": 0, "unrecognized": 0}
    for line in text.splitlines():
        if not CHECKBOX_RE.match(line):
            continue
        match = ITEM_RE.match(line)
        if not match:
            unrecognized += 1
            continue
        total_count += 1
        if match.group(1) == " ":
            open_count += 1
    return {"ok": True, "open_count": open_count, "total_count": total_count, "unrecognized": unrecognized}


def mtime_is_recent(path: Path, since_days: int, as_of: date) -> bool:
    cutoff = datetime.combine(as_of - timedelta(days=since_days), datetime.min.time(), SHANGHAI)
    modified = datetime.fromtimestamp(path.stat().st_mtime, SHANGHAI)
    return modified >= cutoff


def eligible_paths(roots: dict[str, Path], since_days: int, as_of: date, conn: sqlite3.Connection | None) -> tuple[dict[str, set[str]], list[str]]:
    files = logical_files(roots)
    nonterminal: set[str] = set()
    if conn is not None:
        nonterminal = {row[0] for row in conn.execute("SELECT path_rel FROM todo_files WHERE open_count > 0")}
    eligible: dict[str, set[str]] = defaultdict(set)
    excluded: list[str] = []
    for path_rel, states in files.items():
        if "knowledge" in states and "archive" in states:
            eligible[path_rel] = states
            continue
        state = next(iter(states))
        path = physical_path(state, path_rel)
        try:
            active = mtime_is_recent(path, since_days, as_of)
        except OSError:
            active = False
        if active or path_rel in nonterminal:
            eligible[path_rel] = states
        else:
            excluded.append(path_rel)
    return eligible, sorted(excluded)


def presence(path_rel: str) -> str:
    knowledge = physical_path("knowledge", path_rel).is_file()
    archive = physical_path("archive", path_rel).is_file()
    if knowledge and archive:
        return "both"
    if knowledge:
        return "knowledge"
    if archive:
        return "archive"
    return "gone"


def scan(roots: dict[str, Path], since_days: int, dry_run: bool) -> dict[str, Any]:
    as_of = today()
    conn = db_connect()
    try:
        eligible, excluded = eligible_paths(roots, since_days, as_of, conn)
        result: dict[str, Any] = {
            "ok": True, "dry_run": dry_run, "as_of": as_of.isoformat(),
            "since_days": since_days, "eligible_files": len(eligible),
            "excluded_files": len(excluded), "excluded_paths": excluded,
            "scanned_files": 0, "created_rows": 0, "updated_rows": 0,
            "transitioned_rows": 0, "unrecognized_lines": 0,
            "both_exist": [], "read_errors": [], "changes": [],
        }
        changes: list[dict[str, Any]] = []
        parsed: list[tuple[str, str, dict[str, Any]]] = []
        for path_rel, states in eligible.items():
            if states == {"knowledge", "archive"}:
                result["both_exist"].append(path_rel)
                continue
            state = next(iter(states))
            info = parse_file(physical_path(state, path_rel))
            if not info["ok"]:
                result["read_errors"].append({"path": path_rel, "error": info["error"]})
                continue
            parsed.append((path_rel, state, info))
            result["scanned_files"] += 1
            result["unrecognized_lines"] += info["unrecognized"]
        if dry_run:
            for path_rel, state, info in parsed:
                old = conn.execute("SELECT * FROM todo_files WHERE path_rel = ?", (path_rel,)).fetchone()
                changes.append({"path": path_rel, "state": state, "open_count": info["open_count"], "total_count": info["total_count"], "previous_open_count": old["open_count"] if old else None})
            result["changes"] = changes
            return result
        conn.execute("BEGIN IMMEDIATE")
        for path_rel, state, info in parsed:
            old = conn.execute("SELECT * FROM todo_files WHERE path_rel = ?", (path_rel,)).fetchone()
            open_count = info["open_count"]
            total_count = info["total_count"]
            if old is None:
                first_open = as_of.isoformat() if open_count > 0 else None
                closed_at = None
                conn.execute("INSERT INTO todo_files VALUES (?, ?, ?, ?, ?, ?, ?)", (path_rel, state, open_count, total_count, first_open, closed_at, as_of.isoformat()))
                result["created_rows"] += 1
                transitioned = open_count > 0
            else:
                first_open = old["first_open_date"]
                closed_at = old["closed_at"]
                transitioned = (old["open_count"] == 0) != (open_count == 0)
                if old["open_count"] == 0 and open_count > 0 and not first_open:
                    first_open = as_of.isoformat()
                if old["open_count"] > 0 and open_count == 0:
                    closed_at = as_of.isoformat()
                conn.execute(
                    "UPDATE todo_files SET state=?, open_count=?, total_count=?, first_open_date=?, closed_at=?, last_scan_date=? WHERE path_rel=?",
                    (state, open_count, total_count, first_open, closed_at, as_of.isoformat(), path_rel),
                )
                result["updated_rows"] += 1
            if transitioned:
                result["transitioned_rows"] += 1
            changes.append({"path": path_rel, "state": state, "open_count": open_count, "total_count": total_count, "transitioned": transitioned})
        conn.commit()
        result["changes"] = changes
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_output(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["presence"] = presence(item["path_rel"])
    start = item["closed_at"] or item["first_open_date"]
    item["current_cycle_start"] = start
    item["age_days"] = max(0, (today() - date.fromisoformat(start)).days) if start else 0
    return item


def list_todos(args: dict[str, Any]) -> dict[str, Any]:
    conn = db_connect()
    try:
        rows = [row_output(row) for row in conn.execute("SELECT * FROM todo_files")]
    finally:
        conn.close()
    prefix = args.get("prefix")
    state = args.get("state")
    open_only = args.get("open_only", True)
    min_age = args.get("min_age_days")
    if prefix:
        rows = [row for row in rows if row["path_rel"] == prefix or row["path_rel"].startswith(prefix.rstrip("/") + "/")]
    if state:
        rows = [row for row in rows if row["presence"] == state]
    if open_only:
        rows = [row for row in rows if row["open_count"] > 0]
    if min_age is not None:
        rows = [row for row in rows if row["open_count"] > 0 and row["age_days"] >= int(min_age)]
    sort = args.get("sort", "age_desc")
    if sort == "path":
        rows.sort(key=lambda row: row["path_rel"])
    elif sort == "open_count_desc":
        rows.sort(key=lambda row: (-row["open_count"], row["path_rel"]))
    elif sort == "first_open_asc":
        rows.sort(key=lambda row: (row["first_open_date"] or "9999-99-99", row["path_rel"]))
    else:
        rows.sort(key=lambda row: (-row["age_days"], row["path_rel"]))
    limit = min(int(args.get("limit", 100)), 1000)
    return {"ok": True, "count": len(rows), "items": rows[:limit]}


def group_name(path_rel: str, mode: str) -> str:
    parts = path_rel.split("/")
    if mode == "system" and len(parts) >= 2 and parts[0] == "交易":
        return "/".join(parts[:2])
    return parts[0] if parts else "(root)"


def stats(args: dict[str, Any]) -> dict[str, Any]:
    items = list_todos({"open_only": True, "limit": 1000})["items"]
    mode = args.get("group_by", "prefix")
    groups: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "open_items": 0})
    for item in items:
        group = group_name(item["path_rel"], mode)
        groups[group]["files"] += 1
        groups[group]["open_items"] += item["open_count"]
    top = sorted(groups.items(), key=lambda pair: (-pair[1]["open_items"], pair[0]))[: int(args.get("top_n", 10))]
    oldest = sorted(items, key=lambda item: (-item["age_days"], item["path_rel"]))[: int(args.get("top_n", 10))]
    return {"ok": True, "open_file_count": len(items), "open_item_count": sum(item["open_count"] for item in items), "oldest": oldest, "groups": [{"group": key, **value} for key, value in top]}


def audit(args: dict[str, Any]) -> dict[str, Any]:
    as_of = date.fromisoformat(args.get("date", iso_today()))
    since_days = int(args.get("since_days", 7))
    roots = roots_for(args.get("roots"))
    conn = db_connect()
    try:
        eligible, excluded = eligible_paths(roots, since_days, as_of, conn)
        db_rows = {row["path_rel"]: row for row in conn.execute("SELECT * FROM todo_files")}
    finally:
        conn.close()
    result: dict[str, Any] = {
        "ok": True, "as_of": as_of.isoformat(), "since_days": since_days,
        "eligible_files": len(eligible), "excluded_historical_files": len(excluded),
        "missing_in_db": [], "count_mismatch": [], "unrecognized_lines": [],
        "path_drift": [], "both_exist": [], "gone": [], "read_errors": [],
    }
    seen: set[str] = set()
    for path_rel, states in eligible.items():
        seen.add(path_rel)
        if states == {"knowledge", "archive"}:
            result["both_exist"].append(path_rel)
            continue
        state = next(iter(states))
        info = parse_file(physical_path(state, path_rel))
        if not info["ok"]:
            result["read_errors"].append({"path": path_rel, "error": info["error"]})
            continue
        row = db_rows.get(path_rel)
        if row is None:
            result["missing_in_db"].append(path_rel)
        else:
            if row["open_count"] != info["open_count"] or row["total_count"] != info["total_count"]:
                result["count_mismatch"].append({"path": path_rel, "db_open_count": row["open_count"], "file_open_count": info["open_count"], "db_total_count": row["total_count"], "file_total_count": info["total_count"]})
        if info["unrecognized"]:
            result["unrecognized_lines"].append({"path": path_rel, "count": info["unrecognized"]})
    result["gone"] = sorted(path for path in db_rows if path not in seen and presence(path) == "gone")
    result["problem_count"] = sum(len(result[key]) for key in ("missing_in_db", "count_mismatch", "unrecognized_lines", "path_drift", "both_exist", "gone", "read_errors"))
    return result


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "todo_scan":
            result = scan(roots_for(args.get("roots")), int(args.get("since_days", 7)), bool(args.get("dry_run", False)))
        elif name == "todo_list":
            result = list_todos(args)
        elif name == "todo_stats":
            result = stats(args)
        elif name == "todo_audit":
            result = audit(args)
        else:
            raise ValueError(f"未知工具：{name}")
    except (ValueError, OSError, sqlite3.Error) as exc:
        result = {"ok": False, "error": str(exc)}
    return [TextContent(type="text", text=dump(result))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
