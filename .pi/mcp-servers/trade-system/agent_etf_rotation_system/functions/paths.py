"""路径、系统常量、基础 IO 与过程资料／复盘目录解析。

`__file__` 深度只在本模块推导一次，其它模块一律从这里取常量。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent
SYSTEM_ROOT = MODULE_ROOT.parent
REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = SYSTEM_ROOT.parents[3]
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "基于Agent的ETF轮动体系"
SYSTEM_VERSION = "v1"
PARAMETER_FILES = ("runtime", "universe")
CONTENT_ROOT_NAMES = ("knowledge", "archive")
REVIEW_ARTIFACTS = ("review",)
if not PARAMS_ROOT.is_dir():
    raise RuntimeError(f"体系参数目录缺失：{PARAMS_ROOT}")

def load_env() -> None:
    env_file = REPO_ROOT / ".pi/mcp-servers/tushare/.env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

def normalize_date(value: str | None) -> tuple[str, str]:
    if value is None:
        parsed = date.today()
    else:
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYY-MM-DD 或 YYYYMMDD：{value}") from exc
    return parsed.strftime("%Y%m%d"), parsed.strftime("%Y-%m-%d")

def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"JSON 文件不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无效：{path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须是对象：{path}")
    return value

def logical_root(field: str) -> str:
    raw = str(read_json(PARAMS_ROOT / "runtime.json")[field])
    return raw.split("/", 1)[1] if raw.startswith("knowledge/") else raw

def logical_process_root() -> str:
    return logical_root("process_root")

def review_dir(directory_date: str) -> Path:
    return REPO_ROOT / "knowledge" / logical_root("review_root") / directory_date
