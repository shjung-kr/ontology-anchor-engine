"""
C-V / EIS 도메인 특징 추출.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


def _is_finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _finite_series(values: List[float]) -> List[float]:
    return [float(value) for value in values if _is_finite(float(value))]


def _range(values: List[float]) -> float:
    finite = _finite_series(values)
    if not finite:
        return 0.0
    return max(finite) - min(finite)


def _count_local_peaks(values: List[float]) -> int:
    finite = _finite_series(values)
    peaks = 0
    for index in range(1, len(finite) - 1):
        if finite[index] > finite[index - 1] and finite[index] > finite[index + 1]:
            peaks += 1
    return peaks


def _duplicate_bias_spread(bias: List[float], capacitance: List[float]) -> float:
    groups: Dict[float, List[float]] = {}
    for x_val, y_val in zip(bias, capacitance):
        if not (_is_finite(x_val) and _is_finite(y_val)):
            continue
        groups.setdefault(round(float(x_val), 9), []).append(float(y_val))

    spread = 0.0
    for values in groups.values():
        if len(values) < 2:
            continue
        spread = max(spread, max(values) - min(values))
    return spread


def extract_electrical_features(parsed: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    measurement_kind = str(parsed.get("measurement_kind") or "unknown")
    series = parsed.get("series", {}) or {}

    features: List[str] = []
    evidence: List[str] = []
    metrics: Dict[str, Any] = {
        "measurement_kind": measurement_kind,
    }

    if measurement_kind in {"cv", "cv_frequency"}:
        bias = _finite_series(series.get("bias", []))
        capacitance = _finite_series(series.get("capacitance", []))
        cap_range = _range(capacitance)
        bias_range = _range(bias)
        metrics["capacitance_range"] = cap_range
        metrics["bias_range"] = bias_range

        if bias and capacitance and len(bias) == len(capacitance) and cap_range > 0 and bias_range > 0:
            features.append("electrical_features.bias_dependent_capacitance_slope")
            evidence.append("Capacitance changes across the measured bias window.")

        hysteresis_spread = _duplicate_bias_spread(series.get("bias", []), series.get("capacitance", []))
        metrics["hysteresis_spread"] = hysteresis_spread
        if hysteresis_spread > 0.05 * max(cap_range, 1e-12):
            features.append("electrical_features.hysteresis_loop_present")
            evidence.append("Repeated bias points show separated capacitance values.")

        frequency_values = _finite_series(series.get("frequency", []))
        if frequency_values:
            features.append("electrical_features.frequency_dispersion_present")
            evidence.append("Capacitance data spans multiple probing frequencies.")

        loss_source = _finite_series(series.get("loss", []))
        if not loss_source and frequency_values and capacitance:
            loss_source = capacitance
        if _count_local_peaks(loss_source) > 0:
            features.append("electrical_features.loss_peak_present")
            evidence.append("A local peak appears in the frequency-dependent response.")

    if measurement_kind == "eis":
        z_real = _finite_series(series.get("z_real", []))
        z_imag = _finite_series(series.get("z_imag", []))
        frequency_values = _finite_series(series.get("frequency", []))
        neg_imag = [-value for value in z_imag]
        metrics["z_real_range"] = _range(z_real)
        metrics["neg_z_imag_range"] = _range(neg_imag)

        if len(neg_imag) >= 3:
            peak_count = _count_local_peaks(neg_imag)
            metrics["nyquist_peak_count"] = peak_count
            if peak_count >= 1:
                features.append("electrical_features.semicircle_present")
                evidence.append("Nyquist response contains an internal -Im(Z) peak.")

        if len(frequency_values) >= 3:
            features.append("electrical_features.frequency_dispersion_present")
            evidence.append("Impedance is measured over a frequency sweep.")

        if len(z_real) >= 4 and len(z_real) == len(z_imag):
            peak_index = max(range(len(neg_imag)), key=lambda index: neg_imag[index])
            tail_points = len(z_real) - peak_index - 1
            if 1 <= peak_index < len(z_real) - 2 and tail_points >= 2:
                dx_1 = z_real[-1] - z_real[-2]
                dy_1 = abs(z_imag[-1] - z_imag[-2])
                dx_2 = z_real[-2] - z_real[-3]
                dy_2 = abs(z_imag[-2] - z_imag[-3])
                slope_1 = abs(dy_1 / dx_1) if abs(dx_1) > 1e-12 else float("inf")
                slope_2 = abs(dy_2 / dx_2) if abs(dx_2) > 1e-12 else float("inf")
                metrics["tail_slope_abs"] = slope_1
                if (
                    0.3 <= slope_1 <= 2.5
                    and 0.3 <= slope_2 <= 2.5
                    and z_real[-1] > z_real[-2] > z_real[-3]
                ):
                    features.append("electrical_features.warburg_tail_present")
                    evidence.append("Low-frequency tail extends obliquely in the Nyquist plane.")

        if _count_local_peaks(neg_imag) > 0:
            features.append("electrical_features.loss_peak_present")
            evidence.append("The imaginary impedance magnitude shows a relaxation peak.")

    return {
        "features": features,
        "evidence": evidence,
        "metrics": metrics,
    }


def build_l1_state(
    extracted: Dict[str, Any],
    registry: Dict[str, Any],
    validation: Dict[str, Any],
) -> Dict[str, Any]:
    observed = extracted.get("features", []) or []
    accepted = [feature_id for feature_id in observed if feature_id in registry.get("electrical_features", {})]
    rejected = [feature_id for feature_id in observed if feature_id not in registry.get("electrical_features", {})]
    return {
        "electrical_features": accepted,
        "measurement_conditions": validation.get("detected_conditions", []) or [],
        "evidence": extracted.get("evidence", []) or [],
        "rejected_ids": rejected,
        "metrics": extracted.get("metrics", {}) or {},
    }
