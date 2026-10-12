# Cronjob 书写规范

## 推荐目录

全局型：

```text
cronjob/global/global-0915-daily-plan-report/
├── cronjob.yml
└── prompt.txt
```

体系型：

```text
cronjob/system/agent-etf-rotation/agent-etf-rotation-1850-generate-plan/
├── cronjob.yml
└── prompt.txt
```

辅助脚本放在对应任务目录中；任务之间共享逻辑时，优先通过 MCP 或 Skill 提供，不建立公共脚本目录。

## `cronjob.yml`

最小模板（Pi 适配）：

```yaml
name: {task-name}
job_id:            # 注册后回填
type: cron
schedule: "0 50 18 * * *"   # Pi：秒 分 时 日 月 周
enabled: true
scope: workdir     # 共享作用域，不绑定会话
mode: inline       # inline=主会话执行并自动回传飞书；subagent=独立会话（需 model/notify）
prompt: prompt.txt # 注册时读取文本写入运行时
created_at: YYYY-MM-DD
description: 任务职责说明
```

写作要求：

- `name` 必须与任务目录名完全一致。
- 新任务的 `job_id` 可以留空，注册后再回填实际值；模式切换会换 `job_id`，必须重新回填。
- `schedule` 使用合法 cron 表达式，并与名称中的时间一致；Pi 用 **6 字段**（秒 分 时 日 月 周），不要与旧版 5 字段混写。
- `prompt` 指向任务目录中的实际 prompt 文件；注册时由执行者读取文件文本传给工具。
- `type` 默认 `cron`；`enabled` 默认 `true`。
- `scope` 使用 `workdir`（共享作用域）；注册后应核查运行时记录没有 `session` 字段。
- `mode` 必须与 Pi 运行时一致；`mode: inline` 时不得出现 `model`，`mode: subagent` 时必须写 `model` 并考虑 `notify`。
- `created_at` 使用 `YYYY-MM-DD`。
- 不要再使用 Hermes 时代的 `workdir`、`mode: agent`、`deliver`、`scripts` 字段。
- 不要把密钥、密码或 token 写入 YAML。

字段含义、运行模式能力与飞书投递方式见 [runtime-and-delivery.md](runtime-and-delivery.md)。

## `prompt.txt`

prompt 必须自包含，至少包含：

1. 任务目的。
2. 输入来源和目标日期。
3. 执行步骤。
4. 输出路径或通知方式。
5. 非交易日、输入缺失或脚本失败时的处理方式。
6. 失败时汇报阶段和原因。

建议结构：

```markdown
# 任务名称

## 任务目标

## 输入

## 执行步骤

## 输出

## 异常处理

- 没有输入时：
- 脚本失败时：
- 已有输出时：
```

不应在 prompt 中：

- 依赖当前会话中的上下文。
- 要求用户确认或等待用户回复。
- 写入密钥。
- 复制应由知识库规则文档维护的完整阈值表和业务规则（改用「加载 `xxx` 技能、按其中流程执行」+ 本任务特有约束的写法）。
- 引用未经检查、实际不存在的脚本或文档路径。
- 在 `subagent` 模式下写「通过飞书推送」之类无法实现的送达要求（见 [runtime-and-delivery.md](runtime-and-delivery.md)）。

## 输出与简报

- 任务产生的简报写入 `knowledge/摘要/.abstract/{日期}_{主题}.txt`，由当天 23:55 的摘要聚合任务读取并删除。
- **聚合任务只读当天日期前缀的简报**：在 23:55 之后补写的简报必须使用**次日日期**命名，否则永远不会被聚合。
- 正常无事的任务应在 prompt 中明确「静默结束」，只在有结果或异常时输出。

## 修改同步

修改 `prompt.txt` 后，必须同时处理两份内容：

1. 提交仓库中的 `prompt.txt`。
2. 更新 Pi 调度器中已注册任务的 prompt 内容。

只改文件不会改变已注册任务使用的 prompt；只改运行时注册又会使仓库文件落后。

## 时间和交易日

推荐每天触发，再由任务内部判断交易日：

```yaml
schedule: "50 18 * * *"
```

不要仅使用 `1-5` 代替交易日判断，因为节假日调休可能导致任务遗漏。涉及交易日的 prompt 应说明非交易日是跳过、继续还是生成下一交易日结果。
