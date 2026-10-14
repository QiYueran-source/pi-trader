---
name: knowledge-management
description: 管理动态知识文档的分类、路径、Frontmatter 和正文。创建、修改、移动、归档或整理动态知识文档时必须使用。
---

# 知识库管理

本技能只治理动态知识文档。动态知识的物理文件主要位于 `/pi-trader/knowledge`，历史归档位于 `/pi-trader/archive`；两者是同一类动态知识的不同物理位置。

将需要长期保留的事实、长期笔记、财经分析、交易文档、摘要和附件保存到 `/pi-trader/knowledge`。动态知识的逻辑路径、物理位置和引用规则见 [`reference/path-protocol.md`](reference/path-protocol.md)。

## 工作流程

1. 判断内容是否属于动态知识以及是否需要落盘。
2. 阅读 `reference/type.md`，确定内容类型。
3. 如果属于交易体系内部内容，识别体系名称并交给对应的交易体系技能。
4. 阅读 `reference/routes.md`，结合 `knowledge` 中已有的同类文件确定路径和文件名。
5. 阅读 `reference/frontmatter.md`，生成或更新文档头部。
6. 阅读 `reference/path-protocol.md`，确认逻辑路径和引用写法。
7. 需要确认引用目标存在且唯一时，调用 `logic-path` MCP 的 `logic_path_validate` 或 `logic_path_resolve`；MCP 不可用或返回错误时，不得把路径校验描述为已完成。
8. 阅读 `reference/style.md`，整理正文内容。
9. 保存后检查路径、文件名、Frontmatter、逻辑路径引用和 `summary` 是否准确。

## 处理原则

- 内容类型优先于文件格式，先判断内容用途再选择目录。
- 已有目录结构和同类文件命名优先于默认模板。
- 新文档遵循当前规范；历史文档保持兼容，按需渐进整理。
- 不重复创建同一内容；已有文档应优先补充或更新。
- 区分事实、观点、计划、已发生的成交和复盘结论。
- 动态知识之间以及数据库业务记录引用动态知识时，使用逻辑路径，**不允许**把 `knowledge/` 或 `archive/` 物理前缀写入新引用。
- 动态知识被归档时，逻辑路径保持不变；归档流程不得要求动态知识正文或数据库来源字段跟随物理位置改写。
- 面向读者的正文出现无效免责声明、叠加保守措辞或编辑过程叙述时，按需加载 `stss`；来源、日期、证据强度、风险条件、模拟与真实交易范围及其他影响理解或决策的限制必须保留。

## 与其他资产的边界

本技能仅负责 `knowledge/`（以及 `archive/`）下文档的落盘和写作。

## 历史遗留与新内容优先级

- 历史文档可能存在旧 Frontmatter（`uuid`、`links`、`updated`）、旧物理路径（如 `knowledge/`、`archive/` 或旧工作区绝对路径）、失效引用或指向 archive 的旧引用。这些属遗留状态，不要求本轮批量修复，允许长期存在。
- `archive/` 是动态知识的本地历史物理位置；其文件仍可通过逻辑路径解析，但存量格式问题按历史兼容规则处理。
- 落盘新内容时先依据本技能及 `reference/`；技能未覆盖的细节，参照**最近期的同类文档**（同目录、同类型中日期最新的文件）。
- 不主动回修历史遗留，也不在回复、简报或复盘中汇报或列为待办；用户明确询问时再说明。

## 参考文件

- `reference/type.md`：动态知识内容类型与目录判断。
- `reference/routes.md`：动态知识路径模板、命名方式与现有结构检查。
- `reference/frontmatter.md`：Frontmatter 要求和历史格式说明。
- `reference/style.md`：知识库正文的总体写作原则。  
- `reference/path-protocol.md`：逻辑路径、物理位置、引用和归档身份协议。
- `logic-path` MCP：执行动态知识逻辑路径的格式校验、双头解析和批量审计；服务不可用时必须如实报告，不得假设校验成功。
