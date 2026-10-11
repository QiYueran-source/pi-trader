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
5. 归档后按项目知识图谱流程同步旧路径和新路径。

归档不是删除，不覆盖已有文件。默认只预览，不自动移动。
