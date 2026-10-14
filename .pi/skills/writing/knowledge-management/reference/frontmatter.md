# Frontmatter

新建或主动整理的 Markdown 文档使用以下最小格式：

```yaml
---
title: 文档标题
summary: 用一两句话概括文档的核心内容、结论或用途
date: YYYY-MM-DD
tags:
  - 分类标签
---
```

## 字段

- `title`：与正文主题一致的标题。
- `summary`：必须存在，准确概括正文的核心内容。
- `date`：内容发生、记录或整理的日期，格式为 `YYYY-MM-DD`。
- `tags`：辅助分类和检索的标签列表，没有合适标签时使用 `tags: []`。

旧文档中仍然存在旧的uuid、updated、links等字段。历史文档保留原格式；迁移路径或补充内容时，不要求批量改写。新建文档和主动整理的文档使用本文件定义的格式，由archive归档即可。  


