#!/usr/bin/env python3
"""
Build .jsonc (commented JSON) ontology files into pure .json.

Usage:
  python3 scripts/build_ontology.py

Output:
  backend/ontology mirrors working_ontology with .json outputs
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    import json5  # pip install json5
except ImportError as e:
    raise SystemExit("Missing dependency: json5. Install with: pip install json5") from e

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "working_ontology"
OUT_DIR = ROOT_DIR / "backend" / "ontology"

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
