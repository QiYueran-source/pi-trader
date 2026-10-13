---
name: knowledge-management
description: 管理 knowledge 目录文档的分类、路径、Frontmatter 和正文。创建、修改、移动、归档或整理 knowledge/ 中的正式文档时必须使用。
---

# 知识库管理

将需要长期保留的事实、长期笔记、财经分析、交易文档、摘要和附件保存到 `/pi-trader/knowledge`。

## 工作流程

1. 判断内容是否需要落盘。
2. 阅读 `reference/type.md`，确定内容类型。
3. 如果属于交易体系内部内容，识别体系名称并交给对应的交易体系技能。
4. 阅读 `reference/routes.md`，结合 `knowledge` 中已有的同类文件确定路径和文件名。
5. 阅读 `reference/frontmatter.md`，生成或更新文档头部。
6. 阅读 `reference/style.md`，整理正文内容。
7. 保存后检查路径、文件名、Frontmatter 和 `summary` 是否准确。

## 处理原则

- 内容类型优先于文件格式，先判断内容用途再选择目录。
- 已有目录结构和同类文件命名优先于默认模板。
- 新文档遵循当前规范；历史文档保持兼容，按需渐进整理。
- 不重复创建同一内容；已有文档应优先补充或更新。
- 区分事实、观点、计划、已发生的成交和复盘结论。
- 面向读者的正文出现无效免责声明、叠加保守措辞或编辑过程叙述时，按需加载 `stss`；来源、日期、证据强度、风险条件、模拟与真实交易范围及其他影响理解或决策的限制必须保留。
- 已确认的成交通过交易管理 MCP 登记到账本；交易计划记录准备采取的动作。

## 参考文件

- `reference/type.md`：内容类型与目录判断。
- `reference/routes.md`：路径模板、命名方式与现有结构检查。
- `reference/frontmatter.md`：Markdown Frontmatter 要求和历史格式说明。
- `reference/style.md`：知识库正文的总体写作原则。
