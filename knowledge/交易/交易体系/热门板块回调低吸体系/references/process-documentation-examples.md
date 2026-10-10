---
uuid: 2d4eb8e3d9b441b29a9c4263e43f0e50
title: process-documentation-examples
tags:
  - 交易体系
  - 参考
updated: 2026-08-05 07:38:33
links: []
system-id: hot_sector_pullback_system
---

# 过程资料落盘实践参考 — 具体案例

> Migrated from `process-documentation-pattern/references/examples.md` (2026-07-05 consolidation).

## ETF 轮动体系

**System path:** `knowledge/交易/交易体系/基于Agent的ETF轮动体系/`
**System ID:** `agent_etf_rotation_system`

### Process doc files
- **Mandatory:** `ETF轮动-选股分析.md`
- **Timing:** After comprehensive analysis (1820-generate-plan prompt step 7)
- **7-step flow:** Data collection → Environment → Ranking → Review → Adjust → Risk → Conclusion

### Prompt key constraints
- Rule 6: "Analysis flow cannot be simplified: output can be concise, but data (tushare quotes), news (web_search), and all 4 risk dimensions cannot be skipped just because of long holding period or certain conclusion"
- Risk review with no changes: output "normal, no change" but section cannot disappear

### Actual output examples

| Date | Lines | Hold days | Characteristics |
|------|-------|-----------|-----------------|
| 6/17 | 112 | Day 1 (build) | Full 5 sections, risk = "cautious" (event risk rising) |
| 6/23 | 191 | Day 5 | Full 6 sections, complete candidate-by-candidate evaluation |
| 6/24 | 167 | Day 6 | Complete, detailed position review |
| 6/25 | 169 | Day 7 | Complete, 4-step adjustment logic |
| 6/26 | 75 | Day 8 | ⚠️ Skipped risk review & candidate ranking (needs fix) |

## 热门板块回调低吸体系

**System path:** `knowledge/交易/交易体系/热门板块回调低吸体系/`
**System ID:** `hot_sector_pullback_system`
**cronjob path:** `cronjob/system/hot-sector-pullback-system/`

### Process doc files
- **Mandatory:** `热门板块回调低吸-板块热度研判.md` (Step 1.5)
- **Optional:** `热门板块回调低吸-综合研判.md` (Step 4, only for complex decisions)
- **Timing:** 1835-generate-plan prompt Step 6.5 + Step 10.5

### Sector heat analysis content
- Candidate sector list + 4-dimension data summary
- Analysis per sector: why hot / why not
- Final selected hot industries and reasoning

### Comprehensive analysis content (optional)
- Candidate comparison: why A not B
- Holdings retention trade-off logic
- Final decision reasoning chain for buy/sell/hold
- Skip when no complex decision

### Trading plan frontmatter references

```yaml
links:
  - path: 交易/交易体系/热门板块回调低吸体系/体系介绍.md
    type: belongs_to_system
  - uuid: {板块热度研判报告uuid}
    path: 交易/过程资料/{date}/热门板块回调低吸体系/板块热度研判.md
    relations:
      - 依据
  - uuid: {综合研判报告uuid}
    path: 交易/过程资料/{date}/热门板块回调低吸体系/综合研判.md
    relations:
      - 依据
```

### Sync order
1. First sync process docs (KG)
2. Then sync trading plan (KG → RAG → Git)
3. Comprehensive analysis only sync when actually persisted
