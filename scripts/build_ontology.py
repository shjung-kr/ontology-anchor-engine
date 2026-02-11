#!/usr/bin/env python3
"""
Build .jsonc (commented JSON) ontology files into pure .json.

Usage:
  python scripts/working_ontology.py

Output:
  build_ontology/ mirrors ontology/ with .json outputs
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    import json5  # pip install json5
except ImportError as e:
    raise SystemExit("Missing dependency: json5. Install with: pip install json5") from e

SRC_DIR = Path("working_ontology")
OUT_DIR = Path("d:/users/ontology-por_v14.0/backend/ontology")

def build_one(src_path: Path, out_path: Path) -> None:
    with src_path.open("r", encoding="utf-8") as f:
        obj = json5.load(f)  # parses // and /* */ comments
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

def main() -> None:
    if not SRC_DIR.exists():
        raise SystemExit(f"Source dir not found: {SRC_DIR.resolve()}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for src in SRC_DIR.rglob("*.jsonc"):
        rel = src.relative_to(SRC_DIR)
        out = OUT_DIR / rel.with_suffix(".json")
        build_one(src, out)
        count += 1
        print(f"built: {out.as_posix()}")

    print(f"done. files built: {count}")

if __name__ == "__main__":
    main()
