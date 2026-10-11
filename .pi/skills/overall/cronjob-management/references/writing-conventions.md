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

最小模板：

```yaml
name: {task-name}
job_id:
schedule: "50 18 * * *"
workdir: /pi-trader
mode: agent
model: deepseek-v4-flash-0731
deliver: origin
prompt: prompt.txt
created_at: YYYY-MM-DD
description: 任务职责说明
```

写作要求：

- `name` 必须与任务目录名完全一致。
- 新任务的 `job_id` 可以留空，注册后再回填实际值。
- `schedule` 使用合法 cron 表达式，并与名称中的时间一致。
- `prompt` 指向任务目录中的实际 prompt 文件。
- `workdir` 使用运行环境中的真实路径。
- `scripts` 等附加路径必须可用。
- `created_at` 使用 `YYYY-MM-DD`。
- 不要把密钥、密码或 token 写入 YAML。

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
- 复制应由知识库规则文档维护的完整阈值表和业务规则。
- 引用未经检查、实际不存在的脚本或文档路径。

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
