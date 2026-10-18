---
title: 实现拆分到 functions 目录 | 2026-10-18
summary: "双网格体系 MCP 由单文件 635 行拆为「入口 + functions/ 子包」：`mcp_server.py` 只留工具注册与路由（含 sys.path 自举），实现按职责拆入 paths / parameters / market / scaling / signals / facts / artifacts 七个模块；函数体逐字未改，仅 `__file__` 深度推导集中到 paths.py。验证：36 个代码块逐字比对一致、两种加载方式均可导入、真实 stdio 握手 5 个工具全通、沙盒 12 组矩阵与分腿用例、9+5 条错误路径与三类事实渲染全部通过。"
date: 2026-10-18
reason: 用户 2026-10-18 提出单文件过长、可在体系 MCP 目录内加 functions 目录存 py 脚本；先以双网格做样板
tags:
  - 交易体系
  - 更新日志
  - 网格
system-id: div_etf_grid_trade
system-name: 红利科创ETF双网格体系
---

# 实现拆分到 functions 目录 | 2026-10-18

## 一、动因与范围

- 动因：`mcp_server.py` 单文件 635 行，实现、参数校验、行情取样、事实计算、渲染混在一起，定位与改动成本高。
- 范围：只做**结构搬运**，不改行为、不改参数、不改工具契约、不改 `mcp.json` 注册。三个其它体系（双债、ETF轮动、热门板块）本轮不动。

## 二、拆分结果

```text
div_etf_grid_trade/
├── mcp_server.py        # 入口：sys.path 自举、导入、tool_calculate、TOOLS、server、路由、stdio（147 行）
└── functions/
    ├── paths.py         # 根路径常量、load_env、normalize_date、read_json、process_dir
    ├── parameters.py    # EXPANSION_KEYS、load_parameters、validate_parameters、parameter_metadata
    ├── market.py        # get_client、行情取样、涨跌停与连跌口径
    ├── scaling.py       # floor100、apply_factors
    ├── signals.py       # rolling_sigma、leg_signals、emotion_facts
    ├── facts.py         # positions_input、system_nav、risk_facts、regulator_facts、sector_facts
    └── artifacts.py     # artifact、write_artifact、render_artifact
```

依赖方向单向（`paths → parameters/market → scaling/signals → facts → artifacts → 入口`），无环形导入。

## 三、两处必要改动（其余逐字搬运）

1. **根路径推导收口**：`REPO_ROOT/SYSTEM_ROOT/PARAMS_ROOT/TEMPLATES_ROOT` 等常量集中到 `functions/paths.py`（子模块 `__file__` 深度不同，不能各自推导）；`REPO_ROOT` 的环境变量回退由 `parents[4]` 改为 `SYSTEM_ROOT.parents[3]`。
2. **入口自举**：`mcp_server.py` 在导入子模块前把体系目录插入 `sys.path`——按绝对路径当脚本运行（`.pi/mcp.json` 的方式）本来就能解析，但按文件加载（`importlib.spec_from_file_location`，沙盒验收用）不行，自举后两种方式都通。
3. 顺带删掉入口未使用的 `import inspect`。

## 四、验证

| 项 | 结果 |
|:--|:--|
| 搬运保真 | AST 逐函数源码比对：36 个块全部一致，无遗漏 |
| 编译 | `python -m py_compile mcp_server.py functions/*.py` 通过 |
| 导入方式 | 绝对路径当脚本 ✅；换 cwd ✅；`spec_from_file_location` ✅ |
| 真实 MCP 握手（stdio） | `initialize` → `tools/list` 5 个工具、`validate_parameters` valid=true、`calculate`（分腿）→ 红利 A0 2.40%/3.00%、1,000–800；双创 A2 7.73%/6.44%、700–700；使用率 54.3%、资金倍数 1.2、`get_manifest`／`list_systems` 正常，进程 stderr 为空 |
| 沙盒回归（`PI_PROJECT_DIR=/tmp/gridsbx`） | 12 组参数矩阵、保底仓、停买/恢复线、买入封顶、9 条参数错误路径；分腿 4 组 + 5 条错误路径；`risk_facts`／`sector_facts`／`render` 全部通过 |

## 五、文档同步

- `交易/交易体系/红利科创ETF双网格体系/MCP介绍.md`：运行定义目录树改为「入口 + functions/ 七个模块」并写明依赖方向；
- `体系介绍.md`、`体系运作流程.md`（运行定义行、变更执行顺序第 1 步）：实现位置改为 `functions/`；
- `system.yml` 与 `.pi/mcp.json` 不变（入口路径与契约未变）。

## 六、遗留

- 入口需重启或新会话后才加载新结构；运行中会话内的 MCP 仍是旧进程。
- 三个其它体系仍为单文件；是否照此拆分（以及是否抽 `trade-system/common/`）待定，见 `.scratch-space/MCP-体系目录拆分方案.md`。
