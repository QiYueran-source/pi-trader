# MCP 工具

服务名：`financial-analysis`；行情另用服务 `tushare-data`。

## 数据库工具（参数已按实际 schema 核对）

| 工具 | 参数 | 说明 |
|:---|:---|:---|
| `financial_analysis_list_mentions` | `mention_date` / `source_type` / `source_file` / `name` / `code` / `type` / `limit`（默认 200，上限 1000） | 查询判断记录，全部筛选项可选 |
| `financial_analysis_record_mentions` | **`items`：判断对象数组（必填）** | 批量新增，重复项自动跳过 |
| `financial_analysis_replace_mentions` | **`mention_date`（必填）＋ `source_file`（必填）＋ `items`（必填）** | 按日期和来源文件原子替换；`items` 内可省略这两个字段 |
| `financial_analysis_active_items` | `as_of`（默认今天） | 查询「`window_end_date >= as_of`」的标的 |
| `financial_analysis_record_performance` | **`items`：行情对象数组（必填）**，每条至少 `name`、`track_date` | `code` / `pct_chg` / `volume` / `check_time` 可选 |
| `financial_analysis_list_performance` | `name` / `code` / `track_date` / `limit` | 查询行情跟踪 |
| `financial_analysis_review_date` | **`review_date`（必填）**＋ `source`（模糊匹配 `source_file`） | 返回判断、验证日期和窗口内行情 |
| `financial_analysis_stats` | `days`（默认 30，上限 3650）＋ `source` | 方向判断准确率 |

判断对象字段：`name`、`code`、`type`、`mention_date`、`source_type`、`source_file`、`sentiment`、`context`、`window_end_date`。

### 参数形状（易错点）

- 批量写入的参数名是 **`items`**，不是 `mentions`；写成 `mentions` 会被 schema 校验直接拒绝。
- `replace_mentions` 的 `mention_date` 与 `source_file` 传在**顶层**，`items` 里不必重复。
- 枚举由 MCP 校验：`type` ∈ {stock, sector}；`sentiment` ∈ {积极, 中性, 消极, 谨慎}；`source_type` ∈ {盘前分析, 盘前荐股, 盘后荐股, 盘后分析, 周末要闻, 调仓信息}。`sentiment` 缺省为 `中性`。

## 行情工具

服务名：`tushare-data`

- `get_stock_daily`：个股日线。
- `get_index_daily`：指数日线。
- `get_stock_basic`：**只接受 `ts_code`**，用于由代码反查名称；没有按名称反查的接口。
- `get_trade_calendar`：确定交易日与下一交易日。

## 约束

- 先读后写：写入前先 `financial_analysis_list_mentions` 查重，按「日期 + 来源文件」判断用 record 还是 replace。
- **先列清单再入库**：用户要求整理财经分析时，默认先把待入库清单列给用户，确认后才写库（字段与校验见 `mentions.md`）。
- 覆盖来源文件用 `financial_analysis_replace_mentions`，不要手动删除旧记录。
- 批量写入后核对返回的 `inserted` / `skipped` / `deleted`，再 `list_mentions` 复核条数。
- 数据库写入只使用业务工具，不执行任意 SQL。行情来源和日期必须与复盘对象一致。
- 失败时按返回的 `error.type` 与 `error.message` 定位：`invalid_request` 属参数或枚举问题，`internal_error` 属服务端问题；不要把失败当成空结果。
- MCP 只校验必填与枚举；名称、代码、窗口、路径等口径由 `mentions.md` 的「入库校验」清单强制。
