"""
C-V / EIS 도메인 interpretation 제안.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.domains.cv_eis.common import unique_preserve_order
from backend.domains.cv_eis.registry import list_interpretations, normalize_assumption_card


def evaluate_interpretations(l1_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    observed_features = set(l1_state.get("electrical_features", []) or [])
    observed_conditions = set(l1_state.get("measurement_conditions", []) or [])
    proposals: List[Dict[str, Any]] = []

    for interpretation in list_interpretations():
        required = set(interpretation.get("required_features", []) or [])
        interpretation_conditions = set(interpretation.get("measurement_conditions", []) or [])
        if interpretation_conditions and observed_conditions and not interpretation_conditions.intersection(observed_conditions):
            continue
        matched = sorted(list(required.intersection(observed_features)))
        score = len(matched)
        if score <= 0:
            continue
        proposals.append(
            {
                "ontology_file": interpretation.get("_filename"),
                "claim_concept": interpretation.get("claim_concept"),
                "score": score,
                "matched_features": matched,
                "required_features": sorted(list(required)),
                "observed_features": interpretation.get("observed_features", []) or [],
                "measurement_conditions": interpretation.get("measurement_conditions", []) or [],
                "sj_assumptions": interpretation.get("assumptions", []) or [],
                "mechanism_by_regime": interpretation.get("mechanism_by_regime", []) or [],
                "explanation_notes": interpretation.get("explanation_notes", {}) or {},
            }
        )

    proposals.sort(key=lambda item: item["score"], reverse=True)
    return proposals


def build_derived_assumptions(
    measurement_validation: Dict[str, Any],
    sj_top: Optional[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    validation_assumptions = measurement_validation.get("emitted_assumptions", []) or []
    sj_assumptions = (sj_top or {}).get("sj_assumptions", []) or []
    merged = unique_preserve_order(list(validation_assumptions) + list(sj_assumptions))
    cards = [normalize_assumption_card(item, registry) for item in merged]
    return {
        "assumptions": cards,
        "assumption_ids": merged,
        "assumptions_meta": {
            "from_validation": list(validation_assumptions),
            "from_sj": list(sj_assumptions),
        },
    }
