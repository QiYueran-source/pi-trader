# 复盘规则

复盘文件统一写入：`knowledge/交易/财经分析/{date}/财经分析复盘.md`。

## 验证日期

- 当前开源证券盘前分析：发布日期当天。
- 历史来源记录：按原有发布日期、验证日期和窗口复核，不因来源停止录入而删除或改写。

复盘时仍需覆盖有效窗口内的历史判断，不能只查询当前来源。

## 流程

1. 调用 `financial_analysis_active_items`。
2. 调用 `tushare-data.get_stock_daily` 或 `get_index_daily` 获取行情。
3. 调用 `financial_analysis_record_performance` 写入跟踪结果。
4. 对当天、前一交易日及周末记录调用 `financial_analysis_review_date`。
5. 汇总结果并写复盘 Markdown。
6. 按 `summary` 技能写一条简报到 `knowledge/摘要/.abstract/`。

### 跨窗口复核（工具不支持，需人工）

`stats` 只在同一天做 name 对齐（`mention_date = track_date`），`review_date` 只查单个 `mention_date`，两者都**不能**回答「上周发布的判断今天表现如何」。跨窗口复核必须人工组合：

1. `list_mentions(mention_date=发布日)` 取回待复核记录；
2. 对每条标的 `list_performance(name=…, track_date=验证日)` 或直接取行情；
3. 对照结果写进复盘的「跨窗口项」段落，并注明是人工拼接而非工具直接给出。

## 统计

调用 `financial_analysis_stats` 获取方向判断准确率。中性判断和无数据记录不计入准确率。

- 积极 + 上涨：正确。
- 谨慎/消极 + 下跌：正确。
- 其余有数据判断：错误。
- 板块没有可靠指数或代理数据时，标记为定性验证，不伪造行情。

## 复盘格式

正文按来源分段，至少包含：

- 大盘背景；
- 判断与实际表现；
- 出入分析；
- 命中率统计；
- 总结。

文件 frontmatter 按 `knowledge-management` 规范：`title`、`summary`、`date`、`tags`；不写 `uuid`、`links`。
