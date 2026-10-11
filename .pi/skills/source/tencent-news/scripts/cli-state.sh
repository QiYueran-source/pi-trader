#!/bin/sh
set -e

# cli-state.sh — Output install state, version/update status, and API key status.
# Usage: sh scripts/cli-state.sh

# ── helpers ──────────────────────────────────────────────────────────
fail() { echo "Error: $1" >&2; exit 1; }

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g' | tr '\n' ' '
}

json_bool() {
  echo "$1" | grep "\"$2\"" | head -1 | sed 's/.*"'"$2"'"[[:space:]]*:[[:space:]]*\([a-z]*\).*/\1/'
}

resolve_command_cli_path() {
  resolved_path="$(command -v "$1" 2>/dev/null || true)"
  if [ -z "$resolved_path" ]; then
    return 1
  fi

  if "$resolved_path" help >/dev/null 2>&1; then
    printf '%s\n' "$resolved_path"
    return 0
  fi

  return 1
}

# ── argument parsing ─────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    help)
      echo "Usage: sh scripts/cli-state.sh"
      echo ""
      echo "Print install state, version/update status, and API key status."
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

# ── platform detection ───────────────────────────────────────────────
detect_os() {
  case "$(uname -s)" in
    Darwin) echo "darwin" ;;
    Linux)  echo "linux" ;;
    *)      fail "unsupported os: $(uname -s)" ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    arm64|aarch64) echo "arm64" ;;
    x86_64|amd64)  echo "amd64" ;;
    *)             fail "unsupported architecture: $(uname -m)" ;;
  esac
}

OS="$(detect_os)"
ARCH="$(detect_arch)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_HELPER="$SCRIPT_DIR/env.sh"
[ -f "$ENV_HELPER" ] || fail "environment helper not found: $ENV_HELPER"
. "$ENV_HELPER"

CLI_FILENAME="tencent-news-cli"
LOCAL_CLI_PATH="$SKILL_DIR/$CLI_FILENAME"
INSTALL_ROOT="${TENCENT_NEWS_INSTALL:-${HOME:-}/.tencent-news-cli}"
BIN_DIR="$INSTALL_ROOT/bin"
GLOBAL_CLI_PATH="$BIN_DIR/$CLI_FILENAME"

# ── cli detection: global command > global install path > legacy local path ──
CLI_SOURCE="none"
CLI_PATH="$GLOBAL_CLI_PATH"
COMMAND_CLI_PATH="$(resolve_command_cli_path "$CLI_FILENAME" || true)"

if [ -n "$COMMAND_CLI_PATH" ]; then
  CLI_PATH="$COMMAND_CLI_PATH"
  CLI_SOURCE="global"
elif [ -f "$GLOBAL_CLI_PATH" ]; then
  CLI_SOURCE="global"
elif [ -f "$LOCAL_CLI_PATH" ]; then
  CLI_PATH="$LOCAL_CLI_PATH"
  CLI_SOURCE="local"
fi

if [ "$CLI_SOURCE" != "none" ]; then
  CLI_EXISTS="true"
else
  CLI_EXISTS="false"
fi

# ── update check ────────────────────────────────────────────────────
UPDATE_NEED_UPDATE="null"
UPDATE_ERROR="null"

if [ "$CLI_EXISTS" = "true" ]; then
  chmod +x "$CLI_PATH" 2>/dev/null || true

  VERSION_OUTPUT="$("$CLI_PATH" version 2>&1)" && VERSION_EXIT=0 || VERSION_EXIT=$?

  if [ "$VERSION_EXIT" -eq 0 ]; then
    if echo "$VERSION_OUTPUT" | grep -q '"need_update"'; then
      NEED_UPDATE="$(json_bool "$VERSION_OUTPUT" "need_update")"
      case "$NEED_UPDATE" in
        true|false)
          UPDATE_NEED_UPDATE="$NEED_UPDATE"
          ;;
        *)
          UPDATE_ERROR="\"$(json_escape "$CLI_PATH version did not return valid need_update value: ${VERSION_OUTPUT:-"(empty output)"}")\""
          ;;
      esac
    else
      UPDATE_ERROR="\"$(json_escape "$CLI_PATH version did not return valid JSON: ${VERSION_OUTPUT:-"(empty output)"}")\""
    fi
  elif [ -n "$VERSION_OUTPUT" ]; then
    UPDATE_ERROR="\"$(json_escape "$VERSION_OUTPUT")\""
  else
    UPDATE_ERROR="\"$(json_escape "$CLI_PATH version failed with exit code $VERSION_EXIT.")\""
  fi
fi

# ── api key state ────────────────────────────────────────────────────
APIKEY_STATUS="missing"
APIKEY_PRESENT="false"
APIKEY_SOURCE="none"
APIKEY_ERROR="null"

if load_tencent_news_env "$SKILL_DIR"; then
  APIKEY_STATUS="configured"
  APIKEY_PRESENT="true"
  APIKEY_SOURCE="$TENCENT_NEWS_ENV_SOURCE"
elif [ ! -f "$SKILL_DIR/.env" ] && [ -z "${TENCENT_NEWS_API_KEY:-}" ]; then
  APIKEY_ERROR="\"$(json_escape "$TENCENT_NEWS_ENV_ERROR")\""
elif [ -z "${TENCENT_NEWS_API_KEY:-}" ] || [ "${TENCENT_NEWS_API_KEY:-}" = "your_api_key" ]; then
  APIKEY_ERROR="\"$(json_escape "$TENCENT_NEWS_ENV_ERROR")\""
else
  APIKEY_STATUS="error"
  APIKEY_ERROR="\"$(json_escape "$TENCENT_NEWS_ENV_ERROR")\""
fi

# ── output JSON ──────────────────────────────────────────────────────
cat <<EOF
{
  "platform": {
    "os": "$OS",
    "arch": "$ARCH",
    "cliPath": "$CLI_PATH",
    "cliSource": "$CLI_SOURCE"
  },
  "cliExists": $CLI_EXISTS,
  "update": {
    "needUpdate": $UPDATE_NEED_UPDATE,
    "error": $UPDATE_ERROR
  },
  "apiKey": {
    "status": "$APIKEY_STATUS",
    "present": $APIKEY_PRESENT,
    "source": "$APIKEY_SOURCE",
    "error": $APIKEY_ERROR
  }
}
EOF
