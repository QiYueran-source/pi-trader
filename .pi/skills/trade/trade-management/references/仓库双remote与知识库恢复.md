# 历史：旧 Hermes 双 remote 与知识库恢复

> 本文只用于解释历史工作区、旧远程和旧知识图谱/检索增强生成（KG/RAG）资料。它不属于当前落盘、归档、同步或交易流程。当前项目不得按本文命令切换旧工作区、恢复旧分支、执行旧同步或直接写数据库。

> 2026-08-05 仓库重构后首次发现。适用于所有在 /hermes-trader 知识库上工作的 cron 任务（ETF轮动 1810/1815/1820、回调低吸、财经分析等）。

## 仓库拓扑（2026-08-05 重构后）

| 项 | 值 |
|---|---|
| `origin` | `git@github.com:QiYueran-source/hermes-trader.git` — **sanitized 清洗版** |
| `personal` | `git@github.com:QiYueran-source/personal_hermes-trader_vault.git` — **完整知识库** |
| 本地分支 `hermes-trader` | 2026-08-05 12:57 `Initialize sanitized Hermes workspace` 重建的孤儿分支（与 `personal/hermes-trader` **无共同祖先**，`git merge-base` 为空） |
| `origin/hermes-trader` | == 本地 HEAD（清洗版，全仓 ~50 文件，knowledge 仅 ~34 个 md） |
| `personal/hermes-trader` | 668 commits / 636 个 knowledge 文件（完整） |
| KG 数据库 | `/opt/data/skills/knowledge-graph/database/knowledge_graph.db`，577 docs 索引完整 |
| RAG 数据库 | `/opt/data/skills/ali-bailian-rag/database/bailian_rag.db`，127 file_mappings |

⚠️ **KG/RAG 有索引 ≠ 文件系统有文件**。清洗后文件物理缺失但索引保留，仅凭 KG 检索结果会误以为文档存在。

## 症状

- 读 `knowledge/交易/交易计划/{日期}/基于Agent的ETF轮动体系_交易计划.md` 等报 `File not found`
- 同链路 cron（如 agent-etf-rotation-1810-replay-execute）因找不到计划文件返回 `[SILENT]`（agent.log 确认）——这是**环境异常信号**，不是正常"无交易/非交易日"静默
- `git status` 显示 working tree clean，但 `find knowledge -name "*.md" | wc -l` 只有 ~30（正常 600+）
- 本地 `cronjob/system/agent-etf-rotation/` 目录也缺失（prompt.txt 只在 personal 分支）
- **generate-plan「运行 ok 但无产出」（2026-08-05 实测）**：`hermes cron list` 显示 1835-generate-plan Last run ok，但次日计划文件在 origin 清洗版与 personal 完整版两份分支的 `交易计划/{次日}/` 下均不存在——这是上游计划链路在清洗态下断裂的信号，下游 1825-execute 会按规则"无计划→静默跳过"，1830-review 则容易误判为"无信号/体系正常"。**判定方法**：① `hermes cron list` 查上游 generate-plan 的 Last run；② `git ls-tree` 查两份分支计划目录确认文件确实不存在；③ 对照上一日复盘是否预判了当日动作（预判了却无计划 = 环境异常，必须在复盘中标注，不能当正常"无交易"处理）

## 恢复读取（不改文件系统，用于复盘/生成内容）

```bash
cd /hermes-trader
git show personal/hermes-trader:knowledge/交易/交易计划/2026-08-05/基于Agent的ETF轮动体系_交易计划.md
git show personal/hermes-trader:knowledge/交易/交易复盘/2026-08-04/基于Agent的ETF轮动体系.md
git show personal/hermes-trader:knowledge/交易/交易体系/基于Agent的ETF轮动体系/体系介绍.md
```

