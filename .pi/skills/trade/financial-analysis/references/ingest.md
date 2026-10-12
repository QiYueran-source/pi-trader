# 内容整理

## 分类

- 午评、收评：`knowledge/事实/{date}/`，只保留客观数据，不录判断。
- 盘前分析、盘前/盘后荐股、周末要闻、调仓：`knowledge/交易/财经分析/{date}/`。
- 含未来判断的其他内容：归入财经分析目录。

## 文件名

- 开源证券盘前分析：`开源证券-盘前分析.md`
- 和信证券盘前荐股：`和信证券-盘前荐股.md`
- 和信证券盘后荐股：`和信证券-盘后荐股.md`
- 和信证券周末要闻：`和信证券-周末要闻.md`
- 开源证券调仓信息：`开源证券-调仓信息.md`

同一来源、同一类型、同一日期只保留一个文件。按内容日期归档，不按整理日期归档。

## 顺序

1. 先列出目标日期目录，读取已有文件。
2. 已有同名文件时，确认是补充还是覆盖。
3. 代码或名称不完整时先核实，不能确定就询问。
4. 按 `references/style.md` 整理 Markdown。
5. **入库前自检**：按 `references/mentions.md` 的「入库校验」逐条核对，并确认文件名 / 来源类型 / `mention_date` 三者自洽。
6. **先列出待入库清单**（一行一条）给用户确认。
7. 确认后写入：新记录用 `financial_analysis_record_mentions`，覆盖旧文件用 `financial_analysis_replace_mentions`；写后核对 `inserted/skipped/deleted` 并复核条数。

## Frontmatter

分析文件至少包含：`uuid`、`title`、`tags`、`updated`、`links`。没有关联文件时使用 ``。每个 link 必须包含目标文件的 `uuid`、`path` 和 `relations`。

事实文件还需包含 `source` 和 `date`。
