# ko_renderer.py
from label_ko import L1_KEYWORD_KO, SJ_ONTOLOGY_KO


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


def render_sj_proposal_ko(selected_ontology):
    if not selected_ontology:
        return {
            "과학적 정당화 제안": "해당 조건에서 명확한 과학적 정당화를 제안할 수 없습니다."
        }

    oid = selected_ontology["ontology_id"]
    info = SJ_ONTOLOGY_KO.get(oid)

    if not info:
        return {
            "과학적 정당화 ID": oid,
            "설명": "한글 설명이 등록되지 않은 정당화입니다."
        }

    return {
        "과학적 정당화 ID": oid,
        "정당화 명칭": info["label"],
        "설명": info["description"]
    }
