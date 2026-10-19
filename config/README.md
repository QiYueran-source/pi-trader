# 部署配置

本目录是容器运行时的唯一配置来源，只读挂载到容器 `/opt/pi-config`。
启动时由 `entrypoint.sh` 同步到 Pi 的 agent 目录（`/home/node/.pi/agent`），
因此业务工作目录里的 `.pi/` 只承担项目级内容（技能、MCP、SYSTEM.md、定时任务）。

## 文件

| 文件 | 作用 | 必填 |
|---|---|---|
| `models.json` | 模型 provider 与模型清单；`PI_MODEL` 未设置时取第一个 provider 的第一个模型 | 是 |
| `settings.json` | agent 级 Pi 设置（例如默认包声明），存在时覆盖卷内同名文件 | 否 |
| `mcp.json` | agent 级 MCP 服务器；项目级 `mcp.json` 存在时以项目级为准 | 否 |
| `SYSTEM.md` / `APPEND_SYSTEM.md` | agent 级系统提示；项目级同名文件优先 | 否 |

## 约定

- 修改配置后重启容器即可生效：`docker compose up -d --force-recreate`。
- 不要在容器内的 `/home/node/.pi/agent` 手工改文件，下次启动会被覆盖。
- API key 走 `.secrets.env` 的环境变量，`models.json` 里用 `$VAR` 形式引用，不写明文。
