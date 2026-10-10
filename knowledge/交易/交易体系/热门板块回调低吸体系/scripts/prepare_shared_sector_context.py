#!/opt/hermes/.venv/bin/python3
"""复用同日红利 ETF 网格的全市场板块环境事实。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_support import REPO_ROOT, normalize_date, process_dir

SOURCE_SYSTEM_ID = "div_etf_grid_trade"
SOURCE_SYSTEM_NAME = "红利ETF网格"
SOURCE_ARTIFACT = "sector_facts"
TARGET_ARTIFACT = "shared_sector_context"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="准备低吸体系共享板块环境事实")
    parser.add_argument("--date", required=True, help="运行日期，YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只输出结果，不写过程资料")
    return parser.parse_args()


def load_source(path: Path, target_date: str) -> dict:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"共享板块事实 JSON 无效: {path}: {exc.msg}") from exc

    if not isinstance(source, dict):
        raise ValueError(f"共享板块事实必须是对象: {path}")
    if source.get("date") != target_date:
        raise ValueError(f"共享板块事实日期不匹配: {source.get('date')} != {target_date}")
    if source.get("system_id") != SOURCE_SYSTEM_ID:
        raise ValueError(f"共享板块事实来源体系不匹配: {source.get('system_id')}")
    if source.get("artifact") != SOURCE_ARTIFACT:
        raise ValueError(f"共享板块事实类型不匹配: {source.get('artifact')}")
    if not isinstance(source.get("limit_up"), dict) or not isinstance(source.get("top_sectors"), list):
        raise ValueError("共享板块事实缺少 limit_up 或 top_sectors")
    return source


def main() -> None:
    args = parse_args()
    _, directory_date = normalize_date(args.date)
    source_path = (
        REPO_ROOT
        / "knowledge/交易/过程资料"
        / directory_date
        / SOURCE_SYSTEM_NAME
        / "sector_facts.json"
    )
    if not source_path.is_file():
        print(json.dumps({
            "date": directory_date,
            "artifact": TARGET_ARTIFACT,
            "available": False,
            "reason": "same_day_grid_sector_facts_not_found",
            "source_artifact": str(source_path),
        }, ensure_ascii=False, indent=2))
        return

    source = load_source(source_path, directory_date)
    output = {
        "date": directory_date,
        "artifact": TARGET_ARTIFACT,
        "system_id": "hot_sector_pullback_system",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "system_id": SOURCE_SYSTEM_ID,
            "artifact": SOURCE_ARTIFACT,
            "path": str(source_path),
        },
        "context": source,
    }
    if not args.dry_run:
        output_path = process_dir(directory_date) / "shared_sector_context.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output_path)
        return
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()