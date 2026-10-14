---
name: archive
description: 归档知识库中的历史日期型文档和每日摘要。整理超过 30 天的日期型知识库内容、执行归档或清理归档遗留目录时必须使用。
---

# 归档

## 范围

只处理 `knowledge/` 下明确具有日期归档身份的文件：

1. 路径中包含合法 `YYYY-MM-DD` 日期目录的文件；
2. `摘要/摘要_YYYY-MM-DD.md` 格式的每日摘要。

归档目标是仓库根目录，保持原相对路径：

```text
archive/{原相对路径}
```

`摘要/.abstract/` 是临时简报目录，不属于正式摘要，不纳入本技能的归档候选。没有日期目录的长期笔记、体系定义、规则和其他长期文件不自动处理。

`archive/` 不在版本管理。归档是文件物理位置变化，不是动态知识身份变化；文档的逻辑路径保持不变。

## 工具

| 工具 | 作用 | 默认 |
|:---|:---|:---|
| `archive_list_candidates(before_date)` | 列出截止日期以前的日期型文档和每日摘要 | 不传则取 30 天前 |
| `archive_preview(path)` | 预览目标路径和目标冲突 | — |
| `archive_move(path)` | 移动单个日期型文档或每日摘要，不覆盖目标文件 | — |
| `archive_run(before_date, dry_run, include_paths)` | 批量发现、移动文件，并在实跑后清理空日期目录 | `dry_run=true` 只干跑 |
| `archive_cleanup_empty_dirs(dry_run)` | 清理归档遗留的空日期目录 | `dry_run=true` 只预览 |

## 流程

**批量归档：**

1. 先调用 `archive_run(dry_run=true)`，查看候选数、预计归档数和跳过原因；
2. 干跑结果正常后，用相同的 `before_date` 调用 `archive_run(dry_run=false)`；
3. 实跑会移动文件，并清理符合条件的归档遗留空日期目录；
4. 汇报候选数、归档数、跳过原因、清理空目录数和异常明细。

**单文件归档：**

```text
archive_preview → archive_move → archive_cleanup_empty_dirs
```

归档不覆盖已有文件。目标已存在时跳过并报告。归档不因为文件被其他文档引用而阻止移动。

## 文件移动规则

- 源文件必须位于 `knowledge/` 内；
- 源文件必须属于有效日期目录，或符合 `摘要/摘要_YYYY-MM-DD.md`；
- 目标为 `archive/` 下与源文件相同的相对路径；
- 只移动文件，不移动目录；
- 不修改文件正文；
- 不改写引用路径；
- 不修改数据库或任何数据库来源字段；
- 不执行目录别名迁移或其他路径同步。

动态知识使用逻辑路径。文件从 `knowledge/` 移到 `archive/` 后，逻辑路径保持不变；路径解析和引用检查由 `knowledge-management` 及 `logic-path` 负责，不由归档 MCP 承担。

## 空目录清理

文件移动后，必须通过 `archive-management` MCP 的 `archive_cleanup_empty_dirs` 工具处理 `knowledge/` 中可能遗留的空目录。不得使用 Bash、`find`、`rm` 或其他直接文件系统命令清理目录。清理只涉及目录，不涉及任何文件。

单文件归档时：

1. 先调用 `archive_cleanup_empty_dirs(dry_run=true)`，查看待清理清单和跳过原因；
2. 确认清单正常后，再调用 `archive_cleanup_empty_dirs(dry_run=false)` 实际清理；
3. 汇报实际清理数量，以及被保留目录和原因。

批量归档时，`archive_run(dry_run=false)` 已自动执行空目录清理，不需要再次调用 `archive_cleanup_empty_dirs`。

清理工具只处理：

- `knowledge/` 内的空目录；
- 目录自身或父级必须包含合法 `YYYY-MM-DD` 日期目录；
- `archive/` 下必须存在相同相对路径的对应目录，证明它是归档遗留目录；
- 日期必须早于当天，避免与当天任务竞争；
- 按目录深度自底向上处理嵌套目录。

工具不会删除文件、非空目录或 `archive/` 内的任何内容。`dry_run=true` 只返回待清理清单，`dry_run=false` 才实际删除目录。如果目录不满足条件，保留目录并报告原因，例如 `no_archive_counterpart` 或 `not_older_than_today`。

## 定时任务

每天归档任务先干跑、后实跑。定时任务不再调用引用改写工具、财经分析数据库同步工具或其他路径迁移工具。MCP 代码或工具变更后，需要重启 Pi 才会在会话和定时任务中生效。
