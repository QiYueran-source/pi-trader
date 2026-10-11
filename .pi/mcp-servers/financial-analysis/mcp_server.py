#!/usr/bin/env python3
"""财经分析数据库 MCP 服务。"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

DB_PATH = Path(os.getenv("FINANCIAL_ANALYSIS_DB_PATH", "/pi-trader/database/financial_analysis.db"))
SOURCE_TYPES = {"盘前分析", "盘前荐股", "盘后荐股", "盘后分析", "周末要闻", "调仓信息"}
SENTIMENTS = {"积极", "中性", "消极", "谨慎"}
TYPES = {"stock", "sector"}


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.is_file():
        raise RuntimeError(f"财经分析数据库不存在：{DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def valid_date(value: str, field: str = "date") -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD") from exc


def validate_mention(item: dict[str, Any]) -> tuple[Any, ...]:
    required = {"name", "type", "mention_date", "source_type", "source_file"}
    missing = required - item.keys()
    if missing:
        raise ValueError(f"判断缺少字段：{sorted(missing)}")
    if not item["name"] or item["type"] not in TYPES:
        raise ValueError("name 不能为空，type 必须是 stock 或 sector")
    if item["source_type"] not in SOURCE_TYPES:
        raise ValueError(f"source_type 必须是 {sorted(SOURCE_TYPES)}")
    sentiment = item.get("sentiment", "中性")
    if sentiment not in SENTIMENTS:
        raise ValueError(f"sentiment 必须是 {sorted(SENTIMENTS)}")
    mention_date = valid_date(item["mention_date"], "mention_date")
    window_end = item.get("window_end_date")
    if window_end:
        window_end = valid_date(window_end, "window_end_date")
    return (item["name"], item.get("code"), item["type"], mention_date,
            item["source_type"], item["source_file"], sentiment,
            item.get("context"), window_end)


def mention_list(args: dict[str, Any]) -> dict[str, Any]:
    query = "SELECT * FROM mentions WHERE 1=1"
    params: list[Any] = []
    filters = (("mention_date", "mention_date"), ("source_type", "source_type"),
               ("name", "name"), ("code", "code"), ("type", "type"),
               ("source_file", "source_file"))
    for key, column in filters:
        if args.get(key):
            query += f" AND {column} = ?"
            params.append(args[key])
    query += " ORDER BY mention_date DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(args.get("limit", 200)), 1000)))
    with db() as conn:
        result = rows(conn.execute(query, params))
    return {"total": len(result), "mentions": result}


def record_mentions(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(items, list) or not items:
        raise ValueError("items 必须是非空数组")
    records = [validate_mention(item) for item in items]
    inserted = 0
    skipped = 0
    with db() as conn:
        for record in records:
            exists = conn.execute(
                "SELECT id FROM mentions WHERE name=? AND mention_date=? AND source_file=? AND context IS ?",
                (record[0], record[3], record[5], record[7]),
            ).fetchone()
            if exists:
                skipped += 1
                continue
            conn.execute("""INSERT INTO mentions
                (name,code,type,mention_date,source_type,source_file,sentiment,context,window_end_date)
                VALUES (?,?,?,?,?,?,?,?,?)""", record)
            inserted += 1
    return {"status": "recorded", "inserted": inserted, "skipped": skipped}


def replace_mentions(args: dict[str, Any]) -> dict[str, Any]:
    mention_date = valid_date(args["mention_date"], "mention_date")
    source_file = args["source_file"]
    items = args.get("items", [])
    for item in items:
        item["mention_date"] = mention_date
        item["source_file"] = source_file
    records = [validate_mention(item) for item in items]
    with db() as conn:
        deleted = conn.execute(
            "DELETE FROM mentions WHERE mention_date=? AND source_file=?",
            (mention_date, source_file),
        ).rowcount
        for record in records:
            conn.execute("""INSERT INTO mentions
                (name,code,type,mention_date,source_type,source_file,sentiment,context,window_end_date)
                VALUES (?,?,?,?,?,?,?,?,?)""", record)
    return {"status": "replaced", "deleted": deleted, "inserted": len(records),
            "mention_date": mention_date, "source_file": source_file}


def active_items(args: dict[str, Any]) -> dict[str, Any]:
    as_of = valid_date(args.get("as_of", date.today().isoformat()), "as_of")
    with db() as conn:
        result = rows(conn.execute("""SELECT name,code,type,MAX(window_end_date) AS window_end_date
            FROM mentions WHERE window_end_date >= ? GROUP BY name,code,type ORDER BY type,name""", (as_of,)))
    return {"as_of": as_of, "total": len(result), "items": result}


def performance_record(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(items, list) or not items:
        raise ValueError("items 必须是非空数组")
    with db() as conn:
        for item in items:
            if not item.get("name") or not item.get("track_date"):
                raise ValueError("行情记录需要 name 和 track_date")
            track_date = valid_date(item["track_date"], "track_date")
            conn.execute("""INSERT OR REPLACE INTO performance
                (name,code,track_date,pct_chg,volume,check_time)
                VALUES (?,?,?,?,?,?)""", (item["name"], item.get("code"), track_date,
                item.get("pct_chg"), item.get("volume"),
                item.get("check_time", datetime.now().strftime("%Y-%m-%d %H:%M"))))
    return {"status": "recorded", "count": len(items)}


def performance_list(args: dict[str, Any]) -> dict[str, Any]:
    query = "SELECT * FROM performance WHERE 1=1"
    params: list[Any] = []
    for key in ("name", "code", "track_date"):
        if args.get(key):
            query += f" AND {key} = ?"
            params.append(args[key])
    query += " ORDER BY track_date DESC LIMIT ?"
    params.append(max(1, min(int(args.get("limit", 200)), 1000)))
    with db() as conn:
        result = rows(conn.execute(query, params))
    return {"total": len(result), "performance": result}


def review_date(args: dict[str, Any]) -> dict[str, Any]:
    review_date_value = valid_date(args["review_date"], "review_date")
    source = args.get("source")
    query = "SELECT * FROM mentions WHERE mention_date = ?"
    params: list[Any] = [review_date_value]
    if source:
        query += " AND source_file LIKE ?"
        params.append(f"%{source}%")
    query += " ORDER BY source_file, id"
    with db() as conn:
        mentions = rows(conn.execute(query, params))
        results = []
        for mention in mentions:
            offset = mention["source_type"] in {"盘后荐股", "周末要闻"}
            check_date = (date.fromisoformat(mention["mention_date"]) + timedelta(days=1)).isoformat() if offset else mention["mention_date"]
            end = mention["window_end_date"] or check_date
            performance = rows(conn.execute("""SELECT track_date,pct_chg,volume,check_time
                FROM performance WHERE name=? AND track_date BETWEEN ? AND ? ORDER BY track_date""",
                (mention["name"], check_date, end)))
            results.append({"mention": mention, "check_date": check_date, "performance": performance})
    return {"review_date": review_date_value, "total": len(results), "results": results}


def stats(args: dict[str, Any]) -> dict[str, Any]:
    days = max(1, min(int(args.get("days", 30)), 3650))
    since = (date.today() - timedelta(days=days)).isoformat()
    with db() as conn:
        query = """SELECT m.*, p.pct_chg, p.track_date FROM mentions m LEFT JOIN performance p
            ON m.name=p.name AND p.track_date=CASE WHEN m.source_type IN ('盘后荐股','周末要闻')
            THEN date(m.mention_date,'+1 day') ELSE m.mention_date END WHERE m.mention_date >= ?"""
        params: list[Any] = [since]
        if args.get("source"):
            query += " AND m.source_file LIKE ?"
            params.append(f"%{args['source']}%")
        records = rows(conn.execute(query, params))
    actionable = [r for r in records if r["sentiment"] != "中性" and r["pct_chg"] is not None]
    correct = sum((r["sentiment"] == "积极" and r["pct_chg"] > 0) or (r["sentiment"] in {"谨慎", "消极"} and r["pct_chg"] < 0) for r in actionable)
    return {"since": since, "total": len(records), "actionable": len(actionable), "correct": correct,
            "accuracy": round(correct / len(actionable), 4) if actionable else None}


TOOLS = [
    Tool(name="financial_analysis_list_mentions", description="查询财经分析判断记录。", inputSchema={"type":"object","properties":{"mention_date":{"type":"string"},"source_type":{"type":"string"},"source_file":{"type":"string"},"name":{"type":"string"},"code":{"type":"string"},"type":{"type":"string"},"limit":{"type":"integer"}}}),
    Tool(name="financial_analysis_record_mentions", description="批量新增判断记录；重复记录会跳过。", inputSchema={"type":"object","properties":{"items":{"type":"array","items":{"type":"object"}}},"required":["items"]}),
    Tool(name="financial_analysis_replace_mentions", description="按日期和来源文件替换判断记录。", inputSchema={"type":"object","properties":{"mention_date":{"type":"string"},"source_file":{"type":"string"},"items":{"type":"array","items":{"type":"object"}}},"required":["mention_date","source_file","items"]}),
    Tool(name="financial_analysis_active_items", description="查询截至指定日期仍在跟踪窗口内的标的。", inputSchema={"type":"object","properties":{"as_of":{"type":"string"}}}),
    Tool(name="financial_analysis_record_performance", description="批量写入行情跟踪数据。", inputSchema={"type":"object","properties":{"items":{"type":"array","items":{"type":"object"}}},"required":["items"]}),
    Tool(name="financial_analysis_list_performance", description="查询行情跟踪数据。", inputSchema={"type":"object","properties":{"name":{"type":"string"},"code":{"type":"string"},"track_date":{"type":"string"},"limit":{"type":"integer"}}}),
    Tool(name="financial_analysis_review_date", description="查询指定日期的判断、验证日期和实际表现。", inputSchema={"type":"object","properties":{"review_date":{"type":"string"},"source":{"type":"string"}},"required":["review_date"]}),
    Tool(name="financial_analysis_stats", description="统计最近一段时间的方向判断准确率。", inputSchema={"type":"object","properties":{"source":{"type":"string"},"days":{"type":"integer"}}}),
]

server = Server("financial-analysis")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        handlers = {
            "financial_analysis_list_mentions": lambda: mention_list(args),
            "financial_analysis_record_mentions": lambda: record_mentions(args["items"]),
            "financial_analysis_replace_mentions": lambda: replace_mentions(args),
            "financial_analysis_active_items": lambda: active_items(args),
            "financial_analysis_record_performance": lambda: performance_record(args["items"]),
            "financial_analysis_list_performance": lambda: performance_list(args),
            "financial_analysis_review_date": lambda: review_date(args),
            "financial_analysis_stats": lambda: stats(args),
        }
        if name not in handlers:
            raise ValueError(f"未知工具：{name}")
        result = handlers[name]()
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
