---
name: git-standard
description: 约束项目中的 Git 分支、远程仓库、提交和 SSH 推送行为。涉及 Git 操作时使用。
---

# Git 规范

## 硬性规则

- AI 只在 `trader` 分支工作和提交。
- 禁止对 `deploy` 分支执行开发操作；从 `deploy` 恢复时只允许查看状态或切回 `trader`。
- 禁止对 `origin` 执行 push、pull、fetch。
- 推送必须显式使用 `personal` 远程和 `trader` 分支。
- 不使用省略远程名称的 `git push`。

## 开始任务

```bash
git branch --show-current
git status --short
```

确认当前分支为 `trader`，并检查已有修改是否属于当前任务。

## 提交时机

完成任务、检查测试和格式后再提交：

```bash
git diff --check
git diff --stat
git status --short
git add <本次任务涉及的明确路径>
git diff --cached --stat
git diff --cached --check
git commit -m "<type>: <简短说明>"
```

不要使用 `git add .` 或 `git add -A`。一次提交只包含一个相关任务。

## 推送

宿主机 SSH 目录由 `SSH_HOST_PATH` 配置，并以只读方式挂载到容器 `/home/node/.ssh`。容器可以使用密钥认证，但不能修改宿主机密钥。

```bash
GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
git push personal trader
```

首次推送使用：

```bash
GIT_SSH_COMMAND="ssh -i /home/node/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
git push -u personal trader
```

禁止 `git push`、`git push origin ...` 和 `git push personal deploy`。

## 提交类型

- `feat`：新增功能
- `fix`：修复问题
- `docs`：文档、技能或知识库
- `refactor`：结构调整
- `chore`：维护

项目通过 `.pi/extensions/git-policy/git-policy.ts` 强制拦截违规 Git 命令。
