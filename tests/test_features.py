from __future__ import annotations

from backend.domains.iv.features import build_l1_state, infer_iv_features_from_numeric
from backend.domains.cv_eis.features import extract_electrical_features
from backend.domains.cv_eis.parser import parse_measurement_table


def test_infer_iv_features_for_linear_regime():
    regimes = [{"name": "low_|V|", "mean_slope_log_absI_per_logV": 1.0}]
    features = infer_iv_features_from_numeric(metrics={}, regimes=regimes)
    assert "iv_features.linear_iv_regime" in features
    assert "iv_features.constant_conductance_behavior" in features


def test_build_l1_state_filters_unknown_registry_items():
    state = build_l1_state(
        llm_keywords=[{"evidence": "strong rise"}],
        metrics={"absI_decades_span": 3.2},
        regimes=[{"name": "high_|V|", "mean_slope_log_absI_per_logV": 2.5, "delta_decades_robust": 3.0}],
        registry={
            "iv_regimes": {"iv_regimes.high_field_regime": True},
            "iv_features": {
                "iv_features.nonlinear_iv_regime": True,
                "iv_features.field_enhanced_current": True,
            },
        },
    )
    assert state["iv_regimes"] == ["iv_regimes.high_field_regime"]
    assert "iv_features.field_enhanced_current" in state["iv_features"]
    assert state["evidence"] == ["strong rise"]


def test_extract_cv_eis_features_for_cv_slope_and_hysteresis():
    parsed = parse_measurement_table(
        "bias,capacitance\n-1,12\n0,10\n1,8\n-1,11\n0,9\n1,7\n"
    )
    extracted = extract_electrical_features(parsed)
    assert "electrical_features.bias_dependent_capacitance_slope" in extracted["features"]
    assert "electrical_features.hysteresis_loop_present" in extracted["features"]


def test_extract_cv_eis_features_for_eis_semicircle():
    parsed = parse_measurement_table(
        "frequency,z_real,z_imag\n1000,1,-1\n100,2,-3\n10,4,-1\n"
    )
    extracted = extract_electrical_features(parsed)
    assert "electrical_features.semicircle_present" in extracted["features"]
    assert "electrical_features.frequency_dispersion_present" in extracted["features"]
