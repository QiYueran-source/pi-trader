#!/usr/bin/env python3
"""交易管理 MCP 服务。

SQLite 仅作为内部账本；模型通过业务工具访问账户、交易、现金和自选股。
数据库路径由 TRADE_DB_PATH 指定，默认 /pi-trader/database/trade_management.db。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

DB_PATH = Path(os.getenv("TRADE_DB_PATH", "/pi-trader/database/trade_management.db"))
VALID_STATUS = {"watching", "candidate", "trading"}
VALID_SIDE = {"buy", "sell"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.is_file():
        raise RuntimeError(f"交易数据库不存在：{DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


def validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")


def parse_fee(raw: str) -> dict[str, Any]:
    try:
        fee = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"账户费率不是合法 JSON：{exc}") from exc
    if not isinstance(fee, dict) or "version" not in fee or "rules" not in fee:
        raise ValueError("账户费率必须包含 version 和 rules")
    return fee


def instrument_type(code: str) -> str:
    return "etf" if code.startswith(("51", "15", "16")) else "stock"


def calc_fee(fee: dict[str, Any], code: str, side: str, qty: float, price: float) -> float:
    rules = fee.get("rules", {})
    rule = dict(fee.get("defaults", {}))
    rule.update(rules.get(instrument_type(code), {}))
    amount = qty * price
    minimum = rule.get("commission_min_fee", rule.get("min_commission", 0))
    commission = max(amount * rule.get("commission_rate", 0), minimum)
    stamp = amount * rule.get("stamp_duty_rate", 0) if side == "sell" else 0
    transfer = amount * rule.get("transfer_fee_rate", 0)
    other = amount * rule.get("other_fee_rate", 0)
    return round(commission + stamp + transfer + other, 2)


def account_list() -> dict[str, Any]:
    with db() as conn:
        return {"accounts": rows(conn.execute("SELECT id,name,note,created_at,updated_at FROM account ORDER BY created_at"))}


def account_get(account_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM account WHERE id = ?", (account_id,)).fetchone()
        if not row:
            return {"error": f"账户不存在：{account_id}"}
        item = dict(row)
        item["fee"] = parse_fee(item["fee"])
        return item


def account_create(account_id: str, name: str, fee: dict[str, Any], note: str = "") -> dict[str, Any]:
    if not account_id or not name:
        raise ValueError("account_id 和 name 不能为空")
    parse_fee(_json(fee))
    with db() as conn:
        try:
            conn.execute("INSERT INTO account(id,name,fee,note) VALUES(?,?,?,?)", (account_id, name, _json(fee), note))
        except sqlite3.IntegrityError as exc:
            return {"error": f"账户已存在：{account_id}", "detail": str(exc)}
    return {"status": "created", "account_id": account_id}


def trade_list(account_id: str | None = None, system_id: str | None = None, code: str | None = None) -> dict[str, Any]:
    query = "SELECT id,account_id,system_id,code,name,side,quantity,price,occurred_at,note FROM trade"
    conditions: list[str] = []
    params: list[Any] = []
    for field, value in (("account_id", account_id), ("system_id", system_id), ("code", code)):
        if value:
            conditions.append(f"{field} = ?")
            params.append(value)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY occurred_at, id"
    with db() as conn:
        result = rows(conn.execute(query, params))
    return {"total": len(result), "trades": result}


def trade_get(trade_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM trade WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else {"error": f"交易不存在：{trade_id}"}


def cash_balance(account_id: str, system_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT COALESCE(SUM(amount),0) AS balance FROM cash_flow WHERE account_id=? AND system_id=?", (account_id, system_id)).fetchone()
    return {"account_id": account_id, "system_id": system_id, "balance": round(row["balance"], 2)}


def cash_list(account_id: str, system_id: str, limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    with db() as conn:
        result = rows(conn.execute("SELECT id,amount,occurred_at,reason FROM cash_flow WHERE account_id=? AND system_id=? ORDER BY occurred_at DESC,id DESC LIMIT ?", (account_id, system_id, limit)))
    return {"total": len(result), "flows": result}


def trade_pnl(account_id: str, code: str, system_id: str | None = None, current_price: float | None = None) -> dict[str, Any]:
    with db() as conn:
        account = conn.execute("SELECT fee FROM account WHERE id=?", (account_id,)).fetchone()
        if not account:
            return {"error": f"账户不存在：{account_id}"}
        query = "SELECT side,quantity,price,occurred_at FROM trade WHERE account_id=? AND code=?"
        params: list[Any] = [account_id, code]
        if system_id:
            query += " AND system_id=?"
            params.append(system_id)
        trades = rows(conn.execute(query + " ORDER BY occurred_at,id", params))
    if not trades:
        return {"error": "没有匹配的交易记录", "account_id": account_id, "code": code}
    fee_rules = parse_fee(account["fee"])
    queue: list[list[float]] = []
    closed = 0.0
    for item in trades:
        fee = calc_fee(fee_rules, code, item["side"], item["quantity"], item["price"])
        if item["side"] == "buy":
            queue.append([item["quantity"], item["price"], fee])
            continue
        remain = item["quantity"]
        while remain > 1e-10 and queue:
            q, buy_price, buy_fee = queue[0]
            matched = min(remain, q)
            closed += matched * item["price"] - matched * buy_price - buy_fee * matched / q - fee * matched / item["quantity"]
            queue[0][0] -= matched
            queue[0][2] -= buy_fee * matched / q
            remain -= matched
            if queue[0][0] <= 1e-10:
                queue.pop(0)
    remaining = sum(x[0] for x in queue)
    cost = sum(x[0] * x[1] for x in queue)
    result: dict[str, Any] = {"account_id": account_id, "code": code, "system_id": system_id, "remaining_quantity": round(remaining, 6), "closed_pnl": round(closed, 2), "average_cost": round(cost / remaining, 4) if remaining else 0}
    if remaining and current_price is not None:
        sell_fee = calc_fee(fee_rules, code, "sell", remaining, current_price)
        result["unclosed_pnl"] = round(remaining * current_price - cost - sum(x[2] for x in queue) - sell_fee, 2)
        result["total_pnl"] = round(closed + result["unclosed_pnl"], 2)
    return result


def position_list(account_id: str, system_id: str) -> dict[str, Any]:
    """按账户和体系返回全部非零持仓，供计划与复盘使用。"""
    trades = trade_list(account_id=account_id, system_id=system_id)["trades"]
    codes = sorted({item["code"] for item in trades})
    positions: list[dict[str, Any]] = []
    for code in codes:
        pnl = trade_pnl(account_id, code, system_id)
        if pnl.get("remaining_quantity", 0) <= 0:
            continue
        name = next(item["name"] for item in reversed(trades) if item["code"] == code)
        positions.append({"code": code, "name": name, "quantity": pnl["remaining_quantity"], "average_cost": pnl["average_cost"], "closed_pnl": pnl["closed_pnl"]})
    return {"account_id": account_id, "system_id": system_id, "positions": positions, "as_of": trades[-1]["occurred_at"] if trades else None}


def portfolio_snapshot(account_id: str, system_id: str) -> dict[str, Any]:
    """返回同一账户体系下可追溯的现金、持仓和交易截止时间快照。"""
    positions = position_list(account_id, system_id)
    cash = cash_balance(account_id, system_id)
    return {"account_id": account_id, "system_id": system_id, "cash": cash["balance"], "positions": positions["positions"], "trade_as_of": positions["as_of"]}


def trade_record(account_id: str, system_id: str, code: str, name: str, side: str, quantity: float, price: float, occurred_at: str, note: str = "") -> dict[str, Any]:
    if side not in VALID_SIDE:
        raise ValueError("side 必须是 buy 或 sell")
    validate_positive("quantity", quantity)
    validate_positive("price", price)
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", occurred_at):
        raise ValueError("occurred_at 格式必须为 YYYY-MM-DD HH:MM:SS")
    with db() as conn:
        account = conn.execute("SELECT fee FROM account WHERE id=?", (account_id,)).fetchone()
        if not account:
            return {"error": f"账户不存在：{account_id}"}
        fee = calc_fee(parse_fee(account["fee"]), code, side, quantity, price)
        amount = quantity * price
        if side == "buy":
            cash_amount = -(amount + fee)
        else:
            cash_amount = amount - fee
        duplicate = conn.execute("SELECT id FROM trade WHERE account_id=? AND system_id=? AND code=? AND side=? AND occurred_at=? AND quantity=? AND price=?", (account_id, system_id, code, side, occurred_at, quantity, price)).fetchone()
        if duplicate:
            return {"error": f"疑似重复交易，已有记录 #{duplicate['id']}"}
        cur = conn.execute("INSERT INTO trade(account_id,system_id,code,name,side,quantity,price,occurred_at,note) VALUES(?,?,?,?,?,?,?,?,?)", (account_id, system_id, code, name, side, quantity, price, occurred_at, note))
        trade_id = cur.lastrowid
        conn.execute("INSERT INTO cash_flow(account_id,system_id,amount,occurred_at,reason) VALUES(?,?,?,?,?)", (account_id, system_id, round(cash_amount, 2), occurred_at, f"{'买入' if side == 'buy' else '卖出'} {code} {quantity}@{price} (trade#{trade_id})"))
    return {"trade_id": trade_id, "fee": fee, "cash_amount": round(cash_amount, 2), "status": "recorded"}


def watchlist_get(code: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM watchlist WHERE code=?", (code,)).fetchone()
    if not row:
        return {"error": f"自选股不存在：{code}"}
    item = dict(row)
    try:
        item["systems"] = json.loads(item["systems"])
    except (TypeError, json.JSONDecodeError):
        pass
    return item


def watchlist_upsert(code: str, name: str, status: str, systems: list[dict[str, Any]], reason: str = "") -> dict[str, Any]:
    if not code or not name:
        raise ValueError("code 和 name 不能为空")
    if status not in VALID_STATUS:
        raise ValueError(f"status 必须是 {sorted(VALID_STATUS)} 之一")
    if not isinstance(systems, list) or any(not isinstance(item, dict) or not {"id", "name", "reason"}.issubset(item) for item in systems):
        raise ValueError("systems 必须是包含 id、name、reason 的对象数组")
    with db() as conn:
        existing = conn.execute("SELECT code FROM watchlist WHERE code=?", (code,)).fetchone()
        if existing:
            conn.execute("UPDATE watchlist SET name=?,status=?,systems=?,reason=?,updated_at=CURRENT_TIMESTAMP WHERE code=?", (name, status, _json(systems), reason, code))
            result = "updated"
        else:
            conn.execute("INSERT INTO watchlist(code,name,status,systems,reason) VALUES(?,?,?,?,?)", (code, name, status, _json(systems), reason))
            result = "created"
    return {"status": result, "code": code}


def watchlist_list(status: str | None = None) -> dict[str, Any]:
    if status and status not in VALID_STATUS:
        raise ValueError(f"status 必须是 {sorted(VALID_STATUS)} 之一")
    with db() as conn:
        if status:
            result = rows(conn.execute("SELECT * FROM watchlist WHERE status=? ORDER BY updated_at DESC", (status,)))
        else:
            result = rows(conn.execute("SELECT * FROM watchlist ORDER BY updated_at DESC"))
    for item in result:
        try:
            item["systems"] = json.loads(item["systems"])
        except (TypeError, json.JSONDecodeError):
            pass
    return {"total": len(result), "watchlist": result}


TOOLS = [
    Tool(name="account_list", description="列出交易账户。", inputSchema={"type":"object","properties":{}}),
    Tool(name="account_get", description="查看账户详情和费率。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"}},"required":["account_id"]}),
    Tool(name="account_create", description="创建交易账户。需要提供包含 version 和 rules 的费率对象。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"name":{"type":"string"},"fee":{"type":"object"},"note":{"type":"string"}},"required":["account_id","name","fee"]}),
    Tool(name="trade_list", description="查询交易记录，可按账户、体系、证券代码筛选。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"},"code":{"type":"string"}}}),
    Tool(name="trade_get", description="查看单笔交易。", inputSchema={"type":"object","properties":{"trade_id":{"type":"integer"}},"required":["trade_id"]}),
    Tool(name="trade_record", description="记录已经发生的成交，并在同一事务中写入对应现金流水。不是券商下单工具。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"},"code":{"type":"string"},"name":{"type":"string"},"side":{"type":"string","enum":["buy","sell"]},"quantity":{"type":"number"},"price":{"type":"number"},"occurred_at":{"type":"string"},"note":{"type":"string"}},"required":["account_id","system_id","code","name","side","quantity","price","occurred_at"]}),
    Tool(name="trade_pnl", description="按 FIFO 计算单只证券的已实现和未实现盈亏。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"code":{"type":"string"},"system_id":{"type":"string"},"current_price":{"type":"number"}},"required":["account_id","code"]}),
    Tool(name="position_list", description="查询账户在指定体系下的全部非零持仓与成本。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"}},"required":["account_id","system_id"]}),
    Tool(name="portfolio_snapshot", description="查询账户在指定体系下的现金、持仓和交易截止时间。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"}},"required":["account_id","system_id"]}),
    Tool(name="cash_balance", description="查询账户某交易体系的现金余额。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"}},"required":["account_id","system_id"]}),
    Tool(name="cash_list", description="查询现金流水。", inputSchema={"type":"object","properties":{"account_id":{"type":"string"},"system_id":{"type":"string"},"limit":{"type":"integer","default":20}},"required":["account_id","system_id"]}),
    Tool(name="watchlist_list", description="查询自选股，可按状态筛选。", inputSchema={"type":"object","properties":{"status":{"type":"string","enum":sorted(VALID_STATUS)}}}),
    Tool(name="watchlist_get", description="查看单只自选股。", inputSchema={"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}),
    Tool(name="watchlist_upsert", description="创建或更新自选股。写入前必须获得用户明确确认。", inputSchema={"type":"object","properties":{"code":{"type":"string"},"name":{"type":"string"},"status":{"type":"string","enum":sorted(VALID_STATUS)},"systems":{"type":"array","items":{"type":"object"}},"reason":{"type":"string"}},"required":["code","name","status","systems"]}),
]

server = Server("trade-management")

@server.list_tools()
async def list_tools() -> list[Tool]: return TOOLS

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    a = arguments or {}
    try:
        dispatch = {"account_list": lambda: account_list(), "account_get": lambda: account_get(a["account_id"]), "account_create": lambda: account_create(a["account_id"], a["name"], a["fee"], a.get("note", "")), "trade_list": lambda: trade_list(a.get("account_id"), a.get("system_id"), a.get("code")), "trade_get": lambda: trade_get(int(a["trade_id"])), "trade_record": lambda: trade_record(**a), "trade_pnl": lambda: trade_pnl(a["account_id"], a["code"], a.get("system_id"), a.get("current_price")), "position_list": lambda: position_list(a["account_id"], a["system_id"]), "portfolio_snapshot": lambda: portfolio_snapshot(a["account_id"], a["system_id"]), "cash_balance": lambda: cash_balance(a["account_id"], a["system_id"]), "cash_list": lambda: cash_list(a["account_id"], a["system_id"], a.get("limit", 20)), "watchlist_list": lambda: watchlist_list(a.get("status")), "watchlist_get": lambda: watchlist_get(a["code"]), "watchlist_upsert": lambda: watchlist_upsert(a["code"], a["name"], a["status"], a["systems"], a.get("reason", ""))}
        if name not in dispatch: return [TextContent(type="text", text=_json({"error": f"未知工具：{name}"}))]
        return [TextContent(type="text", text=_json(dispatch[name]()))]
    except Exception as exc:
        return [TextContent(type="text", text=_json({"error": str(exc)}))]

async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__": asyncio.run(main())
