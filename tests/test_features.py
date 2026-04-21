from __future__ import annotations

from backend.domains.iv.features import build_l1_state, infer_iv_features_from_numeric


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
