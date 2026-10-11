---
name: trade-management
description: 管理账户、交易流水、现金流水、自选股和盈亏统计。只通过 trade-management MCP 访问数据库；不直接执行 SQL 或 CLI。
---

# 交易管理技能

本技能是交易管理 MCP 的业务说明层。数据库位于 `/pi-trader/database/trade_management.db`，由 MCP 负责访问；技能不直接读写 SQLite。

## 工具选择

- 账户：`account_list`、`account_get`、`account_create`
- 交易：`trade_list`、`trade_get`、`trade_record`、`trade_pnl`
- 现金：`cash_balance`、`cash_list`
- 自选股：`watchlist_list`、`watchlist_get`、`watchlist_upsert`

## 使用规则

1. 查询账户、交易、现金或自选股时优先调用对应 MCP 工具，不要猜测数据库内容。
2. `trade_record` 只记录已经发生并由用户确认的成交，不提交券商订单。
3. `trade_record` 会在同一事务中写入交易和现金流水；调用成功后应向用户报告交易 ID、手续费和现金变动。
4. 记录交易前核对账户、`system_id`、证券代码、方向、数量、价格和成交时间。
5. 发现疑似重复交易时停止并向用户确认，不要重复调用。
6. 查询持仓或盈亏时使用 `trade_pnl`；未实现盈亏必须提供当前价格。
7. 现金余额使用 `cash_balance`，不要通过交易金额自行推算。
8. 只读工具可以自动调用；写入交易属于高风险操作，必须有用户明确成交确认。

## 安全边界

- 本 MCP 是交易账本，不是券商下单接口。
- 不得把 `trade_record` 当成真实下单操作。
- 不直接执行 `account_cli.py`、`trade_cli.py` 等旧 CLI。
- 不直接修改 SQLite 文件。
- 不把 API 密钥、账户凭据或完整数据库内容写进回答。
- 真实交易前必须经过独立的券商接口和人工确认流程。

## 输出要求

涉及交易记录时说明：账户、交易体系、证券、方向、数量、价格、时间和交易 ID。
涉及盈亏时区分：剩余数量、平均成本、已实现盈亏和未实现盈亏。
涉及现金时说明账户、交易体系、余额或流水金额。
