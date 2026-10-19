#!/usr/bin/env bash
set -euo pipefail

# 部署配置与业务工作目录分离：
#   /opt/pi-config  只读挂载的部署配置（config/），models.json 等模型与运行配置在这里维护
#   /home/node/.pi/agent  Pi 的 agent 目录，由命名卷持久化，启动时从 config/ 同步
#   /pi-trader      业务工作目录，包含项目级 .pi（技能、MCP、SYSTEM.md、定时任务）
CONFIG_DIR="${PI_CONFIG_DIR:-/opt/pi-config}"
AGENT_DIR="${PI_CODING_AGENT_DIR:-/home/node/.pi/agent}"
PROJECT_DIR="${PI_PROJECT_DIR:-/pi-trader}"
MODEL_CONFIG="${AGENT_DIR}/models.json"

FEISHU_PACKAGE="${PI_FEISHU_PACKAGE:-npm:pi-feishu@1.1.5}"
SCHEDULE_PACKAGE="${PI_SCHEDULE_PACKAGE:-npm:pi-schedule-prompt}"
PROJECT_SETTINGS="${PROJECT_DIR}/.pi/settings.json"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "错误：项目目录不存在：$PROJECT_DIR" >&2
  exit 1
fi

# 把部署配置同步到 agent 目录。config/ 是唯一来源，卷内副本每次启动覆盖。
if [[ ! -d "$CONFIG_DIR" ]]; then
  echo "错误：配置目录不存在：$CONFIG_DIR" >&2
  exit 1
fi

mkdir -p "$AGENT_DIR"

if [[ ! -f "${CONFIG_DIR}/models.json" ]]; then
  echo "错误：缺少模型配置：${CONFIG_DIR}/models.json" >&2
  exit 1
fi
install -m 0644 "${CONFIG_DIR}/models.json" "$MODEL_CONFIG"

# 其余配置文件按存在与否选择性同步，缺失时保持卷内原状。
for name in settings.json mcp.json APPEND_SYSTEM.md SYSTEM.md; do
  if [[ -f "${CONFIG_DIR}/${name}" ]]; then
    install -m 0644 "${CONFIG_DIR}/${name}" "${AGENT_DIR}/${name}"
  fi
done

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/.pi"

# settings.json 中是否已声明某个包；文件不存在时视为未声明。
declared() {
  [[ -s "$PROJECT_SETTINGS" ]] && grep -q "$1" "$PROJECT_SETTINGS"
}

# 项目级扩展安装：settings.json 已声明则跳过，避免每次启动重复安装。
if ! declared "pi-feishu"; then
  echo "安装项目级飞书扩展：$FEISHU_PACKAGE" >&2
  pi install --local --approve "$FEISHU_PACKAGE"
fi

if ! declared "pi-schedule-prompt"; then
  echo "安装项目级定时任务扩展：$SCHEDULE_PACKAGE" >&2
  pi install --local --approve "$SCHEDULE_PACKAGE"
fi

if [[ ! -r "$MODEL_CONFIG" ]]; then
  echo "错误：找不到模型配置文件：$MODEL_CONFIG" >&2
  exit 1
fi

# 默认取 models.json 中第一个 provider 的第一个模型；PI_MODEL 可覆盖它。
if [[ -n "${PI_MODEL:-}" ]]; then
  MODEL="$PI_MODEL"
else
  MODEL="$(jq -er '
    .providers
    | to_entries[0] as $provider
    | $provider.key + "/" + $provider.value.models[0].id
  ' "$MODEL_CONFIG")" || {
    echo "错误：无法从 $MODEL_CONFIG 读取第一个模型" >&2
    exit 1
  }
fi

if [[ -z "$MODEL" || "$MODEL" == "null/null" ]]; then
  echo "错误：没有找到可用模型，请检查 $MODEL_CONFIG" >&2
  exit 1
fi

# 调用方显式传入 --model 时尊重调用方选择。
for arg in "$@"; do
  if [[ "$arg" == "--model" || "$arg" == "-m" ]]; then
    exec pi "$@"
  fi
done

echo "启动 Pi，模型：$MODEL" >&2

exec pi -a --model "$MODEL" "$@"
