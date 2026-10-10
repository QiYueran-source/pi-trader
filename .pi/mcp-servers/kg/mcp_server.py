#!/usr/bin/env python3
"""
KG MCP Server — 对外暴露知识图谱（Knowledge Graph）查询工具。

提供工具：
- kg_query: 查询文档的关联关系（出入边，支持多层遍历）
- kg_search: 按关键词搜索文档路径
- kg_list_all: 列出知识图谱所有文档

数据库路径默认按环境变量 KG_DB_PATH 读取，
未设置时回退到项目默认路径：/pi-trader/knowledge/knowledge_graph.db。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── 数据库路径 ────────────────────────────────────────────────────────────
_DEFAULT_DB = Path(
    os.getenv("KG_DB_PATH", "/pi-trader/knowledge/knowledge_graph.db")
)


def _get_kg_db(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    """获取 KG 数据库连接，若文件不存在则报错，不隐式建空库。"""
    if not db_path.is_file():
        raise RuntimeError(
            f"KG 数据库不存在：{db_path}（可通过环境变量 KG_DB_PATH 配置）"
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ═════════════════════════════════════════════════════════════════════════
#  KG 查询核心逻辑
# ═════════════════════════════════════════════════════════════════════════

def kg_query(
    path: str | None = None,
    uuid: str | None = None,
    depth: int = 1,
) -> str:
    """查询文档在知识图谱中的关联关系（出入边）。"""
    if not path and not uuid:
        return json.dumps(
            {"error": "需要指定 path 或 uuid 参数"}, ensure_ascii=False
        )

    try:
        conn = _get_kg_db()
        cursor = conn.cursor()

        if uuid:
            cursor.execute("SELECT * FROM documents WHERE uuid = ?", (uuid,))
        else:
            cursor.execute("SELECT * FROM documents WHERE path = ?", (path,))

        doc = cursor.fetchone()
        if not doc:
            return json.dumps(
                {"error": f"未找到文档: {path or uuid}"}, ensure_ascii=False
            )

        doc_data = {
            "uuid": doc["uuid"],
            "path": doc["path"],
            "updated_at": doc["updated_at"],
        }
        doc_uuid = doc["uuid"]

        # 出边
        cursor.execute(
            "SELECT target_uuid, target_path, relations_json "
            "FROM links WHERE source_uuid = ?",
            (doc_uuid,),
        )
        outbound = [
            {
                "target_uuid": r["target_uuid"],
                "target_path": r["target_path"],
                "relations": json.loads(r["relations_json"]),
            }
            for r in cursor.fetchall()
        ]

        # 入边
        cursor.execute(
            "SELECT l.source_uuid, l.relations_json, d.path AS source_path "
            "FROM links l LEFT JOIN documents d ON l.source_uuid = d.uuid "
            "WHERE l.target_uuid = ?",
            (doc_uuid,),
        )
        inbound = [
            {
                "source_uuid": r["source_uuid"],
                "source_path": r["source_path"],
                "relations": json.loads(r["relations_json"]),
            }
            for r in cursor.fetchall()
        ]

        result: dict[str, Any] = {
            "document": doc_data,
            "outbound": outbound,
            "inbound": inbound,
        }

        # depth > 1：BFS 遍历多层出边
        if depth > 1:
            visited = {doc_uuid}
            queue = [(doc_uuid, 0)]
            levels = []
            while queue:
                current_uuid, current_depth = queue.pop(0)
                if current_depth >= depth:
                    continue
                cursor.execute(
                    "SELECT target_uuid, target_path, relations_json "
                    "FROM links WHERE source_uuid = ?",
                    (current_uuid,),
                )
                children = []
                for r in cursor.fetchall():
                    tuuid = r["target_uuid"]
                    if tuuid not in visited:
                        visited.add(tuuid)
                        children.append({
                            "uuid": tuuid,
                            "path": r["target_path"],
                            "relations": json.loads(r["relations_json"]),
                        })
                        queue.append((tuuid, current_depth + 1))
                if children:
                    levels.append({
                        "from_uuid": current_uuid,
                        "depth": current_depth + 1,
                        "children": children,
                    })
            result["extended"] = levels

        conn.close()
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"KG 查询失败: {e}"}, ensure_ascii=False)


def kg_list_all() -> str:
    """列出知识图谱中所有文档的路径和 UUID。"""
    try:
        conn = _get_kg_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT uuid, path, updated_at FROM documents ORDER BY path"
        )
        rows = cursor.fetchall()
        conn.close()

        docs = [
            {"uuid": r["uuid"], "path": r["path"], "updated_at": r["updated_at"]}
            for r in rows
        ]
        return json.dumps(
            {"total": len(docs), "documents": docs}, ensure_ascii=False
        )

    except Exception as e:
        return json.dumps(
            {"error": f"KG 列表查询失败: {e}"}, ensure_ascii=False
        )


def kg_search(keyword: str) -> str:
    """按关键词搜索知识图谱中的文档路径。"""
    if not keyword:
        return json.dumps({"error": "keyword 不能为空"}, ensure_ascii=False)
    try:
        conn = _get_kg_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT uuid, path, updated_at FROM documents "
            "WHERE path LIKE ? ORDER BY path",
            (f"%{keyword}%",),
        )
        rows = cursor.fetchall()
        conn.close()

        docs = [
            {"uuid": r["uuid"], "path": r["path"], "updated_at": r["updated_at"]}
            for r in rows
        ]
        return json.dumps(
            {"total": len(docs), "keyword": keyword, "documents": docs},
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps({"error": f"KG 搜索失败: {e}"}, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════════
#  MCP Server
# ═════════════════════════════════════════════════════════════════════════

_TOOLS = [
    Tool(
        name="kg_query",
        description=(
            "查询文档在知识图谱中的关联关系。"
            "查某篇文档引用/被引用了哪些其他文档，支持多层深度遍历。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文档相对路径，如 '笔记/财经分析/xxx.md'",
                },
                "uuid": {
                    "type": "string",
                    "description": "文档 UUID（与 path 二选一）",
                },
                "depth": {
                    "type": "integer",
                    "description": "查询深度，1=仅直接邻居（默认），2=邻居的邻居",
                    "default": 1,
                },
            },
        },
    ),
    Tool(
        name="kg_list_all",
        description="列出知识图谱中所有文档的路径和 UUID，用于浏览全貌。",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="kg_search",
        description="按关键词搜索知识图谱中的文档路径，快速定位相关文档。",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，匹配文档路径",
                },
            },
            "required": ["keyword"],
        },
    ),
]

server = Server("knowledge-graph")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return _TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    arguments = arguments or {}
    try:
        if name == "kg_query":
            result = kg_query(
                path=arguments.get("path"),
                uuid=arguments.get("uuid"),
                depth=arguments.get("depth", 1),
            )
        elif name == "kg_list_all":
            result = kg_list_all()
        elif name == "kg_search":
            result = kg_search(keyword=arguments.get("keyword", ""))
        else:
            result = json.dumps({"error": f"未知工具: {name}"})
        return [TextContent(type="text", text=result)]
    except Exception as e:
        error = json.dumps({"error": str(e)}, ensure_ascii=False)
        return [TextContent(type="text", text=error)]


async def main() -> None:
    if not _DEFAULT_DB.is_file():
        print(
            f"knowledge-graph MCP 提示：数据库尚未就绪（{_DEFAULT_DB}），"
            "查询时若库仍不存在会返回错误说明。",
            file=sys.stderr,
        )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
