"""
추세 분석 도메인 출력 렌더러.
"""

from typing import Any, Dict, List


def render_narrative(
    validation: Dict[str, Any],
    extracted: Dict[str, Any],
    proposals: List[Dict[str, Any]],
) -> str:
    """
    프론트 출력을 위한 간단한 서술 텍스트를 생성한다.
    """

    feature_text = ", ".join(extracted.get("features", [])) or "(none)"
    evidence_text = "\n".join(f"- {item}" for item in extracted.get("evidence", [])) or "- (none)"

    if proposals:
        top = proposals[0]
        proposal_text = f"{top.get('claim_concept')} ({top.get('score')})"
    else:
        proposal_text = "No matching interpretation found."

    return (
        "【Trend Validation】\n"
        f"- valid: {validation.get('valid')}\n"
        f"- points: {validation.get('stats', {}).get('points')}\n\n"
        "【Detected Features】\n"
        f"- features: {feature_text}\n"
        f"{evidence_text}\n\n"
        "【Interpretation】\n"
        f"- top proposal: {proposal_text}"
    )
