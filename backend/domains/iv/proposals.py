"""
I-V 도메인 scientific justification 평가 모듈.
"""

import json
from typing import Any, Dict, List, Optional

from backend.domains.iv.common import get_ontology_root, unique_preserve_order
from backend.domains.iv.registry import normalize_assumption_card


def evaluate_scientific_justification(l1_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    L1 상태와 ontology를 비교해 scientific justification 후보를 계산한다.
    """

    proposals: List[Dict[str, Any]] = []
    ontology_dir = get_ontology_root() / "04_scientific_justification"
    if not ontology_dir.is_dir():
        return proposals

    for path in sorted(ontology_dir.glob("*.json")):
        try:
            scientific_justification = json.loads(path.read_text(encoding="utf-8")).get("scientific_justification", {})
        except Exception:
            continue

        claim = scientific_justification.get("claim_concept")
        required_features = set(scientific_justification.get("required_features", []))
        matched = required_features.intersection(set(l1_state.get("iv_features", [])))
        score = len(matched)

        if score <= 0:
            continue

        proposals.append(
            {
                "ontology_file": path.name,
                "claim_concept": claim,
                "mechanism_id": claim,
                "score": score,
                "measurement_conditions": scientific_justification.get("measurement_conditions", []) or [],
                "required_features": sorted(list(required_features)),
                "observed_features": scientific_justification.get("observed_features", []) or [],
                "matched_features": sorted(list(matched)),
                "explanation_notes": scientific_justification.get("explanation_notes", {}),
                "sj_assumptions": scientific_justification.get("assumptions", []) or [],
                "mechanism_by_regime": scientific_justification.get("mechanism_by_regime", []) or [],
            }
        )

    proposals.sort(key=lambda item: item["score"], reverse=True)
    return proposals


def build_derived_assumptions(
    measurement_validation: Dict[str, Any],
    sj_top: Optional[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    """
    validation과 SJ 후보의 assumption을 병합한다.
    """

    validation_assumptions = measurement_validation.get("emitted_assumptions", []) or []
    sj_assumptions = (sj_top or {}).get("sj_assumptions", []) or []
    merged = unique_preserve_order(list(validation_assumptions) + list(sj_assumptions))
    cards = [normalize_assumption_card(assumption_id, registry) for assumption_id in merged]

    return {
        "assumptions": cards,
        "assumption_ids": merged,
        "assumptions_meta": {
            "from_validation": list(validation_assumptions),
            "from_sj": list(sj_assumptions),
        },
    }
