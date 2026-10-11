# 复盘规则

复盘文件统一写入：`knowledge/笔记/财经分析/{date}/财经分析复盘.md`。

## 验证日期

- 盘前分析、盘前荐股、调仓信息：发布日期当天。
- 盘后荐股、周末要闻：下一交易日。

周一还要覆盖前一周末的周末要闻和盘后荐股；每天还要覆盖前一交易日的盘后荐股。不能只看当天 `mention_date`。

## 流程

1. 调用 `financial_analysis_active_items`。
2. 调用 `tushare-data.get_stock_daily` 或 `get_index_daily` 获取行情。
3. 调用 `financial_analysis_record_performance` 写入跟踪结果。
4. 对当天、前一交易日及周末记录调用 `financial_analysis_review_date`。
5. 汇总结果并写复盘 Markdown。

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

文件 frontmatter 的 `links` 只引用实际存在且有 UUID 的 Markdown 文件。
