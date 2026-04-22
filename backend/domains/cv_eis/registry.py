"""
C-V / EIS 도메인 ontology 로더.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.domains.cv_eis.common import get_ontology_root, load_json_files


def load_registry() -> Dict[str, Any]:
    ontology_root = get_ontology_root()
    features: Dict[str, bool] = {}
    assumptions: Dict[str, Dict[str, Any]] = {}

    for _, payload in load_json_files(ontology_root / "02_electrical_features"):
        feature_id = payload.get("id") or payload.get("feature_id")
        if isinstance(feature_id, str) and feature_id.strip():
            features[feature_id.strip()] = True

    for _, payload in load_json_files(ontology_root / "00_lexicon"):
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.strip():
                assumptions[item_id.strip()] = item

    return {
        "electrical_features": features,
        "assumptions": assumptions,
    }


def list_interpretations() -> List[Dict[str, Any]]:
    ontology_root = get_ontology_root()
    interpretations: List[Dict[str, Any]] = []

    for path, payload in load_json_files(ontology_root / "04_interpretations"):
        interpretation = payload.get("scientific_justification")
        if isinstance(interpretation, dict):
            item = dict(interpretation)
            item["_filename"] = path.name
            interpretations.append(item)

    return interpretations


def normalize_assumption_card(assumption_id: str, registry: Dict[str, Any]) -> Dict[str, Any]:
    card = registry.get("assumptions", {}).get(assumption_id, {})
    if isinstance(card, dict) and card:
        return {
            "assumption_id": assumption_id,
            "statement": (
                card.get("definition", {}).get("ko")
                or card.get("definition", {}).get("en")
                or card.get("labels", {}).get("ko")
                or card.get("labels", {}).get("en")
                or assumption_id
            ),
            "labels": card.get("labels", {}),
            "category": card.get("category"),
        }
    return {"assumption_id": assumption_id, "statement": assumption_id, "impact_axis": []}
