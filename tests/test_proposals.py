from __future__ import annotations

from backend.domains.iv.proposals import build_derived_assumptions, evaluate_scientific_justification
from backend.domains.iv.registry import load_registry_from_folders
from backend.domains.cv_eis.proposals import build_derived_assumptions as build_cv_eis_derived_assumptions
from backend.domains.cv_eis.proposals import evaluate_interpretations
from backend.domains.cv_eis.registry import load_registry as load_cv_eis_registry


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


def test_evaluate_cv_eis_interpretations_matches_single_rc():
    proposals = evaluate_interpretations(
        {"electrical_features": ["electrical_features.semicircle_present", "electrical_features.frequency_dispersion_present"]}
    )
    assert proposals
    assert "eis_interpretation.single_rc_relaxation" in [item["claim_concept"] for item in proposals]


def test_build_cv_eis_derived_assumptions_merges_validation_and_sj():
    registry = load_cv_eis_registry()
    derived = build_cv_eis_derived_assumptions(
        measurement_validation={"emitted_assumptions": ["measurement_assumption.small_signal_linearity_holds"]},
        sj_top={"sj_assumptions": ["measurement_assumption.small_signal_linearity_holds"]},
        registry=registry,
    )
    assert derived["assumption_ids"] == ["measurement_assumption.small_signal_linearity_holds"]
    assert derived["assumptions"][0]["assumption_id"] == "measurement_assumption.small_signal_linearity_holds"
