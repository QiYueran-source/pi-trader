# 运行模式与投递

Pi 的定时任务有两种运行模式，能力差别很大，注册前必须先选对。

## 运行模式

| | `inline`（不设 `model`） | `subagent`（设 `model`） |
|---|---|---|
| 执行位置 | 当前会话，prompt 作为一条用户消息注入 | 独立 in-process 会话 |
| 技能 | ✅ 可用 | ✅ 可用（需 `skills: true` 或技能名数组） |
| MCP | ✅ 可用（走 codemode） | ❌ 不可用（见「已知坑 3」） |
| 飞书推送 | ✅ 自动（本会话助手的回复由 `pi-feishu` 在 `turn_end` 投递） | ❌ 不推送，需 `notify: true` 由主会话转述 |
| 隔离性 | ❌ 与日常会话共用上下文与队列 | ✅ 独立 |
| 主会话上下文 | 占用（任务越重占用越大） | 不占用 |

选择建议：

- 需要 MCP、需要"推给我"、或需要看到执行过程的任务 → `inline`。
- 纯产出、静默型任务（如归档、草稿清理）→ 可用 `subagent`，但需接受 MCP 不可用；若该任务依赖 MCP，则只能用 `inline`。
- 模式切换必须 remove + add（Pi 无法原地清空 `model`），`job_id` 会变，需回填并告知用户。

## 投递（飞书）

- Pi 侧**没有**投递/`deliver` 参数；`cronjob.yml` 里历史遗留的 `deliver: origin` 不生效。
- 飞书推送由 `pi-feishu` 扩展在 `turn_end` 时把**该会话**中助手的回复发出：
  - `inline`：任务本身产生一轮回复 → 自动推送。prompt 用「推送/汇报」描述意图即可。
  - `subagent`：子会话以 `noExtensions` 创建，不加载 `pi-feishu` → 不会推送；要通知用户需 `notify: true`（唤醒主会话转述）或改为 `inline`。
- 静默型任务（如"没有过期文件时静默结束"）在 `inline` 下同样只在有结果时输出。
- prompt 中不要写「调用 `send_to_feishu`」这类工具名来保证投递，除非确认该模式下该工具存在；按模式描述意图即可。

## 已知坑

### 1. 重启后任务不触发（磁盘有记录、调度器无定时器）

判定：`schedule_prompt list` 中该任务**没有 `Next:`**。
处置：逐条 `update`（传原 `schedule` 或 `description`）重建定时器；**无需** remove/add，`job_id` 不变。

### 2. 新建任务被绑定到会话

判定：任务正常出现在 `list`，但重启后不再触发；`.pi/schedule-prompts.json` 中该任务带 `session` 字段。
原因：`defaultJobScope` 未生效时，新建任务按 `session` 作用域落库。
处置：清除该字段并 `update` 重挂。
预防：`.pi/schedule-prompts-settings.json` 与 `~/.pi/agent/schedule-prompts-settings.json` 都应含 `{"defaultJobScope": "workdir"}`；本项目在 `cronjob/schedule-prompts-settings.json` 留存副本，需要同步到上述两处。

### 3. subagent 拿不到 MCP

根因：`pi-schedule-prompt` 的 `subagent.js` 创建 `DefaultResourceLoader` 时没有传 `extensionFactories`，内置扩展（`builtin:mcp`、`builtin:codemode`）不在基线里；`extensions` 参数只是**过滤器**，过滤不出基线中不存在的扩展。而 MCP 工具默认 `exposure: codemode`，没有 codemode 就无法调用。
判定：子会话可用工具只有 `read/bash/edit/write`（主会话为这些 + `codemode` + 扩展工具）。
若确需 subagent 使用 MCP：在 `pi-schedule-prompt/dist/subagent.js` 的 loader 参数中补 `extensionFactories: builtInExtensions`（来自 `@earendil-works/pi-coding-agent/dist/extensions/index.js`）与 `additionalExtensionPaths: ['builtin:mcp','builtin:codemode']`，注册时用 `extensions: ['mcp','codemode']` + `skills: true`（机制已实测通过）。该补丁在 npm 更新/重装后会被覆盖，需要时按此重做。
禁止：`extensions: true` 会把 `pi-feishu`（及 `pi-schedule-prompt`）载入子会话，产生**第二个飞书 WebSocket 客户端**与第二个调度器，会与主会话抢收消息。

### 4. cron 表达式与时区

- Pi 使用 **6 字段**（秒 分 时 日 月 周），如 `0 40 23 * * *`；历史 `cronjob.yml` 中的 5 字段写法与运行时不一致，同一任务不要混写两套。
- 触发按**进程本地时区**（本项目 `TZ=Asia/Shanghai`）。改时区后需重启，并按「坑 1」核查 `Next` 是否回到正确时点。

## 诊断手册

| 症状 | 先查 | 处置 |
|:---|:---|:---|
| 到点没跑 | `list` 中是否有 `Next`；记录是否带 `session` | 无 `Next` → `update` 重挂；带 `session` → 清除后重挂 |
| 跑了但没收到飞书 | 任务是否设了 `model`（subagent） | 改 `inline`，或加 `notify: true` |
| 任务里用不了 MCP | 是否 subagent | 改 `inline`，或按「坑 3」打补丁 |
| 触发时间不对 | 进程 `TZ`、cron 字段顺序 | 修正后重启并复核 `Next` |
| 注册报同名冲突 | 是否已存在同名任务 | 先 `list` 再 `add`；已存在改用 `update` |
