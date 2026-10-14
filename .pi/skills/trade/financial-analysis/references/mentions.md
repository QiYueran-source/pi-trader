# 判断记录规则

数据库由 `financial-analysis` MCP 管理，位置由 MCP 配置注入。技能不直接访问 SQLite。

## mentions 字段

- `name`：个股或板块名称。
- `code`：个股代码，必须带交易所后缀；板块可空。
- `type`：`stock` 或 `sector`。
- `mention_date`：内容发布日期。
- `source_type`：盘前分析、盘前荐股、盘后荐股、盘后分析、周末要闻、调仓信息。
- `source_file`：相对 `knowledge/` 的 Markdown 路径。
- `sentiment`：积极、中性、消极、谨慎。
- `context`：简短说明判断依据。
- `window_end_date`：跟踪窗口结束日。

## 入库校验

MCP 只校验：必填字段（`name`/`type`/`mention_date`/`source_type`/`source_file`）、`type`、`source_type`、`sentiment` 的枚举，以及日期格式。**下列项目 MCP 拦不住，由本技能逐条强制**：

| 项 | 规则 |
|:---|:---|
| `name` | 去首尾空白；板块 ≤10 字且不含标点与功能词；个股用**代码**在 `tushare stock_basic` 反查名称核对——**按名称反查代码不可行**（`get_stock_basic` 只接受 `ts_code`，`get_market_daily` 不返回名称），名称有疑问时人工确认或请用户裁决 |
| `code` | `type=stock` 时**必填**，匹配 `^\d{6}\.(SH\|SZ\|BJ)$`，且与 `name` 一致 |
| `type` | 个股=`stock`；板块/指数/题材=`sector`；判断不了就不录 |
| `mention_date` | = 内容发布日期，不是整理日、不是验证日 |
| `window_end_date` | **必填**，按「窗口」计算。MCP 本身不强制（缺失写 NULL），但 `active_items` 靠 `window_end_date >= as_of` 过滤，**漏填＝该条永不进入跟踪窗口** |
| `source_type` | 与来源文件一一对应（如 `开源证券-盘前分析.md` → 盘前分析） |
| `source_file` | 动态知识的逻辑路径，新写入一律使用当前逻辑路径。文件归档只改变物理位置，不修改该字段；历史路径按兼容规则读取。 |
| `context` | 用原文片段（≤100 字），不改写、不编造、不跨句拼接 |

## 名称与反例

能否录入看两点：**这个 `name` 是可跟踪的标的吗（个股代码或板块名）？这条判断能被原文一句话直接支撑吗？** 两头都不满足，就是碎片，不录。

碎片反例（历史实际出现过的错误录入）：`那该板块`、`而不是一个方向`、`当前的指数`、`科创已经达到极致`、`其他板块`、`属于超跌轮动板块`。

## 提取

只记录对未来的明确判断：推荐个股、板块方向、风险判断和调仓建议。事实描述不录入。

- 周末要闻的“关注企业”按板块参考处理，通常记录为 `sector`。
- 盘前/盘后荐股中的明确推荐记录为 `stock`。
- 调仓移入记录为 `stock`，当天生效。

## 窗口

窗口从 `mention_date` 起算，`window_end_date` **必填**：

- 短线、近日、博弈、谨慎、风险：3 天。
- 无明确修饰：5 天。
- 趋势向好、主升、中期、延续：10 天。
- 长期、业绩驱动、政策、进口替代：44 天。

判定顺序：先找原文修饰词 → 落到上表某一档 → 按 `mention_date + N 天` 计算 → 写入。写入前核对同来源历史记录，避免重复或窗口错误。

## 写入：先列清单，再入库

1. **先列出待入库清单**（`name` / `code` / `type` / `sentiment` / `window_end_date` / `context` 一行一条）给用户过目。用户要求"整理财经分析"时，**默认先列清单、得到确认后再写库**。
2. `financial_analysis_list_mentions(mention_date, source_file)` 查重。
3. 无记录 → `record_mentions`；已有记录 → `replace_mentions`（原子替换，不要先手动删除）。
4. 核对返回的 `inserted` / `skipped` / `deleted` 数量。
5. 再 `list_mentions` 复核条数与内容。

自动提取只作建议：清单里每一条都要能对上原文的一句话，确认后才调用写入工具。
