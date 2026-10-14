# 路径与命名

知识库根目录为：`/pi-trader/knowledge`。

本文件定义动态知识文档的落盘路由和命名。动态知识被引用时，不直接使用下面的物理根目录；引用规则见 [`path-protocol.md`](path-protocol.md)。

路径模板是默认参考。确定路径前，先查看目标目录、相邻日期和同类型文件；已有结构和命名优先于模板。仍无法判断时，先询问用户。

## 通用路径

- 事实：`knowledge/事实/<yyyy-mm-dd>/<标题>.md`
- 长期笔记：`knowledge/笔记/<题材>/<笔记>.md`
- 财经分析：`knowledge/交易/财经分析/<yyyy-mm-dd>/<文件名>.md`
- 交易计划：`knowledge/交易/交易计划/<yyyy-mm-dd>/<体系名称>_交易计划.md`
- 交易复盘：`knowledge/交易/交易复盘/<yyyy-mm-dd>/<体系名称>_复盘.md`
- 交易过程资料：`knowledge/交易/过程资料/<yyyy-mm-dd>/<体系名称>/<产物名称>.<扩展名>`
- 摘要：`knowledge/摘要/摘要_<yyyy-mm-dd>.md`
- 附件：`knowledge/附件/<yyyy-mm-dd>/<文件名>.<扩展名>`

上述模板中的 `knowledge/` 是物理落盘根目录。对应的逻辑路径应去掉该前缀，例如：`事实/<yyyy-mm-dd>/<标题>.md`。

## 路径检查

1. 先列出目标一级目录和相关日期目录。
2. 查找同类型、同题材、同体系或相邻日期的已有文件。
3. 沿用已有的目录层级、文件名后缀和日期格式。
4. 长期笔记保留题材目录，文件名直接使用笔记标题，不再创建日期目录。
5. 财经分析保留日期目录，用于区分同名的每日分析文件。
6. 只有找不到相近样例时，才使用上面的默认模板。
7. 交易体系内部的 `params`、`scripts`、`templates`、`references`、`更新日志` 等目录由交易体系专用技能处理。
8. 新建动态知识引用时，使用去掉 `knowledge/` 或 `archive/` 前缀的逻辑路径；不要把物理路径写入正文或数据库来源字段。

当前结构示例（用 `<yyyy-mm-dd>` 占位，避免示例路径随归档失效）：

```text
knowledge/笔记/交易心法/从看红绿到看结构-看盘心法.md
knowledge/交易/财经分析/<yyyy-mm-dd>/开源证券-盘前分析.md
knowledge/交易/交易复盘/<yyyy-mm-dd>/基于Agent的ETF轮动体系_复盘.md
knowledge/交易/过程资料/<yyyy-mm-dd>/<体系名称>/grid_parameters.json
knowledge/摘要/摘要_<yyyy-mm-dd>.md
```
