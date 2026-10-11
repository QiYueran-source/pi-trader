#!/bin/sh

# Shared private environment loading and CLI credential synchronization.

TENCENT_NEWS_ENV_SOURCE="none"
TENCENT_NEWS_ENV_ERROR=""

load_tencent_news_env() {
  skill_dir="$1"
  env_file="$skill_dir/.env"

  TENCENT_NEWS_ENV_SOURCE="none"
  TENCENT_NEWS_ENV_ERROR=""

  if [ -n "${TENCENT_NEWS_API_KEY:-}" ]; then
    TENCENT_NEWS_ENV_SOURCE="process"
  elif [ ! -f "$env_file" ]; then
    TENCENT_NEWS_ENV_ERROR="missing environment file: $env_file"
    return 1
  else
    set -a
    if ! . "$env_file"; then
      set +a
      TENCENT_NEWS_ENV_ERROR="failed to load environment file: $env_file"
      return 1
    fi
    set +a
    TENCENT_NEWS_ENV_SOURCE="skill-env"
  fi

  case "${TENCENT_NEWS_API_KEY:-}" in
    ""|your_api_key)
      TENCENT_NEWS_ENV_ERROR="TENCENT_NEWS_API_KEY is not configured in $env_file"
      return 1
      ;;
  esac

  return 0
}

read_cli_api_key() {
  cli_path="$1"
  output="$("$cli_path" apikey-get 2>&1)" && exit_code=0 || exit_code=$?

  if [ "$exit_code" -eq 0 ]; then
    key="$(
      printf '%s\n' "$output" |
        sed -n 's/.*API Key[[:space:]]*:[[:space:]]*//p' |
        head -n 1 |
        tr -d '[:space:]' |
        sed "s/^['\"]//; s/['\"]$//"
    )"
    [ -n "$key" ] || return 2
    printf '%s\n' "$key"
    return 0
  fi

  if [ "$exit_code" -eq 2 ] || printf '%s\n' "$output" | grep -qiE '未设置 API Key|not set'; then
    return 1
  fi

  return 2
}

sync_tencent_news_api_key() {
  cli_path="$1"
  current_key="$(read_cli_api_key "$cli_path")" && key_status=0 || key_status=$?

  if [ "$key_status" -eq 0 ] && [ "$current_key" = "$TENCENT_NEWS_API_KEY" ]; then
    return 0
  fi

  [ "$key_status" -ne 2 ] || return 2

  if ! "$cli_path" apikey-set "$TENCENT_NEWS_API_KEY" >/dev/null 2>&1; then
    return 3
  fi

  return 0
}