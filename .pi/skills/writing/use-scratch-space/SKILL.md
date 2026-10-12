---
name: use-scratch-space
description: 管理不确定、待确认或尚未整理的内容。需要暂存草稿、无法确定正式路径或内容尚未确认时必须使用，避免未经确认的内容进入正式知识库。
---

# 草稿箱

## 规则

- 不确定归属、格式或内容时，先写入 `.scratch-space/`。
- 草稿保留原始内容，不直接视为正式知识库文档。
- 确认后再移动到正式目录，并按对应技能整理。
- 草稿默认保留 7 天，超过期限由 `scratch-space-management` 定时清理。
- 不在草稿箱保存密钥、密码或其他敏感凭据。

## 工具

- `scratch-space-management.scratch_list`：查看草稿。
- `scratch-space-management.scratch_preview_cleanup`：预览过期草稿。
- `scratch-space-management.scratch_cleanup`：清理过期草稿。
