---
name: archive
description: 归档知识库中的历史日期型文档。适用于整理超过 30 天的按日期落盘内容，保持目录结构并处理引用检查。
---

# 归档

## 范围

只处理 `knowledge/` 下按 `YYYY-MM-DD` 目录归档的文档。没有日期目录的长期笔记、体系定义、规则和已归档内容不自动处理。

超过 30 天的日期型文件进入候选列表。归档目标为仓库根目录：

```text
archive/{原相对路径}
```

## 流程

1. 调用 `archive-management.archive_list_candidates` 扫描候选。
2. 调用 `archive-management.archive_preview` 检查目标路径、冲突和引用。
3. 有引用时先修正引用；目标已存在或引用未处理时跳过。
4. 确认后调用 `archive-management.archive_move`。
5. 调用 `archive-management.archive_cleanup_empty_dirs` 清理归档后遗留的空日期目录（先 `dry_run: true` 预览，再以 `dry_run: false` 执行）。
6. 归档后按项目知识图谱流程同步旧路径和新路径。

归档不是删除，不覆盖已有文件；文件移动默认只预览。空目录清理是唯一可自动执行、无需用户确认的步骤，见下。

## 空目录清理

文件被移动后会在 `knowledge/` 留下空的日期目录，由 `archive_cleanup_empty_dirs` 负责清理。

- **不需要用户确认**：该步骤只删除空壳目录，不涉及任何文件内容；不需要确认，以免阻塞每日归档任务。
- 工具只删除**同时满足**以下条件的目录：位于 `YYYY-MM-DD` 日期目录内、完全为空（含隐藏文件）、`archive/` 下存在同相对路径目录（证明确实是归档遗留）、日期早于今天（避开当天任务）。
- 任一条件不满足的目录会保留，并在结果中以 `reason` 标明（如 `no_archive_counterpart`）。**不要把被跳过的目录手工删掉**：先在 `archive/` 侧核对内容去向，确认后再处理。
- 只读/只删 `knowledge/` 内的空目录；不动 `archive/`，不删除任何文件。
