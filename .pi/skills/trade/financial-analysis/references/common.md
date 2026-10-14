# 财经分析公共规则

本文件只保存所有专业财经来源共用的规则。来源主体的整理、录入、跟踪和复盘差异放在 `references/source/` 下对应文件中。

## 专业来源边界

- 只有证券公司、投顾机构或其他明确专业财经来源才能进入本技能。
- 用户口述、主观交易观点、交易意图和体系内部判断不进入专业财经判断数据库。
- 已停止来源只能按历史规则查询、复盘和统计，不能新增。

## 动态知识与来源字段

- 新分析文档按 `knowledge-management` 规则写入 `knowledge/`。
- 文档和数据库中的 `source_file` 使用逻辑路径，不带 `knowledge/` 或 `archive/` 前缀。
- 归档只改变物理位置，不修改逻辑来源路径。
- `source_file` 必须能通过 `logic-path` MCP 唯一解析；无法确认唯一目标时停止依赖该路径的写入。

## 判断记录字段

每条专业判断至少包含：

- `name`：可跟踪的个股或板块名称；
- `code`：个股必须带 `.SH`、`.SZ` 或 `.BJ` 后缀，板块可以为空；
- `type`：`stock` 或 `sector`；
- `mention_date`：内容发布日期；
- `source_type`：来源内部的内容类型；
- `source_file`：专业来源文件的逻辑路径；
- `sentiment`：积极、中性、消极或谨慎；
- `context`：能够被原文直接支持的简短片段，不改写、不编造；
- `window_end_date`：按来源规则和判断语义计算的跟踪截止日期。

## 通用写入流程

1. 先读取来源原文和同日已有文件。
2. 按来源规则提取明确的未来判断；没有明确判断不录入。
3. 核对个股代码与名称，代码有疑问时使用行情 MCP 查询，无法确认则停止。
4. 计算并填写 `window_end_date`。
5. 先列待入库清单，得到用户确认后才写入。
6. 使用 `financial_analysis_list_mentions` 查重。
7. 新来源文件使用 `financial_analysis_record_mentions`；覆盖同一来源、同一日期文件使用 `financial_analysis_replace_mentions`。
8. 写入后核对 `inserted`、`skipped`、`deleted`，再查询复核。

## 通用复盘流程

1. 按来源和 `source_file` 查询有效判断。
2. 使用 `tushare-data` 获取对应个股、指数或可靠代理行情。
3. 使用 `financial_analysis_record_performance` 保存验证事实。
4. 使用 `financial_analysis_review_date` 获取来源判断与表现。
5. 使用 `financial_analysis_stats` 获取该来源统计；不同来源必须分别统计。
6. 将结果写入来源独立的复盘文档。
7. 区分已验证、未到验证日、无行情和无可靠板块代理，不把缺失数据当作错误。

## 统计口径

- 积极且上涨：正确；
- 谨慎或消极且下跌：正确；
- 中性、无行情或无可靠板块代理：不计入分母；
- 其他有可靠数据的方向判断：错误。

来源命中率必须单独计算；跨来源汇总只能作为额外总览，不能替代来源独立统计。
