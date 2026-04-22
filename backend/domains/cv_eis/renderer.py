"""
C-V / EIS 도메인 출력 렌더러.
"""

from __future__ import annotations

from typing import Any, Dict, List


def render_narrative(
    validation: Dict[str, Any],
    extracted: Dict[str, Any],
    proposals: List[Dict[str, Any]],
) -> str:
    feature_text = ", ".join(extracted.get("features", [])) or "(none)"
    evidence_text = "\n".join(f"- {item}" for item in extracted.get("evidence", [])) or "- (none)"
    top_text = "No matching interpretation found."
    if proposals:
        top = proposals[0]
        top_text = f"{top.get('claim_concept')} ({top.get('score')})"

    return (
        "【CV/EIS Validation】\n"
        f"- valid: {validation.get('valid')}\n"
        f"- kind: {validation.get('measurement_kind')}\n"
        f"- rows: {validation.get('stats', {}).get('n_rows')}\n\n"
        "【Detected Features】\n"
        f"- features: {feature_text}\n"
        f"{evidence_text}\n\n"
        "【Interpretation】\n"
        f"- top proposal: {top_text}"
    )
