"""
I-V 도메인 공통 상수와 파일 로딩 유틸리티.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[2]
DOMAIN_DIR = Path(__file__).resolve().parent
ONTOLOGY_ROOT = BASE_DIR / "ontology" / "iv"
LEGACY_ONTOLOGY_ROOT = BASE_DIR / "ontology"
PROMPTS_DIR = BASE_DIR.parent / "prompts"
RUNS_DIR = BASE_DIR / "runs"


def get_ontology_root() -> Path:
    """
    I-V 도메인 ontology 루트를 반환한다.
    """

    if ONTOLOGY_ROOT.is_dir():
        return ONTOLOGY_ROOT
    return LEGACY_ONTOLOGY_ROOT


def unique_preserve_order(items: List[str]) -> List[str]:
    """
    입력 순서를 유지하며 중복을 제거한다.
    """

    seen = set()
    output: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def load_json_files(dir_path: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """
    디렉터리 아래 JSON 파일을 읽어 반환한다.
    """

    loaded: List[Tuple[Path, Dict[str, Any]]] = []
    if not dir_path.is_dir():
        return loaded

    for path in sorted(dir_path.glob("*.json")):
        try:
            loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return loaded


def extract_statement_from_definition(obj: Dict[str, Any]) -> Optional[str]:
    """
    assumption 정의 객체에서 대표 설명 문장을 뽑는다.
    """

    statement = obj.get("statement")
    if isinstance(statement, str) and statement.strip():
        return statement.strip()

    definition = obj.get("definition")
    if isinstance(definition, dict):
        for lang in ("ko", "en"):
            value = definition.get(lang)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(definition, str) and definition.strip():
        return definition.strip()

    labels = obj.get("labels")
    if isinstance(labels, dict):
        for lang in ("ko", "en"):
            value = labels.get(lang)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("description", "label", "summary"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def coerce_assumption_definition(
    assumption_id: str,
    obj: Dict[str, Any],
    source_file: str,
) -> Optional[Dict[str, Any]]:
    """
    다양한 assumption 표현을 표준 카드 형태로 정규화한다.
    """

    if not isinstance(assumption_id, str) or not assumption_id.strip() or not isinstance(obj, dict):
        return None

    statement = extract_statement_from_definition(obj)
    if not statement:
        return None

    impact_axis = obj.get("impact_axis")
    if not isinstance(impact_axis, list):
        impact_axis = []

    card: Dict[str, Any] = {
        "assumption_id": assumption_id.strip(),
        "statement": statement,
        "impact_axis": impact_axis,
        "_source_file": source_file,
    }

    labels = obj.get("labels")
    if isinstance(labels, dict):
        card["labels"] = labels

    for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
        if extra_key in obj:
            card[extra_key] = obj[extra_key]

    return card
