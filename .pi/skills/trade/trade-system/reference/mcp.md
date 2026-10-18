# 体系 MCP 接口

## 定位

交易体系的计算、参数读取与校验、模板渲染统一由 MCP 完成。**一个交易体系一个 MCP 服务**，服务入口、参数与模板都在该体系的运行定义目录内；Agent 不直接执行体系脚本，也不从知识库读取运行参数或模板。

通用 MCP 规范（`.pi/mcp.json` 配置、连接与工具发现、服务实现结构）由 `agent-dev/mcp-management` 技能负责，本文件只写体系侧的命名映射、入参与产物口径。

## 运行定义目录

```text
.pi/mcp-servers/trade-system/<system-id>/
├── mcp_server.py      # 服务入口；只做工具注册与路由
├── functions/         # 实现模块（按职责拆分，视规模取用）
├── params/            # 参数唯一来源（每个文件带 schema_version）
└── templates/         # 过程资料模板唯一来源
```

体系一般都有参数、模板与实现逻辑，按上述结构摆放：`params/`、`templates/` 是运行定义的常规组成；`functions/` 视规模取用，简单体系让 `mcp_server.py` 单文件承载实现即可。**此结构为参考，不强制。** 目录名即 `system-id`；体系的身份（名称、成熟度、账户）写在知识库 `体系介绍.md`，不另设运行契约文件。

`.pi/mcp-servers/trade-system/` 只是容器目录，不放实现。

## 命名规则

| 项 | 规则 | 示例 |
|:--|:--|:--|
| `system-id` | 机器标识，下划线 | `div_etf_grid_trade` |
| 运行定义目录 | 与 `system-id` 同名 | `.pi/mcp-servers/trade-system/div_etf_grid_trade/` |
| MCP 注册键（服务名） | `system-id` 的 `_` 换成 `-` | `div-etf-grid-trade` |
| 工具命名空间 | 由注册键派生 | `mcp__div_etf_grid_trade__*` |
| 定时任务目录与任务名 | 同连字符形式 | `cronjob/system/div-etf-grid-trade/div-etf-grid-trade-1800-daily-check/` |
| 知识库体系目录与产物目录 | 人读体系名称 | `交易/过程资料/<YYYY-MM-DD>/<体系名称>/` |

注册在 `.pi/mcp.json`，`command` 为 `/opt/venv/bin/python`，`args` 指向运行定义目录内的 `mcp_server.py`。

## 工具与入参

| 工具 | 入参 | 返回 |
|:--|:--|:--|
| `list_systems` | — | 本服务实现的体系（含 `system_id`、名称、支持的操作） |
| `get_manifest` | `system_id` | 运行定义路径（`system_root`/`parameter_root`/`template_root`）、操作清单、产物落盘位置 |
| `validate_parameters` | `system_id` | `valid`、`files`、`parameter_version`、`parameter_hash`、`schema_versions` |
| `calculate` | `system_id`、`operation`、`date`、`positions`（按体系契约，部分操作必填）、`human_review`（按体系契约）、`dry_run`（可选） | 事实 JSON；`dry_run=false` 时写入过程资料 |
| `render` | `system_id`、`artifact`、`date`、`document`（可选）、体系定制附加输入（可选） | 同名 Markdown，返回落盘路径 |

约定：

- `system_id` 必填，且必须等于本服务的体系；调用别的体系要用它自己的服务。
- `date` 支持 `YYYY-MM-DD` 或 `YYYYMMDD`；落盘目录统一用 `YYYY-MM-DD`。
- `positions` 必须包含真实持仓与现金（`cash` 必填），由 `trade-management` MCP 生成，不用估算值。
- 每次调用重新读取并校验 `params/`；参数改动后无需重启服务。
- `render` 的 `document` 可省略：省略时按 `date` + `artifact` 读同日过程资料；需要附加输入（如关联状态）时按体系契约传入。渲染出的来源行使用逻辑路径。
- 操作名与入参以实现注册的工具与工具 schema 为准（`get_manifest` 的 `operations` 由实现给出）；同一操作可以落盘多份产物（实现需在返回中给出各自路径）。

## 产物与落盘

- 过程资料写入 `knowledge/交易/过程资料/<YYYY-MM-DD>/<体系名称>/`，文件名以 `params/runtime.json`（跑批体系）或实现约定的产物契约为准。
- 过程资料不是交易指令；实际成交、持仓与账户变化由 `trade-management` 负责。
- 渲染出的文档正文引用其它动态知识时使用逻辑路径，不带 `knowledge/` 或 `archive/` 前缀。

## 错误与降级

- 调用失败返回 `{"ok": false, "error": "..."}`，不产生产物；入口层还会拦截缺失参数、体系不符与非法操作。
- 非交易日或当日无行情时按无数据报错，不使用其它日期数据替代。
- 调用失败时记录失败阶段与错误信息并停止依赖该事实的下游步骤；不估算、不编造、不用历史产物冒充当日结果。
- MCP 服务不可用时如实报告，不改为直接执行仓库内的历史脚本。

## 自检

新增或修改运行定义后，重载 MCP 客户端并确认：

1. 工具发现正常，命名空间为 `mcp__<注册键下划线形式>__*`，工具数量与 `list_systems`／`get_manifest` 的返回一致。
2. `get_manifest` 返回的运行定义、参数与模板路径存在。
3. `validate_parameters` 通过；改参数后哈希发生变化。
4. 参数或模板迁移、实现改动后，用同一输入复算一次，比对事实值不发生变化。
5. 写入前用 `dry_run=true` 预览，需要正式产物时再写。

## 新增体系

1. 复制一份运行定义目录，目录名取新的 `system-id`。
2. 写 `mcp_server.py`（以及 `functions/`，视规模）、`params/`、`templates/`，并在知识库补 `体系介绍.md`。
3. 在 `.pi/mcp.json` 增加一条服务（键 = `system-id` 连字符形式）。
4. 重载后按「自检」核对。

公共代码（行情客户端、日期与落盘工具）在出现第二个体系时再决定提取方式，默认各体系自带一份。

## 存量体系迁入

知识库内仍保留 `params/`、`scripts/` 或 `templates/` 的体系，按以下顺序收口到运行定义：

1. 建运行定义目录 `.pi/mcp-servers/trade-system/<system-id>/`，把实现、参数与模板放进去；参数选取当前生效的那一份，带上 `schema_version`。
2. 在 `.pi/mcp.json` 注册服务，重载后按「自检」核对。
3. 用同一输入比对：新服务的事实值与迁移前的脚本产物逐字段一致（元数据、文案差异单独确认）。
4. 删除知识库内的 `params/`、`scripts/`、`templates/`；脚本能力已由实现覆盖，历史版本留 git。
5. 同步知识库文档：体系介绍的文件索引、运作流程的步骤表与变更链、参数说明、规则文档及接口速查。
6. 同步任务：prompt 里的事实来源改为本体系的服务名，写运行契约并指向 SOP 章节；按 `agent-dev/cronjob-management` 重注册并自检。
7. 写一篇 `更新日志/<YYYY-MM-DD>_<主题>.md`，记动因、变更、验证与遗留。

迁移期间同一体系的运行定义只能存在一处：要么在知识库（旧），要么在运行定义目录（新）。
