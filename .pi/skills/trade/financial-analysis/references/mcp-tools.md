# MCP 工具

服务名：`financial-analysis`

## 数据库工具

- `financial_analysis_list_mentions`：查询判断，可按日期、来源、名称、代码筛选。
- `financial_analysis_record_mentions`：批量新增判断，重复项自动跳过。
- `financial_analysis_replace_mentions`：按日期和来源文件原子替换判断。
- `financial_analysis_active_items`：查询仍在窗口内的个股和板块。
- `financial_analysis_record_performance`：批量写入行情跟踪。
- `financial_analysis_list_performance`：查询行情记录。
- `financial_analysis_review_date`：返回判断、验证日期和实际表现。
- `financial_analysis_stats`：统计方向判断准确率。

## 行情工具

服务名：`tushare-data`

- `get_stock_daily`：个股日线。
- `get_index_daily`：指数日线。
- `get_stock_basic`：核实股票名称和代码。
- `get_trade_calendar`：确定下一交易日。

## 约束

- 先读后写：写入前先 `financial_analysis_list_mentions` 查重，按「日期 + 来源文件」判断用 record 还是 replace。
- **先列清单再入库**：用户要求整理财经分析时，默认先把待入库清单列给用户，确认后才写库（字段与校验见 `mentions.md`）。
- 覆盖来源文件用 `financial_analysis_replace_mentions`，不要手动删除旧记录。
- 批量写入后核对返回的 `inserted` / `skipped` / `deleted`，再 `list_mentions` 复核条数。
- 数据库写入只使用业务工具，不执行任意 SQL。行情来源和日期必须与复盘对象一致。
- MCP 只校验必填与枚举；名称、代码、窗口、路径等口径由 `mentions.md` 的「入库校验」清单强制。
