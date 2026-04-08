"""
I-V 도메인 출력 서술 렌더러.
"""

from typing import Any, Dict, List


def render_system_narrative_ko(
    measurement_validation: Dict[str, Any],
    llm_pattern: str,
    l1_state: Dict[str, Any],
    sj_proposals: List[Dict[str, Any]],
    derived: Dict[str, Any],
) -> Dict[str, str]:
    """
    프론트 표시용 한국어 서술 결과를 생성한다.
    """

    _ = measurement_validation
    regimes = l1_state.get("iv_regimes", [])
    features = l1_state.get("iv_features", [])

    l1_summary = "【L1 관측 좌표 요약】\n"
    l1_summary += f"- iv_regimes: {', '.join(regimes) if regimes else '(none)'}\n"
    l1_summary += f"- iv_features: {', '.join(features) if features else '(none)'}\n"

    if sj_proposals:
        top = sj_proposals[0]
        scientific_text = f"최상위 제안: {top.get('ontology_file')} (score={top.get('score')})"
    else:
        scientific_text = "제안 가능한 과학적 정당화가 발견되지 않았습니다."

    assumptions = derived.get("assumptions", []) or []
    assumption_ids = [item.get("assumption_id", "") for item in assumptions if isinstance(item, dict)]
    assumption_text = f"- assumptions: {', '.join(assumption_ids) if assumption_ids else '(none)'}"

    narrative = (
        f"{l1_summary}\n"
        f"【LLM 관측 패턴】\n{llm_pattern or '(none)'}\n\n"
        f"【과학적 정당화 제안】\n{scientific_text}\n\n"
        f"【가정(assumptions)】\n{assumption_text}\n"
    )

    return {
        "L1 좌표 요약": l1_summary.strip(),
        "과학적 정당화 제안": scientific_text,
        "system_narrative": narrative.strip(),
    }
