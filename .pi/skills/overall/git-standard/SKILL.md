# Git 工作规范

本项目的 AI Git 操作遵循两条边界：

- 只在 `trader` 分支工作。
- 只向 `personal` 远程仓库推送。

`deploy` 分支用于部署配置，不作为 AI 的工作分支。`origin` 不属于允许操作的远程。

## 常用流程

```bash
git branch --show-current
git status --short
git diff --stat
git diff --check
```

提交前确认：

1. 当前分支为 `trader`；
2. 变更属于当前任务；
3. 没有把 `.env`、`.secrets.env`、数据库、私钥或其他敏感文件加入暂存区；
4. 已查看 staged diff；
5. 必要的语法或测试检查已经完成。

## 提交

只暂存本次任务明确涉及的路径，使用显式路径，不使用 `git add .` 或 `git add -A`：

```bash
git add <明确的文件或目录>
git diff --cached --stat
git diff --cached --check
git commit -m "<type>: <简短说明>"
```

提交类型按内容选择：

- `feat`：新增功能；
- `fix`：修复问题；
- `docs`：文档、技能或知识库内容；
- `refactor`：结构调整；
- `chore`：维护性改动。

## SSH 推送

宿主机 SSH 目录通过 `.env` 中的 `SSH_HOST_PATH` 配置，并由 Compose 只读挂载到容器的 `/home/node/.ssh`。容器内使用挂载后的路径，不直接访问宿主机绝对路径。

推送前先确认：

```bash
git branch --show-current
git remote -v
```

只允许显式推送到 `personal`：

```bash
GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  git push personal trader
```

如果远程分支尚未建立，可以在确认目标仍为 `personal` 后使用：

```bash
GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  git push -u personal trader
```

不使用省略远程的 `git push`，也不对 `origin` 执行 fetch、pull 或 push。

## Git Guard

项目提供独立的 TypeScript 扩展 `.pi/extensions/git-guard/git-guard.ts`。它在 Bash/Terminal 工具执行 Git 命令前检查：

- 当前分支是否为 `trader`；
- 命令是否涉及 `deploy` 分支；
- 命令是否涉及 `origin` 远程；
- `git push` 是否显式指定 `personal`。

不满足条件时，扩展会阻断工具调用并说明原因。`git branch --show-current` 作为诊断命令保留，用于确认当前分支。

Git Guard 只执行分支和远程边界检查，不负责文件范围、提交内容、测试结果或提交信息审查；这些检查按本规范在提交前完成。
