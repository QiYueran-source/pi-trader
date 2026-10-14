# 内容整理

## 分类

- 午评、收评：`knowledge/事实/{date}/`，只保留客观数据，不录判断。
- 开源证券盘前分析、财经分析复盘及含未来判断的其他当前内容：`knowledge/交易/财经分析/{date}/`。

## 文件名

- 开源证券盘前分析：`开源证券-盘前分析.md`
- 财经分析复盘：`财经分析复盘.md`

同一来源、同一类型、同一日期只保留一个文件。按内容日期归档，不按整理日期归档。

> 和信证券及开源证券调仓信息已停止录入。历史文件、历史摘要和数据库记录保留，但不再作为当前来源扫描、整理或入库。

## 顺序

1. 先列出目标日期目录，读取已有文件。
2. 已有同名文件时，确认是补充还是覆盖。
3. 代码或名称不完整时先核实，不能确定就询问。
4. 按 `references/style.md` 整理 Markdown。
5. **入库前自检**：按 `references/mentions.md` 的「入库校验」逐条核对，并确认文件名 / 来源类型 / `mention_date` 三者自洽。
6. **先列出待入库清单**（一行一条）给用户确认。
7. 确认后写入：新记录用 `financial_analysis_record_mentions`，覆盖旧文件用 `financial_analysis_replace_mentions`；写后核对 `inserted/skipped/deleted` 并复核条数。

## Frontmatter

按 `knowledge-management` 规范生成（2026-10-13 全库统一后的字段）：

- 分析文件：`title`、`summary`、`date`、`tags`。
- 事实文件：另加 `source`；`date` 必需。

**`summary` 必填**，且必须能概括正文实际内容，不写空泛描述。
不再写 `uuid`、`updated`、`links`——全库已统一移除，不要把这三个字段加回新文件。
