# trade-management MCP 工具

本文件只列出当前 MCP 工具及其用途。参数定义、字段校验、事务行为、数据库结构和错误处理以 `/pi-trader/.pi/mcp-servers/trade/mcp_server.py` 的实际实现及 MCP 工具 schema 为准。

## 账户

- `account_list`：列出交易账户。
- `account_get`：查询指定账户详情和费率配置。
- `account_create`：创建交易账户。

费率对象至少包含 `version` 和 `rules`。`rules` 支持两种形式：按品种配置的嵌套形式（`etf` / `stock`），或现有账户使用的扁平形式；扁平形式直接包含 `commission_rate`、`stamp_tax_rate`（卖出印花税）、`transfer_fee_rate` 等字段。可选的 `defaults` 提供通用默认费率，`commission_min_fee` 或 `min_commission` 表示佣金最低收费。代码同时兼容 `stamp_duty_rate` 这一字段名。

## 交易

- `trade_list`：查询成交记录，可按账户、交易体系和证券代码筛选。
- `trade_get`：查询单笔成交详情。
- `trade_record`：登记已经发生且已确认的成交，并在同一事务中联动写入现金流水；不是下单工具。
- `trade_pnl`：按账户、证券和可选交易体系查询 FIFO 已实现盈亏、剩余持仓和可选的未实现盈亏。

## 持仓和组合快照

- `position_list`：查询指定账户和交易体系下的非零持仓、数量、平均成本和已实现盈亏。
- `portfolio_snapshot`：查询指定账户和交易体系下的现金、持仓和交易截止时间。

## 现金

- `cash_balance`：查询指定账户和交易体系的现金余额。
- `cash_list`：查询指定账户和交易体系的现金流水。

## 自选股

- `watchlist_list`：查询自选股，可按状态筛选。
- `watchlist_get`：查询指定证券的自选股详情。
- `watchlist_upsert`：创建或更新自选股及其体系关注信息；写入前必须获得用户明确确认。

## 工具选择提示

- 查询某体系当前现金和持仓：使用 `portfolio_snapshot`。
- 查询单只证券盈亏：使用 `trade_pnl`。
- 查询明细成交：使用 `trade_list` 或 `trade_get`。
- 登记已确认成交：使用 `trade_record`。
- 查询现金流水：使用 `cash_balance` 或 `cash_list`。
- 查询或维护观察标的：使用 `watchlist_list`、`watchlist_get` 或 `watchlist_upsert`。

本文件不提供旧 CLI、直接 SQL 或数据库文件操作说明。
