"""路径、系统常量、基础 IO 与过程资料（含归档双头）解析。

`__file__` 深度只在本模块推导一次，其它模块一律从这里取常量。"""

from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import date, datetime
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent
SYSTEM_ROOT = MODULE_ROOT.parent
REPO_ROOT = Path(os.environ.get("PI_PROJECT_DIR", "/pi-trader")).expanduser()
if not REPO_ROOT.exists():
    REPO_ROOT = SYSTEM_ROOT.parents[3]
PARAMS_ROOT = SYSTEM_ROOT / "params"
TEMPLATES_ROOT = SYSTEM_ROOT / "templates"
SYSTEM_ID = SYSTEM_ROOT.name
SYSTEM_NAME = "热门板块回调低吸体系"
SYSTEM_VERSION = "v1"
PARAMETER_FILES = ("entry", "risk", "runtime", "sector_heat", "selection")
OPERATIONS = ("select_candidates", "sector_heat", "entry_signal", "risk_signal")
CONTENT_ROOT_NAMES = ("knowledge", "archive")
BENCHMARK_INDEX = "399006.SZ"
DAILY_SLEEP_SECONDS = 0.3
RISK_SLEEP_SECONDS = 5
HIT_LIMIT_EPSILON = 0.01
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
    elif isinstance(value, str):
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError as exc:
            raise ValueError(f"date 必须为 YYYYMMDD 或 YYYY-MM-DD: {value}") from exc
    else:
        raise ValueError("date 必须为 YYYYMMDD 或 YYYY-MM-DD")
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

def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)

def logical_root(field: str) -> str:
    raw = str(read_json(PARAMS_ROOT / "runtime.json")[field])
    return raw.split("/", 1)[1] if raw.startswith("knowledge/") else raw

def process_roots() -> list[tuple[Path, str]]:
    relative = logical_root("process_root")
    return [(REPO_ROOT / name / relative, name) for name in CONTENT_ROOT_NAMES]

def process_dir(directory_date: str, create: bool = False) -> Path:
    path = process_roots()[0][0] / directory_date / SYSTEM_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path

def resolve_process_file(directory_date: str, filename: str) -> Path | None:
    for root, _ in process_roots():
        candidate = root / directory_date / SYSTEM_NAME / filename
        if candidate.is_file():
            return candidate
    return None

def logical_process_path(directory_date: str, filename: str) -> str:
    return f"{logical_root('process_root')}/{directory_date}/{SYSTEM_NAME}/{filename}"

def load_process_document(directory_date: str, filename: str) -> dict[str, Any]:
    path = resolve_process_file(directory_date, filename)
    if path is None:
        raise ValueError(f"上游过程资料缺失：{logical_process_path(directory_date, filename)}")
    return read_json(path)

def latest_snapshot(run_api_date: str, filename: str, trade_days: list[str], back_n: int) -> tuple[Path, str] | None:
    earlier = sorted({normalize_date(str(item))[0] for item in trade_days if normalize_date(str(item))[0] < run_api_date})
    for trade_date in reversed(earlier[-back_n:]):
        directory_date = normalize_date(trade_date)[1]
        path = resolve_process_file(directory_date, filename)
        if path is not None:
            return path, trade_date
    return None
