# Pi Trader 系统追加约束

## 文件管理入口

处理某类资产时，必须加载对应的管理 Skill：

- 动态知识文档：`knowledge-management`
- Skill：`agent-dev/skill-management`
- cronjob：`agent-dev/cronjob-management`
- MCP：`agent-dev/mcp-management`
- Extension：`agent-dev/extensions-management`
- Git：`agent-dev/git-standard`
- 草稿：`use-scratch-space`

各管理 Skill 只负责自己的资产类型。需要跨资产协作时，使用对方公开的接口和规则，不复制或越界管理对方的内部细节。

## 动态知识基本原则

动态知识文档的文件类型、分类、目录路由、命名、Frontmatter、逻辑路径和引用协议，以 `knowledge-management` Skill 及其参考文件为准。

动态知识的逻辑路径与物理位置分离：逻辑路径不能以 `knowledge/` 或 `archive/` 开头，更不允许使用绝对路径，**这里的限制只针对动态文档正文、Frontmatter 和数据库来源字段中的引用字符串**。新动态内容的物理落盘目标是 `knowledge/`，`archive/` 仅由归档流程写入。读取时由 `knowledge-management` 规则将逻辑路径同时解析到两棵物理目录。具体请参考 `knowledge-management` 技能的对应说明。
