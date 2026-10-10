# cronjob 目录 · 规则与说明

## 定位

`cronjob/` 是交易体系**定时任务的统一定义目录**。所有由 Hermes 调度器管理的定时任务都在这里定义配置、存放 prompt 和辅助脚本。

## 目录结构

```
cronjob/
├── RULES.md           # 本文件
├── global/            # 全局任务（不归属特定交易体系）
│   ├── global-0915-daily-plan-report/
│   ├── global-1500-trade-remind/
│   ├── global-2130-financial-analysis-review/
│   ├── global-2230-manual-review/
│   └── global-2355-summary-aggregation/
├── system/            # 体系级任务（归属某一交易体系）
│   └── div-etf-grid-trade/
│       ├── div-etf-grid-trade-1800-param-check/
│       └── div-etf-grid-trade-1805-risk-monitor/
└── utils/             # 公共工具脚本
    └── is_trading_day.py
```

### 分类规则

| 层级 | 目录 | 说明 |
|------|------|------|
| 全局任务 | `cronjob/global/` | 不归属特定交易体系的定时任务，如每日计划通报、收盘提醒、摘要聚合 |
| 体系任务 | `cronjob/system/{system-id}/` | 归属某一交易体系的定时任务，用体系 system-id 命名 |
| 公共工具 | `cronjob/utils/` | 多个 cronjob 共享的辅助脚本 |

## 命名规范

### 任务目录名

`{system-id}-{时间}-{任务描述}`

| 部分 | 说明 | 示例 |
|------|------|------|
| `system-id` | global 或体系 system-id（用连字符，`_` → `-`） | `global`, `div-etf-grid-trade` |
| `时间` | 4 位数字 HHMM | `0915`, `1800`, `2355` |
| `任务描述` | 简短英文，连字符分词 | `daily-plan-report`, `param-check`, `risk-monitor` |

**示例**：
- `global-0915-daily-plan-report` — 全局，9:15 每日计划通报
- `div-etf-grid-trade-1800-param-check` — 红利ETF网格，18:00 月度参数检查

### 任务名（name）

对应 Hermes 调度器的 `name` 字段，**必须与任务目录名一致**。

### 简报名

`{今天日期}_{task-name}.txt`

即 `name` 字段的值作为简报文件名后缀，放在 `knowledge/摘要/.abstract/` 下。

**示例**：
- `2026-06-14_div-etf-grid-trade-1800-param-check.txt`
- `2026-06-14_div-etf-grid-trade-1805-risk-monitor.txt`

## 任务定义

每个任务目录下必须有 `cronjob.yml` 和 `prompt.txt` 两个核心文件。

### cronjob.yml 字段标准

```yaml
# 注释：一行说明该任务做什么
name: {task-name}                         # 与目录名一致
job_id:                                   # Hermes 调度器注册后自动生成，留空
schedule: "0 18 * * *"                    # cron 表达式（交易日由脚本内部判断）
workdir: /hermes-trader                   # 工作目录
mode: agent                               # 当前统一使用 agent 模式
model: deepseek-v4-flash-0731             # 运行模型（Provider: custom）
deliver: origin                           # 投递到飞书
prompt: prompt.txt                        # 任务指令文件
scripts:                                  # 可选：辅助脚本列表
  - /hermes-trader/cronjob/{...}/{script}
created_at: 2026-06-12                    # 创建日期
description: 简短的该任务作用描述
```

### prompt.txt 写作规则

1. **自包含**：任务运行时没有对话上下文，prompt 必须完整描述做什么、怎么做
2. **交易日判断**：由脚本 `is_trading_day.py` 或体系内部脚本处理，不要在 prompt 里硬编码
3. **工作完成后落简报**：每种任务执行成功后必须落一条简报到 `knowledge/摘要/.abstract/{日期}_{task-name}.txt`
4. **不需要用户确认**：cron 任务无人值守，不能 ask 用户

### utils/ 公共工具

`cronjob/utils/` 存放公共脚本，多个任务共享：

| 脚本 | 作用 |
|------|------|
| `is_trading_day.py` | 判断指定日期是否为交易日，返回 TRADING_DAY / NON_TRADING_DAY |

## 新增任务流程

1. 确定任务归属：全局 → `cronjob/global/`，体系 → `cronjob/system/{system-id}/`
2. 按命名规范创建任务目录
3. 编写 `cronjob.yml`（name 与目录名一致，job_id 留空）
4. 编写 `prompt.txt`（自包含，末尾加落简报规则）
5. 如需共享工具，写到 `cronjob/utils/`
6. 注册到 Hermes 调度器：`hermes cron create`（或直接在界面上创建）
7. 在对应知识库文档（如 `体系运作流程.md`）中更新 cron 任务表

## 注意事项

- **目录名即任务名**，两者必须一致，否则调度器无法关联
- **job_id** 由调度器自动生成，cronjob.yml 中留空即可
- **不要用中文命名**目录和 name，保持英文+连字符
- **不要在 prompt 里 hardcode 时间**，时间在 cronjob.yml 的 schedule 字段控制
- **不要写死交易日**，用 `is_trading_day.py` 或体系内部脚本判断
- **体系目录名**优先复用 `system.yml` 中定义的 `system-id`（将 `_` 替换为 `-`）
