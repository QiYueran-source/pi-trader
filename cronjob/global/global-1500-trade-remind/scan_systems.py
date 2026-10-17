#!/usr/bin/env python3
"""
扫描所有交易体系。

数据来源（按优先级）：
  1. MCP 运行定义：`.pi/mcp-servers/trade-system/<system-id>/system.yml`（可执行定义的唯一来源）
  2. 知识库体系目录：`knowledge/交易/交易体系/<体系名称>/system.yml`（尚未迁入 MCP 的体系）

同一 `system-id` 同时存在时合并为一条：名称与 `system-id` 取运行定义，知识库目录只补 `logical_dir`。

用法：
  scan_systems.py                     # 扫描所有体系

输出：JSON 到 stdout；动态知识目录使用逻辑路径。
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
SYSTEMS_DIR = KNOWLEDGE_ROOT / "交易" / "交易体系"
MCP_SYSTEMS_DIR = REPO_ROOT / ".pi" / "mcp-servers" / "trade-system"


def read_identity(yml: Path) -> tuple[str, str]:
    name, system_id = "", ""
    try:
        for line in yml.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line.startswith("system-name:"):
                name = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("system-id:"):
                system_id = line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return name, system_id


def scan_systems() -> list[dict]:
    """扫描运行定义与知识库目录，按 system-id 合并。"""
    systems: dict[str, dict] = {}

    def ensure(system_id: str) -> dict:
        return systems.setdefault(system_id, {"name": "", "system_id": system_id, "logical_dir": None, "run_definition": None})

    if KNOWLEDGE_ROOT.is_dir() and SYSTEMS_DIR.is_dir():
        for d in sorted(SYSTEMS_DIR.iterdir()):
            yml = d / "system.yml"
            if not d.is_dir() or not yml.is_file():
                continue
            name, system_id = read_identity(yml)
            entry = ensure(system_id or d.name)
            entry["name"] = entry["name"] or name or d.name
            entry["logical_dir"] = str(d.relative_to(KNOWLEDGE_ROOT))

    if MCP_SYSTEMS_DIR.is_dir():
        for d in sorted(MCP_SYSTEMS_DIR.iterdir()):
            yml = d / "system.yml"
            if not d.is_dir() or not yml.is_file():
                continue
            name, system_id = read_identity(yml)
            entry = ensure(system_id or d.name)
            entry["name"] = name or entry["name"] or d.name
            entry["system_id"] = system_id or d.name
            entry["run_definition"] = str(d.relative_to(REPO_ROOT))

    return [systems[key] for key in sorted(systems, key=lambda k: systems[k]["name"])]


def main() -> None:
    print(json.dumps({"systems": scan_systems()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
