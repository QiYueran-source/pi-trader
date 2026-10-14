---
name: skill-management
description: 管理 Pi 项目中的 Skill 资产，包括 Skill 目录、SKILL.md、参考资料、加载关系和迁移。创建、修改、检查、迁移或排查 Skill 时必须使用。
---

# Skill 管理

## 定位

本技能只管理 Skill 资产

Skill 是项目的静态运行资产，负责描述模型工作流程、业务规则、输入输出和其他资产的调用边界。Skill 的业务内容应保存在自身目录及其 `references/`。

## 文件类型与路径

通常的 Skill 结构为：

```text
.pi/skills/<scope>/<skill-name>/
├── SKILL.md
├── references/
```

- `SKILL.md` 是技能入口，必须存在并包含有效的 `name`、`description` 元数据。
- `references/` 保存详细规则和参考资料；`SKILL.md` 通过相对路径引用它们。

## frontmatter  

技能的frontmatter为  

```text
---
name: 技能名称，需要和路径一致，单词用 '-' 连接
description: 技能描述，触发范围  
---
```

## 技能书写参考

技能属于静态运行资产，参照 `SYSTEM.md` 等。任何技能内部不允许把某次运行产生的具体动态文档路径写成固定依赖；可以使用动态知识的逻辑路径模板，并且必须明确新动态内容写入 `knowledge/`，`archive/` 仅由归档流程作为历史物理目录使用。

技能自身的入口、参考文件和其他静态基础设施路径可以按静态资产需要使用物理路径；“不得使用 `knowledge/` 或 `archive/` 前缀”的规则只适用于动态文档正文、Frontmatter 和数据库来源字段中的引用字符串。

## MCP  

技能**必须**是只读文档，以md的形式组织，**不允许**出现脚本，数据库等内容。  
- 涉及到需要执行的内容，请配置为MCP，并由MCP实现执行。   
- 涉及动态数据保管，请使用sqlite数据库，保存在 `database/`目录  

## 技能、MCP、扩展和定时任务  

一个完整的工作往往需要 技能、MCP、扩展和定时任务的相互配合。在修改一个技能时，请同时检验其配合的MCP、扩展和定时任务是否需要更新。具体更新时，请参考对应的`agent-dev`技能。  



