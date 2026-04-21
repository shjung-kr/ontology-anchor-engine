from __future__ import annotations

from backend.domains.iv.proposals import build_derived_assumptions, evaluate_scientific_justification
from backend.domains.iv.registry import load_registry_from_folders


def test_evaluate_scientific_justification_matches_fn_candidate():
    proposals = evaluate_scientific_justification(
        {"iv_features": ["iv_features.nonlinear_iv_regime", "iv_features.field_enhanced_current"]}
    )
    assert proposals
    assert proposals[0]["claim_concept"] == "iv_interpretation.fn_tunneling_asserted"


def test_build_derived_assumptions_merges_validation_and_sj():
    registry = load_registry_from_folders()
    derived = build_derived_assumptions(
        measurement_validation={"emitted_assumptions": ["physical_assumption.room_temperature_operation"]},
        sj_top={"sj_assumptions": ["physical_assumption.room_temperature_operation"]},
        registry=registry,
    )
    assert derived["assumption_ids"] == ["physical_assumption.room_temperature_operation"]
    assert derived["assumptions"][0]["assumption_id"] == "physical_assumption.room_temperature_operation"
