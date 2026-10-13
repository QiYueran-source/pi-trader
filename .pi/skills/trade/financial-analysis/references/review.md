# 复盘规则

复盘文件统一写入：`knowledge/交易/财经分析/{date}/财经分析复盘.md`。

## 验证日期

- 盘前分析、盘前荐股、调仓信息：发布日期当天。
- 盘后荐股、周末要闻：下一交易日。

周一还要覆盖前一周末的周末要闻和盘后荐股；每天还要覆盖前一交易日的盘后荐股。不能只看当天 `mention_date`。

> ⚠️ `review_date` 内部按**自然日 +1** 推算盘后荐股/周末要闻的验证日，**不排除周末与节假日**（周五发布 → 验证日落到周六）。遇到这种情况必须先用 `tushare-data.get_trade_calendar` 校正到真实的下一交易日，不要在技能层信任工具给出的 `check_date`。

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
