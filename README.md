# pi-trader-deploy

Pi Trader 的部署目录。只负责构建镜像和容器运行配置，业务数据、技能、MCP 与定时任务都在挂载进来的工作目录里。

## 目录

| 路径 | 作用 |
|---|---|
| `config/` | 部署配置，只读挂载到容器 `/opt/pi-config`，启动时同步到 Pi agent 目录 |
| `Dockerfile.pi` | 镜像定义：Node 24 + Pi CLI + Python venv（uv） |
| `docker-compose.yml` | 容器编排：挂载工作目录、SSH 目录、配置目录和 agent 命名卷 |
| `entrypoint.sh` | 启动脚本：同步配置、安装项目级扩展、解析默认模型后启动 `pi` |
| `requirements.txt` | Python 依赖，构建时装入 `/opt/venv` |

## 目录职责划分

```text
config/                部署侧配置（模型清单）
   └─ models.json

工作目录（PI_WORK_PATH_ON_HOST → 容器 /pi-trader）
   ├─ .pi/             项目级配置：skills、mcp.json、SYSTEM.md、定时任务
   ├─ knowledge/       正式文档
   └─ database/        数据库

容器 /home/node/.pi/agent
   └─ 命名卷，保存会话与启动时同步过来的 models.json
```

## 使用

```bash
cp .env.example .env
cp .secrets.env.example .secrets.env
# 填写 .env 中的挂载路径与 .secrets.env 中的密钥
docker compose up -d --build
docker compose exec pi bash
```

修改 `config/` 后需要重建容器才会生效：

```bash
docker compose up -d --force-recreate
```