- 先确认路径存在：`git ls-tree -r personal/hermes-trader --name-only -z | tr '\0' '\n' | grep <关键词>`
- 路径含中文时用完整相对路径（git 输出可能带引号转义，用 -z + tr 处理）
- ⚠️ **naive grep 静默漏报（2026-08-05 实测）**：`git ls-tree -r --name-only personal/hermes-trader | grep "热门板块"` 返回空，容易误判"personal 分支也没有该文档"。原因是 git 对非 ASCII 路径默认 octal 转义输出（`"\344\272\244..."`），中文关键词永远匹配不到。必须用 `-z | tr '\0' '\n'` 还原后再 grep，或直接 `git show "personal/hermes-trader:<完整中文路径>"` 验证文件确实存在

## 恢复文件系统（需落盘/同步时）

```bash
cd /hermes-trader
git checkout personal/hermes-trader -- knowledge/交易/交易体系/基于Agent的ETF轮动体系/
# 或按需 checkout 单个缺失文件
```

- 落盘复盘/计划 + KG sync + Git push 依赖文件系统存在，缺失时必须先恢复（RAG 已停用，不同步 RAG）
- 恢复会引入大量文件变更；若疑似用户有意 sanitize（开源准备 open_sourcing/ 目录），在简报中标注环境异常并说明恢复范围，不要静默吞掉
- **复盘落盘用最小恢复集（2026-08-05 实测）**：只需 checkout 复盘文档 frontmatter `links` 指向的目标文件（体系介绍、上一日计划、上一日复盘）+ 工具脚本（如 `cronjob/utils/ts_cache.py`），不必恢复整个体系目录。这样既满足 frontmatter hook 的目标存在性校验，又把对清洗版工作区的污染降到最低。恢复后 git 状态会显示一批 `A` 新文件——提交时在 commit message 里说明恢复范围
- ⚠️ **frontmatter hook 交互（2026-08-05 hook 部署后新增）**：`write_file` 写 knowledge/ 下的 `.md` 时，hook 会校验 `links[].path` 目标文件是否真实存在。若 sanitized workspace 中 link 目标缺失 → hook 直接 block 写操作，返回"目标不存在"错误明细。**解决方案**：写文件前，先用 `git checkout personal/hermes-trader -- <目标目录>` 把 link 指向的文件所在目录恢复到工作区，再落盘。仅 `git show` 读内容不够——hook 检查的是文件系统存在性，不是内容可读性。
- ⚠️ **孤立 commit 恢复法（2026-08-07 实测）**：`git checkout personal/hermes-trader` 只对已 push 到 personal 的文件有效。若目标文件在 personal 分支上不存在（如复盘 commit `7784671` 建于 rebase 链上、push 被拒成为孤立 commit），但本地 git 对象库里有内容，用 `git show <sha>:<path> > 工作区路径` 恢复（先 `mkdir -p` 目录）。恢复后同样需重新跑 `kg_cli.py sync`（本次 8/6 复盘恢复后 sync 成功），再随本次复盘一起 `git add` 提交补齐历史缺口。

## 推送目标陷阱

- `git config` 中 `branch.hermes-trader.remote=personal`、`pushremote=personal`，但 cron prompt 模板写的是 `git push origin hermes-trader`
- 提交前 `git switch hermes-trader` 确认分支。**推送/暂存规则冲突时以 PROGRAM.md 为准（2026-08-07 实测）**：PROGRAM.md 是用户级规则（只允许 `personal` 远程、只允许显式 `git add knowledge cronjob`、禁止 `git add -A`/`git add .`、禁止对 origin fetch/pull/push），cron prompt 是任务模板（常写 `git add -A` + `git push origin`）。本次按 PROGRAM.md 执行：`git pull --ff-only personal hermes-trader` → `git add knowledge/...`（显式路径）→ `GIT_SSH_COMMAND=... git push personal hermes-trader`，成功（ee29d87..70b6692）。**不要照抄 cron prompt 里的 origin/add -A 命令**，沙箱会拦截且不符合用户规则；正确做法是显式暂存本次新增文件 + push personal。
- **`.abstract/` 简报不纳入 git（2026-08-05 实测）**：`knowledge/摘要/.abstract/` 在 .gitignore 中，写完简报后 `git commit` 显示 "nothing to commit" 是正常行为，不要 `git add -f` 强提；简报由 23:30 聚合任务消费。同理 `git check-ignore -v` 可确认某文件被忽略的原因
