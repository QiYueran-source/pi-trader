#!/opt/hermes/.venv/bin/python3
"""
扫描所有交易体系。

用法：
  scan_systems.py                     # 扫描所有体系

输出：JSON 到 stdout
"""

import argparse
import json
import sys
from pathlib import Path

SYSTEMS_DIR = Path("/hermes-trader/knowledge/交易/交易体系")


def scan_systems():
    """扫描所有交易体系，返回列表"""
    systems = []
    if not SYSTEMS_DIR.exists():
        return systems

    for d in sorted(SYSTEMS_DIR.iterdir()):
        if not d.is_dir():
            continue
        yml = d / "system.yml"
        if not yml.exists():
            continue

        name = d.name
        system_id = ""
        try:
            content = yml.read_text(encoding="utf-8")
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("system-name:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("system-id:"):
                    system_id = line.split(":", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

        systems.append({
            "name": name,
            "system_id": system_id,
            "dir": str(d),
        })

    return systems


def main():
    systems = scan_systems()
    output = {
        "systems": systems,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
