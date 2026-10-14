---
name: financial-analysis
description: 整理开源证券盘前分析和财经分析复盘，维护判断记录并生成复盘。分析、整理、记录或复盘当前财经信息时必须使用。
tags:
  - 财经分析
  - 复盘
  - 判断跟踪
---

# 财经分析

## 触发

以下内容必须使用本技能：开源证券盘前分析、财经分析复盘、投顾观点、复盘，以及“整理/记录/保存”财经分析。历史来源文件和历史判断记录仅用于查询、复盘和统计，不再产生新的和信证券或调仓信息内容。

## 流程

### 整理新内容

1. 先扫描 `knowledge/交易/财经分析/{date}/`，优先使用本地文件，不主动搜索原文。
2. 判断类型：收评/午评放入 `knowledge/事实/{date}/`；含未来判断的内容放入 `knowledge/交易/财经分析/{date}/`。
3. 按 `references/ingest.md` 命名和写入 Markdown，按 `references/style.md` 排版。
4. 从正文提取个股、板块、情绪、判断窗口，按 `references/mentions.md` 的「入库校验」逐条核对（名称、代码、窗口、路径都要过）。
5. **先列出待入库清单给用户确认**，确认后再入库：新内容用 `financial_analysis_record_mentions`；覆盖旧文件用 `financial_analysis_replace_mentions`。
6. 落盘与入库完成后，按 `summary` 技能写一条简报到 `knowledge/摘要/.abstract/`。

### 复盘

1. 调用 `financial_analysis_active_items` 查询有效跟踪项。
2. 用 `tushare-data` 获取个股或指数行情。
3. 调用 `financial_analysis_record_performance` 保存行情。
4. 调用 `financial_analysis_review_date` 获取复盘数据。
5. 将结果写入 `knowledge/交易/财经分析/{date}/财经分析复盘.md`。
6. 按 `summary` 技能写一条简报到 `knowledge/摘要/.abstract/`。

## 时间规则

- 盘前分析：当天验证。
- 历史来源记录按原有 `mention_date` 和窗口继续复盘，不因来源停止录入而删除或改写。
- `window_end_date` 从发布日期计算，不因验证日期改变。

## 判断规则

- 个股：`type=stock`，代码必须带 `.SH`、`.SZ` 或 `.BJ`；板块或指数：`type=sector`，代码可为空。
- 情绪仅使用：积极、中性、消极、谨慎。
- 名称或代码不完整时，先核实，无法确认就询问用户。
- **先列清单再入库**：用户要求整理财经分析时，先把待入库信息列出来，得到确认后才写库。
- MCP 只校验必填与枚举；名称形态、代码格式、窗口天数、路径真实性等口径由 `references/mentions.md` 的「入库校验」强制。
- 自动提取结果必须人工核对（每条都能对上原文一句话），不能直接信任。

## MCP 工具

财经数据库工具见 `references/mcp-tools.md`；行情工具使用 `tushare-data`。

数据库写入必须使用业务工具，不执行任意 SQL，不直接运行旧脚本。详细字段和窗口规则见 `references/mentions.md`，复盘规则见 `references/review.md`。

## 边界

- 目录类型与 Frontmatter 以 `knowledge-management` 为准；本技能只负责分析与判断入库。
- 本技能不负责交易下单、密钥管理、自动重试、自动回滚或复杂任务调度。
