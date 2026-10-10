#!/opt/hermes/.venv/bin/python3
"""
读写当天摘要简报工具。

用法：
  brief_reader.py                     # 读取当天所有简报内容
  brief_reader.py --date 2026-06-15   # 读取指定日期
  brief_reader.py --clean             # 清理当天所有简报
  brief_reader.py --date 2026-06-15 --clean  # 清理指定日期

读取模式输出格式：
  === 2026-06-12_简报A.txt ===
  内容...

清理模式无输出，exit 0。
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ABSTRACT_DIR = Path("/hermes-trader/knowledge/摘要/.abstract")


def main():
    parser = argparse.ArgumentParser(description="读写当天摘要简报")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--clean", action="store_true",
                        help="清理指定日期的简报文件")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        d = date.today()

    prefix = d.strftime("%Y-%m-%d")
    files = sorted(ABSTRACT_DIR.glob(f"{prefix}_*.txt"))

    if not files:
        return  # 无声退出

    if args.clean:
        for f in files:
            f.unlink()
        return

    # 读取模式
    for f in files:
        print(f"=== {f.name} ===")
        print(f.read_text(encoding="utf-8").rstrip())
        print()


if __name__ == "__main__":
    main()
