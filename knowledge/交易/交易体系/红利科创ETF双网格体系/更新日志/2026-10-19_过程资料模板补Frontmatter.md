---
title: 过程资料模板补 Frontmatter | 2026-10-19
summary: "周体检（2026-10-19 首次运行）发现双网格过程资料渲染产物的 Frontmatter 与同批模板不一致：`regulator_facts.md.j2` 完全没有 Frontmatter，`risk_facts.md.j2`／`sector_facts.md.j2` 有字段但缺 `summary`。本次按其余体系同类模板的口径补齐：三个模板的 Frontmatter 统一为 `title`／`summary`／`tags`／`date`／`system-id`，`summary` 只使用已存在的 `data.date` 与静态描述，保证 StrictUndefined 下不会因缺键渲染失败。模板每次渲染从磁盘读取，无需重启即生效；历史产物不回改。"
date: 2026-10-19
reason: 2026-10-19 每周落盘体检报告「建议修：过程资料产物 Frontmatter 口径不统一」；根因在模板而非产物本身
tags:
  - 交易体系
  - 更新日志
  - 网格
system-id: div_etf_grid_trade
system-name: 红利科创ETF双网格体系
---

# 过程资料模板补 Frontmatter | 2026-10-19

## 一、问题

| 模板 | 改前 | 改后 |
|:--|:--|:--|
| `templates/regulator_facts.md.j2` | 无 Frontmatter | `title`／`summary`／`tags`／`date`／`system-id` |
| `templates/risk_facts.md.j2` | 有 `title`／`tags`／`date`／`system-id`，缺 `summary` | 补 `summary` |
| `templates/sector_facts.md.j2` | 同上 | 补 `summary` |

- `summary` 文本只使用 `{{ data.date }}` + 静态描述（该变量在三个模板的标题行已在用），不引入新变量，StrictUndefined 下不会因缺键失败。
- 口径对齐对象：`hot_sector_pullback_system` 与 `agent_etf_rotation_system` 的 md 模板（均有 `summary`）、`zslof_timing_trade` 的 `signal_report.md.j2`（有 `summary`）。

## 二、验证

- 三个模板 `env.parse` 语法解析通过。
- `risk_facts.md.j2` 用 2026-10-16 真实 `risk_facts.json` 完整渲染成功，Frontmatter 五字段齐全。
- `sector_facts.md.j2`、`regulator_facts.md.j2` 的 Frontmatter 段单独渲染成功（标题/摘要/标签/日期/系统号）。
- 两个模板的正文段用 2026-10-16 旧结构 JSON 渲染仍失败（`data.limit_up`、`data.defense_level` 缺失）——该不兼容为既有状态（10-18 已裁定不回改旧产物），与本次改动无关。

## 三、边界与遗留

- 只改渲染模板，不动 `params/`、工具契约、渲染入参与历史产物。
- 模板由 `FileSystemLoader` 每次渲染时从磁盘读取，**无需重启即生效**；2026-10-19 18:00 双网格盘后任务生成的产物即为新 Frontmatter（可与 `T-2026-10-17-13` 首跑复核一并验收）。
- 2026-10-15 热门板块回调低吸体系 7 份手写产物（非模板渲染）无 Frontmatter，属历史产物，不回改。
