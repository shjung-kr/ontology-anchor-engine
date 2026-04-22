"""
C-V / EIS 도메인 공통 유틸리티.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.user_storage import get_user_runs_dir

BASE_DIR = Path(__file__).resolve().parents[2]
ONTOLOGY_ROOT = BASE_DIR / "ontology" / "cv_eis"


def get_runs_dir() -> Path:
    return get_user_runs_dir()


def get_ontology_root() -> Path:
    return ONTOLOGY_ROOT


def load_json_files(dir_path: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    loaded: List[Tuple[Path, Dict[str, Any]]] = []
    if not dir_path.is_dir():
        return loaded

    for path in sorted(dir_path.glob("*.json")):
        try:
            loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return loaded


def unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
