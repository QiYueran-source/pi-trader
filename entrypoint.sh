#!/usr/bin/env bash
set -euo pipefail

# 项目目录由 Compose 挂载，项目级 Pi 配置和扩展必须在容器运行时安装，
# 这样安装结果会写回宿主机，而不是被项目挂载覆盖的镜像层。
PROJECT_DIR="${PI_PROJECT_DIR:-/pi-trader}"
FEISHU_PACKAGE="${PI_FEISHU_PACKAGE:-npm:pi-feishu@1.1.5}"
PROJECT_SETTINGS="$PROJECT_DIR/.pi/settings.json"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "错误：项目目录不存在：$PROJECT_DIR" >&2
  exit 1
fi

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/.pi"

# 首次启动时自动安装项目级飞书扩展；之后只要 settings.json 中已有声明就跳过。
if [[ ! -s "$PROJECT_SETTINGS" ]] || ! grep -q "pi-feishu" "$PROJECT_SETTINGS"; then
  echo "安装项目级飞书扩展：$FEISHU_PACKAGE" >&2
  pi install --local --approve "$FEISHU_PACKAGE"

  # 容器默认以 root 运行，尽量把新生成的项目配置归还给挂载目录的宿主用户。
  PROJECT_UID="$(stat -c '%u' "$PROJECT_DIR" 2>/dev/null || true)"
  PROJECT_GID="$(stat -c '%g' "$PROJECT_DIR" 2>/dev/null || true)"
  if [[ "$PROJECT_UID" =~ ^[0-9]+$ && "$PROJECT_UID" != 0 ]]; then
    chown -R "$PROJECT_UID:${PROJECT_GID:-$PROJECT_UID}" "$PROJECT_DIR/.pi" 2>/dev/null || true
  fi
fi

# Pi 的全局配置目录由 Compose 的命名卷提供，models.json 由宿主机只读挂载。
MODEL_CONFIG="${PI_MODEL_CONFIG:-/root/.pi/agent/models.json}"

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

# 如果调用方已经显式传入 --model，则尊重调用方的选择。
for arg in "$@"; do
  if [[ "$arg" == "--model" || "$arg" == "-m" ]]; then
    exec pi "$@"
  fi
done

echo "启动 Pi，模型：$MODEL" >&2

# -a 自动信任项目配置；pi-feishu 扩展加载后负责建立飞书连接。
exec pi -a --model "$MODEL" "$@"
