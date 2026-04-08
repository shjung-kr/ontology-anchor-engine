"""
I-V 도메인 특징 추출 및 상태 구성 모듈.
"""

from typing import Any, Dict, List, Optional

from backend.domains.iv.common import unique_preserve_order


def infer_iv_features_from_numeric(metrics: Dict[str, Any], regimes: List[Dict[str, Any]]) -> List[str]:
    """
    수치 metric과 regime 정보를 이용해 I-V feature를 추론한다.
    """

    features: List[str] = []
    if not regimes:
        return []

    low_regime = next((regime for regime in regimes if regime.get("name") == "low_|V|"), None)
    high_regime = next((regime for regime in regimes if regime.get("name") == "high_|V|"), None)

    slope_ref: Optional[float] = None
    if low_regime and low_regime.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(low_regime.get("mean_slope_log_absI_per_logV"))
    elif high_regime and high_regime.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(high_regime.get("mean_slope_log_absI_per_logV"))

    if slope_ref is not None:
        if 0.85 <= slope_ref <= 1.15:
            features += ["iv_features.linear_iv_regime", "iv_features.constant_conductance_behavior"]
        elif slope_ref >= 1.20:
            features.append("iv_features.nonlinear_iv_regime")

    if high_regime:
        delta_decades = float(high_regime.get("delta_decades_robust", 0.0) or 0.0)
        mean_slope = float(high_regime.get("mean_slope_log_absI_per_logV", 0.0) or 0.0)
        if delta_decades >= 2.0 and mean_slope >= 2.0:
            features.append("iv_features.field_enhanced_current")
            features.append("iv_features.nonlinear_iv_regime")

    return unique_preserve_order(features)


def build_l1_state(
    llm_keywords: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    regimes: List[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    """
    I-V 관측 결과를 L1 상태로 정규화한다.
    """

    state = {
        "iv_regimes": set(),
        "iv_features": set(),
        "evidence": [],
        "rejected_ids": [],
        "metrics": metrics or {},
        "regimes": regimes or [],
    }

    name_to_regime_id = {
        "low_|V|": "iv_regimes.low_field_regime",
        "high_|V|": "iv_regimes.high_field_regime",
    }

    for regime in regimes or []:
        regime_id = name_to_regime_id.get(regime.get("name", ""))
        if not regime_id:
            continue
        if regime_id in registry.get("iv_regimes", {}):
            state["iv_regimes"].add(regime_id)
        else:
            state["rejected_ids"].append(regime_id)

    for feature_id in infer_iv_features_from_numeric(metrics or {}, regimes or []):
        if feature_id in registry.get("iv_features", {}):
            state["iv_features"].add(feature_id)
        else:
            state["rejected_ids"].append(feature_id)

    for entry in llm_keywords or []:
        evidence = entry.get("evidence")
        if evidence:
            state["evidence"].append(evidence)

    return {
        "iv_regimes": sorted(list(state["iv_regimes"])),
        "iv_features": sorted(list(state["iv_features"])),
        "evidence": state["evidence"],
        "rejected_ids": state["rejected_ids"],
        "metrics": state["metrics"],
        "regimes": state["regimes"],
    }
