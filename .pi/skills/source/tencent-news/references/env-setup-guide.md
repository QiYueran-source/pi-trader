# tencent-news API Key 配置指南

## 获取 API Key

1. 打开浏览器访问 [API Key 获取页面](https://news.qq.com/exchange?scene=appkey)。
2. 按页面引导完成获取。

不要使用命令自动打开浏览器，也不要在对话、日志或提交中展示真实 Key。

## 配置技能私有环境

运行时配置文件位于：

```text
/opt/data/skills/data/tencent-news/.env
```

开发仓库中的对应位置为 `deploy/skills/data/tencent-news/.env`。从同目录 `.env.example` 创建真实配置，并填写：

```dotenv
TENCENT_NEWS_API_KEY=your_api_key
```

建议将真实 `.env` 权限设为仅所有者可读写：

```sh
chmod 600 /opt/data/skills/data/tencent-news/.env
```

进程环境变量 `TENCENT_NEWS_API_KEY` 优先于技能 `.env`。`scripts/run-cli.sh` 在业务命令执行前加载配置，并仅在 Key 缺失或变化时同步到 `tencent-news-cli` 的运行时配置。

## 验证

执行：

```sh
sh scripts/cli-state.sh
```

确认返回结果满足：

- `apiKey.status` 为 `configured`。
- `apiKey.present` 为 `true`。
- `apiKey.source` 为 `skill-env` 或 `process`。
- 输出中不包含真实 Key。

`help`、`version` 和 `update` 不依赖 API Key，可在 `.env` 尚未配置时运行。

## 修改或清除

轮换 Key 时直接更新技能 `.env`；下一次业务调用会自动同步。不要直接调用 `apikey-set`、`apikey-get` 或 `apikey-clear`，包装脚本会拒绝这些命令，避免技能配置与 CLI 内部状态形成两个配置真源。

如需停用凭据，删除技能 `.env` 中的 `TENCENT_NEWS_API_KEY` 或删除整个 `.env`。CLI 中可能仍保留上一次同步产生的派生副本，但所有技能业务调用都会因私有配置缺失而停止，不会继续使用旧 Key。

## 常见问题

- **`missing environment file`** → 从 `.env.example` 创建技能私有 `.env`。
- **`TENCENT_NEWS_API_KEY is not configured`** → 填写有效 Key，不要保留 `your_api_key` 占位值。
- **`failed to load environment file`** → 检查 `.env` 语法和读取权限；该文件通过 POSIX shell 加载，只应包含可信的 `KEY=value` 配置。
- **同步失败** → 确认 CLI 可执行且支持 `apikey-get`、`apikey-set`，然后重试业务命令。
- **找不到 `tencent-news-cli`** → 参考 [安装指南](installation-guide.md) 重新安装。
