---
name: archive
description: 归档知识库中的历史日期型文档。适用于整理超过 30 天的按日期落盘内容，保持目录结构，改写引用，并清理归档遗留的空目录。
---

# 归档

## 范围

只处理 `knowledge/` 下按 `YYYY-MM-DD` 目录归档的文档。没有日期目录的长期笔记、体系定义、规则和已归档内容不自动处理。

`摘要/摘要_*.md`、`笔记/**` 等长期文档本身不归档，但它们引用被归档文件时，其引用会被改写（见「引用处理」）。

超过 30 天的日期型文件进入候选列表。归档目标是仓库根目录，保持原相对路径：

```text
archive/{原相对路径}
```

`archive/` **不在版本管理**（`.gitignore` 忽略）：归档在 git 层面等同于从当前树删除，内容只能从历史提交追回。改写后的引用指向的也是这个本地目录。

## 工具

| 工具 | 作用 | 默认 |
|:---|:---|:---|
| `archive_list_candidates(before_date)` | 列出日期 ≤ `before_date` 的日期型文档 | 不传则取 30 天前 |
| `archive_preview(path)` | 预览目标路径、冲突与引用 | — |
| `archive_move(path, rewrite_references)` | 移动单个文件；`rewrite_references=true` 时先改写引用再移动 | 有引用时拒绝移动 |
| `archive_rewrite_references(path, apply)` | 把引用改写为 `archive/<path>` | `apply=false` 只预览 |
| `archive_run(before_date, rewrite_references, dry_run, include_paths)` | 批量：候选 → 预览 →（改写）→ 移动 → 清理空目录 | `dry_run=true` 只干跑 |
| `archive_cleanup_empty_dirs(dry_run)` | 清理归档遗留的空日期目录 | `dry_run=true` 只预览 |

## 流程

**批量（常规做法）**

1. 先干跑：`archive_run(before_date, rewrite_references, dry_run=true)`，看候选数、将归档数、跳过原因、将改写的文件数与替换数。
2. 需要完整清单时加 `include_paths=true`。
3. 确认后用 `dry_run=false` 执行；工具内部按「预览 → 改写 → 复查引用归零 → 移动 → 清理空目录」顺序处理，失败会记入 `skipped`。

**单文件（精细操作）**：`archive_preview` → 需要时 `archive_rewrite_references(apply=true)` → `archive_move` → `archive_cleanup_empty_dirs`。

归档不是删除，不覆盖已有文件；所有移动与改写默认只预览。**空目录清理是唯一无需用户确认、可自动执行的步骤**（见下）。

## 引用处理

- `rewrite_references=false`（默认）：被引用的文件**跳过**并在结果里记为 `references`，保持历史行为。
- `rewrite_references=true`：先把引用改写为 `archive/<原相对路径>`，复查引用归零后再移动。这样历史引用仍可定位，只是指向归档目录。
- 改写口径：精确路径字符串替换（同一字符串匹配口径，不做模糊匹配）；只改 `knowledge/` 下 `.md/.yaml/.yml/.json`；跳过被引用文件自身；已带 `archive/` 前缀的写法不再重复改写（幂等）。
- 引用判定与改写同口径：`archive/<path>` 里包含的旧路径**不**算未改写引用。
- 改写会修改摘要、长期笔记等文档的正文（只动路径字符串）。执行前先用 `archive_rewrite_references(apply=false)` 或 `archive_run(dry_run=true)` 预览改写清单。
- 由于 `archive/` 不入库，改写后的引用在他人克隆的仓库里打不开；如需保留可移植的引用，改用「跳过」而不是改写。

## 空目录清理

文件被移动后会在 `knowledge/` 留下空的日期目录，由 `archive_cleanup_empty_dirs` 负责清理。

- **不需要用户确认**：该步骤只删除空壳目录，不涉及任何文件内容；不需要确认，以免阻塞每日归档任务。
- 工具只删除**同时满足**以下条件的目录：位于 `YYYY-MM-DD` 日期目录内、完全为空（含隐藏文件）、`archive/` 下存在同相对路径目录（证明确实是归档遗留）、日期早于今天（避开当天任务）。
- 任一条件不满足的目录会保留，并在结果中以 `reason` 标明（如 `no_archive_counterpart`）。**不要把被跳过的目录手工删掉**：先在 `archive/` 侧核对内容去向，确认后再处理。
- 只读/只删 `knowledge/` 内的空目录；不动 `archive/`，不删除任何文件。

## 生效前提

归档 MCP 的代码或工具变更后，需要**重启 Pi** 才会在会话与定时任务中生效（MCP 只在启动时加载）。重启前调用新工具会报「工具不存在」，任务应按降级路径跳过并说明。
