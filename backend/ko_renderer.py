# ko_renderer.py
from label_ko import L1_KEYWORD_KO, SJ_ONTOLOGY_KO
from typing import Dict, List


def render_l1_keywords_ko(l1_keywords):
    rendered = []

    for k in l1_keywords:
        key = k["l1_keyword"]

        rendered.append({
            "L1 키워드": L1_KEYWORD_KO.get(key, key),
            "강도": k["strength"],
            "분류": k["category"],
            "근거(LLM 관찰)": k["evidence"]
        })

    return rendered


def render_sj_proposal_ko(sj_results: List[Dict]) -> str:
    """
    V14 renderer: score-based SJ proposal list (Korean)
    """

    if not sj_results:
        return "제안 가능한 과학적 정당화가 발견되지 않았습니다."

    lines = []
    lines.append("【과학적 정당화 제안 결과】")

    for idx, r in enumerate(sj_results, start=1):
        mech = r.get("mechanism_id", "unknown")
        score = r.get("score", 0)
        note = r.get("interpretation", "")

        lines.append(f"\n[{idx}] 제안 메커니즘: {mech}")
        lines.append(f"    · 적합도 점수: {score}")
        if note:
            lines.append(f"    · 해석: {note}")

    lines.append(
        "\n※ 본 결과는 관측된 I–V 거동 좌표에 기반한 "
        "조건부 과학적 정당화 제안이며, "
        "어떠한 메커니즘도 단정하지 않습니다."
    )

    return "\n".join(lines)



def render_l1_state_ko(l1_state: Dict) -> str:
    """
    V14 renderer: L1 좌표(state) 한글 요약
    """
    lines = []

    regime_map = {
        "low_field": "저전압 구간",
        "intermediate_field": "중간 전압 구간",
        "high_field": "고전압 구간"
    }

    slope_map = {
        "gradual": "완만한 증가",
        "abrupt": "급격한 증가"
    }

    magnitude_map = {
        "near_noise": "노이즈 수준 전류",
        "finite": "유의미한 전류",
        "large": "큰 전류"
    }

    lines.append("【L1 관측 좌표 요약】")

    if l1_state.get("regime"):
        lines.append(
            "- 전압 구간: " +
            ", ".join(regime_map[r] for r in l1_state["regime"])
        )

    if l1_state.get("slope"):
        lines.append(
            "- 전류 변화 형태: " +
            ", ".join(slope_map[s] for s in l1_state["slope"])
        )

    if l1_state.get("magnitude"):
        lines.append(
            "- 전류 크기 수준: " +
            ", ".join(magnitude_map[m] for m in l1_state["magnitude"])
        )

    lines.append(f"- 구조적 특성: {'다중 구간' if l1_state.get('structure') == 'multi_regime' else '단일 구간'}")

    return "\n".join(lines)

    
