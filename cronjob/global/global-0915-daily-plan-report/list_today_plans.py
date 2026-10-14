#!/usr/bin/env python3
"""
扫描指定日期下的交易计划文件。

用法：
  list_today_plans.py                           # 扫今天
  list_today_plans.py --date 2026-06-15         # 扫指定日期

输出：每行一个计划文件的逻辑路径，不带 knowledge/ 或 archive/ 前缀。
"""

import argparse
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
TRADE_PLAN_DIR = KNOWLEDGE_ROOT / "交易" / "交易计划"


def main():
    parser = argparse.ArgumentParser(description="扫描当日交易计划文件")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        d = date.today()

    plan_dir = TRADE_PLAN_DIR / d.strftime("%Y-%m-%d")
    if not plan_dir.exists():
        return

    for f in sorted(plan_dir.glob("*.md")):
        print(f.relative_to(KNOWLEDGE_ROOT))


if __name__ == "__main__":
    main()
