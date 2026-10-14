# logic-path MCP

`logic-path` 为动态知识逻辑路径提供统一的格式校验和双头解析。它实现 `knowledge-management/reference/path-protocol.md` 中的路径协议，不负责移动文件、改写引用或迁移数据库。

## 配置

服务通过环境变量读取两个动态知识物理根目录：

```text
KNOWLEDGE_ROOT=/pi-trader/knowledge
ARCHIVE_ROOT=/pi-trader/archive
```

逻辑路径不带 `knowledge/` 或 `archive/` 前缀，例如：

```text
交易/交易复盘/2026-10-14/整体复盘.md
```

## 工具

### `logic_path_resolve`

输入一个逻辑路径，同时检查 `knowledge/` 和 `archive/`：

- `unique`：恰有一个物理文件，返回其位置；
- `not_found`：两边都不存在；
- `duplicate`：两边都存在，调用方不得静默选择。

### `logic_path_validate`

校验逻辑路径格式。默认还要求路径当前唯一存在；传入 `require_exists: false` 时只校验格式。

### `logic_path_audit`

批量检查多个逻辑路径，汇总 `unique`、`not_found`、`duplicate` 和 `invalid` 数量。

## 使用边界

新建动态知识引用或数据库来源字段前，调用 `logic_path_validate` 或 `logic_path_resolve`，且仅在结果为 `unique` 时使用该路径。服务不可用或返回错误时，调用方必须报告校验未完成。
