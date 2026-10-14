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

- Pi 侧**没有**投递/`deliver` 参数；`cronjob.yml` 的 `deliver: feishu` 只作声明，实际投递靠任务自己调用工具。
- 飞书推送由 `pi-feishu` 扩展在 `turn_end` 时把**该会话**中助手的回复发到 `findActiveState()` 解析出的 `chatId`。
- ⚠️ **关键限制**：`pi-feishu` 在 `agent_end` 时执行 `chatStates.delete(chatId)`，**会话空闲时没有活跃聊天状态**；定时任务绝大多数在空闲时触发 → `turn_end` 自动推送与 `send_to_feishu`（不传 `chat_id`）都**拿不到目标聊天**：
  - 自动推送：`findActiveState()` 为 null → 直接不发送（**不会报错**）。
  - `send_to_feishu` 不传 `chat_id`：返回「没有活跃的飞书聊天」。
- **本项目采用的做法**：**所有任务都投递**，且必须在 prompt 里**显式传 `chat_id`**（显式值会绕过上述状态检查）。
  - chat_id 的**单一来源**是仓库根 `cronjob/delivery.json` 的 `feishuChatId`；prompt 统一写「读 `cronjob/delivery.json` 的 `feishuChatId`，用 `send_to_feishu` 显式传入」。换群只改这一个文件，无需改 prompt 或重注册。
  - 不把 id 写进 16 份 prompt（避免多处硬编码）；不写进 `.pi/schedule-prompts-settings.json`（该文件被扩展 UI 重写时会丢弃自定义键）。
- **回执口径**：非交易日、无候选、无过期文件等“无动作”情形也发一行状态，用于确认任务确实执行；失败时把内容留在回复中并说明原因。
- `subagent` 模式仍不加载 `pi-feishu`（`noExtensions`），无法投递；`notify: true` 也依赖主会话有活跃状态，同样不可靠。

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
| 跑了但没收到飞书 | 任务是否显式传了 `chat_id`；是否设了 `model`（subagent） | 在 prompt 中显式传 `chat_id`；去掉 `model` |
| 任务里用不了 MCP | 是否 subagent | 改 `inline`，或按「坑 3」打补丁 |
| 触发时间不对 | 进程 `TZ`、cron 字段顺序 | 修正后重启并复核 `Next` |
| 注册报同名冲突 | 是否已存在同名任务 | 先 `list` 再 `add`；已存在改用 `update` |
