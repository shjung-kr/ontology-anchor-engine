"""
C-V / EIS 도메인 입력 검증.
"""

from __future__ import annotations

from typing import Any, Dict, List


def validate_measurement(parsed: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    measurement_kind = str(parsed.get("measurement_kind") or "unknown")
    series = parsed.get("series", {}) or {}
    stats = parsed.get("stats", {}) or {}

    errors: List[str] = []
    warnings: List[str] = []
    emitted_assumptions: List[str] = []
    detected_conditions: List[str] = []

    if measurement_kind == "unknown":
        errors.append("Could not classify the table as C-V or EIS.")

    if int(stats.get("n_rows", 0)) < 3:
        errors.append("At least 3 numeric rows are required.")

    if measurement_kind in {"cv", "cv_frequency"}:
        detected_conditions.append("measurement_conditions.capacitance_voltage_sweep")
        if "capacitance" not in series:
            errors.append("Capacitance column is required for C-V analysis.")
        if measurement_kind == "cv" and "bias" not in series:
            errors.append("Bias column is required for bias-dependent C-V analysis.")

    if measurement_kind == "eis":
        detected_conditions.append("measurement_conditions.impedance_spectroscopy_frequency_sweep")
        for required in ("frequency", "z_real", "z_imag"):
            if required not in series:
                errors.append(f"{required} column is required for EIS analysis.")

    ac_amplitude = metadata.get("ac_amplitude")
    if ac_amplitude is not None:
        detected_conditions.append("measurement_conditions.small_signal_ac_linearization")
        emitted_assumptions.append("measurement_assumption.small_signal_linearity_holds")
    else:
        warnings.append("AC amplitude metadata is missing; small-signal validity is assumed only implicitly.")

    if metadata.get("dc_bias") is not None:
        detected_conditions.append("measurement_conditions.bias_dependent_impedance")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "measurement_kind": measurement_kind,
        "detected_conditions": detected_conditions,
        "emitted_assumptions": emitted_assumptions,
    }
