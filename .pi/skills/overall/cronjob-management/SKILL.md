---
name: cronjob-management
description: 设计、书写、注册、检查和维护 Pi cronjob 定时任务。创建、修改、注册、检查、删除、暂停、恢复或重注册任意全局型、体系型定时任务时必须使用。
---

# Cronjob 管理

## 定位

本技能管理两部分：

1. 仓库中的 cronjob 声明文件：目录、`cronjob.yml`、`prompt.txt`。
2. Pi 运行时的 cronjob 注册状态：任务是否已注册、注册参数是否与声明一致。

本技能是轻量级管理规范，不负责复杂调度运维。任务失败、上游结果缺失或补做时，汇报任务、阶段和原因，后续由人工处理。

## 两类定时任务

### 全局型任务

不属于任何一个交易体系的任务放在：

```text
cronjob/global/{global}-{HHMM}-{task}/
```

例如：

```text
cronjob/global/global-0915-daily-plan-report/
```

全局型任务可以读取多个体系的结果，但不能把某个体系的业务规则当作全局规则。

### 体系型任务

属于某个交易体系的任务放在：

```text
cronjob/system/{system-id}/{system-id}-{HHMM}-{task}/
```

例如：

```text
cronjob/system/agent-etf-rotation/agent-etf-rotation-1850-generate-plan/
```

`system-id` 必须来自对应交易体系的 `system.yml`，目录和任务名称使用英文连字符。体系型任务应引用该体系的流程和规则文档。

## 设计任务

创建任务前先明确：

- 类型：全局型或体系型
- 名称和执行时间
- 任务目的
- 输入来源
- 执行动作
- 输出位置和通知方式
- 非交易日或输入缺失时的行为
- 失败时需要汇报的阶段和原因

设计原则：

- `schedule` 负责触发时间，交易日判断由任务内部处理。
- prompt 必须自包含，不能依赖当前对话上下文。
- 业务规则放知识库文档，prompt 只描述执行步骤和文档引用。
- 任务输出必须说明产物日期，避免把执行日期、数据日期和产物日期混淆。
- 不在 prompt 或配置文件中写入密钥。

## 书写和检查

每个任务目录至少包含：

```text
cronjob.yml
prompt.txt
```

检查以下内容：

- `cronjob.yml` 的 `name` 与任务目录名完全一致。
- `schedule` 是合法 cron 表达式，且与名称中的 `HHMM` 一致。
- `prompt` 指向实际存在的 `prompt.txt`。
- `mode`、`scope`、`schedule` 与 Pi 运行时的实际注册参数一致。
- 体系型任务的目录、`system-id` 和所属体系一致。
- `prompt.txt` 自包含，明确输入、动作、输出和异常汇报方式。
- 修改 prompt 后，同时更新仓库文件和 Pi 注册任务中的 prompt 内容。
- 每个任务的 `prompt.txt` 含统一的「投递与输出」段：投递读 `cronjob/delivery.json` 的 `feishuChatId` 并显式传给 `send_to_feishu`，输出首行给一行式状态，无动作也回执。
- 注册或变更后，把运行时的 `job_id` 回填到 `cronjob.yml`。

完整字段和 prompt 写作规则见 [writing-conventions.md](references/writing-conventions.md)。

## Pi cronjob 工具

使用 Pi 的 `schedule_prompt` 工具（交互命令 `/schedule-prompt`）管理运行时任务。标准流程：

1. 设计任务。
2. 创建或修改仓库中的 `cronjob.yml` 和 `prompt.txt`。
3. 检查名称、时间、路径和 prompt。
4. 查询当前已注册任务。
5. 判断是新增、更新、已存在还是注册缺失。
6. 对重要变更先获得用户确认。
7. 调用 `schedule_prompt` 创建或更新。
8. 再次查询，确认注册结果并回填 `job_id`。

注册完成后必须自检三件事：

1. `list` 中该任务有 `Next:`（有存活定时器；没有说明只是磁盘上有记录）。
2. 运行时记录不带 `session` 字段（带则为会话绑定，重启后静默失效）。
3. 运行时 `prompt` 与仓库 `prompt.txt` 逐字一致。

工具操作和注册同步规则见 [pi-cronjob-tool.md](references/pi-cronjob-tool.md)；运行模式能力与投递机制见 [runtime-and-delivery.md](references/runtime-and-delivery.md)。

## 必须先确认的操作

以下操作执行前必须向用户说明变更内容并获得确认：

- 调整执行时间或频率
- 创建新的任务
- 删除任务
- 暂停或恢复任务
- 改变任务类型或所属体系
- 切换运行模式（`inline` ↔ `subagent`）；该变更必须 remove + add，`job_id` 会改变
- 修改通知渠道
- 修改核心执行逻辑，尤其是可能产生交易动作的逻辑
- 补做可能覆盖已有业务产物的任务

确认时至少说明：任务名称、当前配置、拟修改内容和影响范围。

## 重启后的检查

Pi 重启、进程重启或调度器状态重置后，运行时注册可能丢失。仓库文件存在不代表任务仍已注册。

启动后执行最小检查：

```text
读取 cronjob 定义
→ 查询 Pi 当前注册任务
→ 按 name 对比，并检查每项是否有 Next
→ 汇报缺失或配置不一致
→ 获得确认后重新注册或重挂
```

判据与处置：

- **磁盘上有记录、但 `list` 中该任务没有 `Next`**：调度器里没有存活定时器，任务不会触发。用 `update`（原 `schedule`/`description` 即可）逐条重挂，`job_id` 不变。
- **任务完全不在 `list` 中**：按仓库定义重新注册，并回填 `job_id`。
- **注册后发现任务带 `session` 字段**：属会话绑定，重启后会失效，需清除该字段并 `update` 重挂。

不要因为查询不到任务就直接重复创建：先按 `name` 检查是否已有同名任务，避免重复注册。交易体系任务缺失时，默认先汇报并等待确认。

## 失败、缺失和补做

只做最小处理：

- 执行失败：汇报任务名称、失败阶段、错误原因，以及是否产生部分输出。
- 上游结果缺失：按该任务 prompt 中的约定跳过、继续或说明缺失。
- 补做：先确认目标日期、输出位置和是否覆盖已有文件。
- 并发或时序冲突：发现后停止重复操作并汇报，由人工决定处理方式。

本技能不建立执行日志系统、并发锁、自动重试、自动回滚、权限管理或密钥管理。

## 参考资料

- [cronjob-design.md](references/cronjob-design.md)：两类任务的设计差异。
- [writing-conventions.md](references/writing-conventions.md)：目录、YAML 和 prompt 规范。
- [pi-cronjob-tool.md](references/pi-cronjob-tool.md)：注册、查询、更新和重启检查。
- [runtime-and-delivery.md](references/runtime-and-delivery.md)：运行模式能力、飞书投递机制、已知坑与诊断手册。
