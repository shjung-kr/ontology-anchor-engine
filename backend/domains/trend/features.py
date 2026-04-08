"""
추세 분석 도메인 특징 추출 모듈.
"""

from typing import Any, Dict, List


def validate_input(x_values: List[float], y_values: List[float]) -> Dict[str, Any]:
    """
    추세 분석에 필요한 최소 입력 조건을 검사한다.
    """

    errors: List[str] = []
    warnings: List[str] = []

    if len(x_values) != len(y_values):
        errors.append("X and Y lengths do not match.")
    if len(x_values) < 3:
        errors.append("At least 3 numeric pairs are required.")
    if len(set(x_values)) < 2:
        warnings.append("X values have very low variation.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "points": len(x_values),
            "x_min": min(x_values) if x_values else None,
            "x_max": max(x_values) if x_values else None,
            "y_min": min(y_values) if y_values else None,
            "y_max": max(y_values) if y_values else None,
        },
    }


def extract_signal_features(x_values: List[float], y_values: List[float]) -> Dict[str, Any]:
    """
    단순 수치 규칙으로 추세 특징을 추출한다.
    """

    deltas = [y_values[index + 1] - y_values[index] for index in range(len(y_values) - 1)]
    positive_steps = sum(1 for delta in deltas if delta > 0)
    negative_steps = sum(1 for delta in deltas if delta < 0)
    zero_steps = sum(1 for delta in deltas if delta == 0)

    features: List[str] = []
    evidence: List[str] = []

    if positive_steps == len(deltas):
        features.append("signal_features.monotonic_increase")
        evidence.append("All successive Y deltas are positive.")
    elif negative_steps == len(deltas):
        features.append("signal_features.monotonic_decrease")
        evidence.append("All successive Y deltas are negative.")
    elif zero_steps == len(deltas):
        features.append("signal_features.flat_signal")
        evidence.append("All successive Y deltas are zero.")
    else:
        features.append("signal_features.non_monotonic_variation")
        evidence.append("Successive Y deltas change sign or mix positive and negative values.")

    if y_values and abs(y_values[-1] - y_values[0]) > 0:
        if y_values[-1] > y_values[0]:
            features.append("signal_features.net_positive_shift")
            evidence.append("Final Y is larger than initial Y.")
        elif y_values[-1] < y_values[0]:
            features.append("signal_features.net_negative_shift")
            evidence.append("Final Y is smaller than initial Y.")

    return {
        "features": features,
        "evidence": evidence,
        "metrics": {
            "positive_steps": positive_steps,
            "negative_steps": negative_steps,
            "zero_steps": zero_steps,
            "net_delta": y_values[-1] - y_values[0] if y_values else None,
        },
    }
