# 判断记录规则

数据库由 `financial-analysis` MCP 管理，位置由 MCP 配置注入。技能不直接访问 SQLite。

## mentions 字段

- `name`：个股或板块名称。
- `code`：个股代码，必须带交易所后缀；板块可空。
- `type`：`stock` 或 `sector`。
- `mention_date`：内容发布日期。
- `source_type`：盘前分析、盘前荐股、盘后荐股、盘后分析、周末要闻、调仓信息。
- `source_file`：相对 `knowledge/` 的 Markdown 路径。
- `sentiment`：积极、中性、消极、谨慎。
- `context`：简短说明判断依据。
- `window_end_date`：跟踪窗口结束日。

## 提取

只记录对未来的明确判断：推荐个股、板块方向、风险判断和调仓建议。事实描述不录入。

- 周末要闻的“关注企业”按板块参考处理，通常记录为 `sector`。
- 盘前/盘后荐股中的明确推荐记录为 `stock`。
- 调仓移入记录为 `stock`，当天生效。

## 窗口

- 短线、近日、博弈、谨慎、风险：3 天。
- 无明确修饰：5 天。
- 趋势向好、主升、中期、延续：10 天。
- 长期、业绩驱动、政策、进口替代：44 天。

窗口从 `mention_date` 起算。写入前核对同来源历史记录，避免重复或错误窗口。

## 写入

- 新内容：调用 `financial_analysis_record_mentions`。
- 覆盖来源文件：调用 `financial_analysis_replace_mentions`，不要先手动删除。
- 先检查工具返回的 `inserted`、`skipped`、`deleted` 数量。
- 自动提取只作建议，必须结合原文人工确认。
