"""
I-V 도메인 출력 서술 렌더러.
"""

from typing import Any, Dict, List, Optional

from backend.domains.iv.common import (
    format_confirmed_conditions_ko,
    join_term_labels,
    summarize_observation_pattern_ko,
    term_label,
)


def render_system_narrative_ko(
    measurement_validation: Dict[str, Any],
    llm_pattern: str,
    l1_state: Dict[str, Any],
    sj_proposals: List[Dict[str, Any]],
    derived: Dict[str, Any],
    intent_profile: Optional[Dict[str, Any]] = None,
    proposal_adjustments: Optional[List[Dict[str, Any]]] = None,
    curated_overlay: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    프론트 표시용 한국어 서술 결과를 생성한다.
    """

    _ = measurement_validation
    regimes = l1_state.get("iv_regimes", [])
    features = l1_state.get("iv_features", [])

    l1_summary = "【구간별 관찰】\n"
    l1_summary += f"- 관측된 전압 구간: {join_term_labels(regimes) if regimes else '(none)'}\n"
    l1_summary += f"- 관측된 핵심 패턴: {join_term_labels(features) if features else '(none)'}\n"

    if sj_proposals:
        top = sj_proposals[0]
        scientific_text = f"최상위 제안: {term_label(str(top.get('claim_concept') or ''))} (score={top.get('score')})"
    else:
        scientific_text = "제안 가능한 과학적 정당화가 발견되지 않았습니다."

    assumptions = derived.get("assumptions", []) or []
    assumption_ids = [item.get("assumption_id", "") for item in assumptions if isinstance(item, dict)]
    assumption_text = f"- 주요 가정: {join_term_labels(assumption_ids, max_items=4) if assumption_ids else '(none)'}"

    intent_profile = dict(intent_profile or {})
    proposal_adjustments = list(proposal_adjustments or [])
    curated_overlay = dict(curated_overlay or {})
    intent_lines: List[str] = []
    if intent_profile.get("analysis_priority"):
        intent_lines.append(f"- analysis_priority: {intent_profile.get('analysis_priority')}")
    if intent_profile.get("focus_claims"):
        intent_lines.append(f"- focus_claims: {join_term_labels(intent_profile.get('focus_claims', []))}")
    if intent_profile.get("exclude_claims"):
        intent_lines.append(f"- exclude_claims: {join_term_labels(intent_profile.get('exclude_claims', []))}")
    if intent_profile.get("confirmed_conditions"):
        intent_lines.append(f"- 확인된 조건: {format_confirmed_conditions_ko(intent_profile.get('confirmed_conditions') or {})}")

    analysis_priority = intent_profile.get("analysis_priority")
    priority_block = ""
    if analysis_priority == "mechanism_identification":
        priority_block = "사용자는 메커니즘 식별을 우선하고 있으므로, 현재는 최상위 해석과 그 근거 feature를 중심으로 읽는 것이 적절합니다."
    elif analysis_priority == "measurement_anomaly_diagnosis":
        warnings = measurement_validation.get("warnings", []) or []
        errors = measurement_validation.get("errors", []) or []
        priority_block = (
            "사용자는 측정 이상 진단을 우선하고 있으므로, 메커니즘 단정 전에 validation 경고와 조건 누락을 먼저 점검해야 합니다. "
            f"현재 error={len(errors)}, warning={len(warnings)} 입니다."
        )
    elif analysis_priority == "next_experiment_planning":
        required = top.get("required_features", []) if sj_proposals else []
        priority_block = (
            "사용자는 다음 실험 설계를 우선하고 있으므로, 현재 상위 가설을 구분할 수 있는 추가 feature 확보와 조건 통제를 중심으로 해석해야 합니다. "
            f"상위 가설의 구분 feature는 {join_term_labels(required) if required else '(none)'} 입니다."
        )

    adjustment_lines: List[str] = []
    for item in proposal_adjustments[:3]:
        claim = term_label(str(item.get("claim_concept") or ""))
        parts = []
        for adjustment in item.get("adjustments", []):
            delta = adjustment.get("delta", 0)
            reason = adjustment.get("reason", "")
            parts.append(f"{delta:+g} {reason}")
        if parts:
            adjustment_lines.append(f"- {claim}: {'; '.join(parts)}")

    overlay_lines: List[str] = []
    claim_overlay_count = len(curated_overlay.get("claims", []) or [])
    assumption_overlay_count = len(curated_overlay.get("assumptions", []) or [])
    if claim_overlay_count or assumption_overlay_count:
        overlay_lines.append(f"- curated_claims: {claim_overlay_count}")
        overlay_lines.append(f"- curated_assumptions: {assumption_overlay_count}")

    narrative = (
        f"{l1_summary}\n"
        f"- 관측 패턴 요약: {summarize_observation_pattern_ko(llm_pattern) or '(none)'}\n\n"
        f"【메커니즘 제안】\n{scientific_text}\n\n"
        f"【가정】\n{assumption_text}\n"
    )

    if priority_block:
        narrative += f"\n【분석 우선순위 해석】\n{priority_block}\n"

    if intent_lines:
        narrative += "\n【사용자 의도 반영】\n" + "\n".join(intent_lines) + "\n"
    if adjustment_lines:
        narrative += "\n【재정렬 근거】\n" + "\n".join(adjustment_lines) + "\n"
    if overlay_lines:
        narrative += "\n【승인된 Overlay 반영】\n" + "\n".join(overlay_lines) + "\n"

    return {
        "L1 좌표 요약": l1_summary.strip(),
        "과학적 정당화 제안": scientific_text,
        "system_narrative": narrative.strip(),
    }
