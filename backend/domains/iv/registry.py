"""
I-V 도메인 ontology 레지스트리 로더.
"""

from pathlib import Path
from typing import Any, Dict

from backend.domains.iv.common import (
    coerce_assumption_definition,
    get_ontology_root,
    load_json_files,
)


def load_registry_from_folders() -> Dict[str, Any]:
    """
    I-V 도메인 ontology 파일에서 레지스트리를 구성한다.
    """

    ontology_root = get_ontology_root()
    reg: Dict[str, Any] = {"iv_regimes": {}, "iv_features": {}, "assumptions": {}}

    def ingest_dir(dir_path: Path, key: str) -> None:
        if not dir_path.is_dir():
            return
        for _, obj in load_json_files(dir_path):
            ontology_id = obj.get("id") or obj.get("ontology_id")
            if isinstance(ontology_id, str) and ontology_id.strip():
                reg[key][ontology_id.strip()] = True

    def ingest_assumptions_dir(dir_path: Path) -> None:
        if not dir_path.is_dir():
            return

        def register_one(item: Dict[str, Any], source_file: str) -> None:
            if not isinstance(item, dict):
                return

            assumption_id = item.get("assumption_id")
            if not (isinstance(assumption_id, str) and assumption_id.strip()):
                object_id = item.get("id") or item.get("ontology_id")
                if isinstance(object_id, str) and object_id.strip():
                    assumption_id = object_id.split(".", 1)[1] if object_id.lower().startswith("assumption.") else object_id

            if not (isinstance(assumption_id, str) and assumption_id.strip()):
                return

            card = coerce_assumption_definition(assumption_id.strip(), item, source_file)
            if card:
                reg["assumptions"][assumption_id.strip()] = card

        for path, obj in load_json_files(dir_path):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        card = coerce_assumption_definition(key, value, str(path))
                        if card:
                            reg["assumptions"][key] = card

            looks_like_single = False
            if isinstance(obj, dict):
                if isinstance(obj.get("assumption_id"), str) and obj["assumption_id"].strip():
                    looks_like_single = True
                else:
                    object_id = obj.get("id") or obj.get("ontology_id")
                    if isinstance(object_id, str) and object_id.strip():
                        looks_like_single = True

            if looks_like_single:
                register_one(obj, str(path))

            if isinstance(obj, dict) and isinstance(obj.get("assumptions"), list):
                for item in obj["assumptions"]:
                    register_one(item, str(path))

            if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                for item in obj["items"]:
                    register_one(item, str(path))

    ingest_dir(ontology_root / "01_iv_regimes", "iv_regimes")
    ingest_dir(ontology_root / "02_iv_features", "iv_features")

    for relative_dir in ("00_lexicon", "03_assumptions", "02_measurement_validations"):
        ingest_assumptions_dir(ontology_root / relative_dir)

    return reg


def normalize_assumption_card(assumption_id: str, registry: Dict[str, Any]) -> Dict[str, Any]:
    """
    레지스트리 기준으로 assumption 카드 정보를 반환한다.
    """

    ref = registry.get("assumptions", {}).get(assumption_id)
    if isinstance(ref, dict):
        card: Dict[str, Any] = {
            "assumption_id": assumption_id,
            "statement": ref.get("statement", assumption_id),
            "impact_axis": ref.get("impact_axis", []),
        }
        if isinstance(ref.get("labels"), dict):
            card["labels"] = ref["labels"]
        for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
            if extra_key in ref:
                card[extra_key] = ref[extra_key]
        return card

    return {"assumption_id": assumption_id, "statement": assumption_id, "impact_axis": []}
