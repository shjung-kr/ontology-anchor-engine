# l1_sj_engine.py
import os
import json
from typing import Dict, List

from openai import OpenAI

from llm_adapter import llm_analyze_numeric

# 한글로그 출력을 위한 임포트
from ko_renderer import (
    render_l1_keywords_ko, 
    render_sj_proposal_ko
)


ONTOLOGY_DIR = "./ontology/scientific_justification"

# =========================================================
# L1 강화: LLM keyword + evidence → 강화된 L1 keyword
# =========================================================
def strengthen_l1(llm_keywords: List[Dict]) -> List[Dict]:
    l1_keywords = []

    for entry in llm_keywords:
        kw = entry["keyword"].lower()
        ev = entry["evidence"].lower()

        # ----------------------------
        # 1. category 정규화
        # ----------------------------
        if "temperature" in kw:
            category = "temperature_dependence"
        elif "voltage" in kw:
            category = "voltage_dependence"
        else:
            category = "generic_dependence"

        # ----------------------------
        # 2. strength 추론 (evidence 기반)
        # ----------------------------
        strength = "moderate"

        if any(token in ev for token in [
            "orders of magnitude",
            "order-of-magnitude",
            "exponential",
            "rapid increase",
            "significant increase"
        ]):
            strength = "strong"

        elif any(token in ev for token in [
            "slight increase",
            "minor change",
            "weak dependence"
        ]):
            strength = "weak"

        # 수치 표현 힌트 (계산 ❌, 표현만 사용)
        elif "e-" in ev and "to" in ev:
            strength = "strong"

        # ----------------------------
        # 3. L1 keyword 생성
        # ----------------------------
        l1_keywords.append({
            "l1_keyword": f"{strength}_{category}",
            "source_llm_keyword": entry["keyword"],
            "strength": strength,
            "category": category,
            "evidence": entry["evidence"]
        })

    return l1_keywords


# =========================================================
# SJ Ontology selection (L1 keyword 기준)
# =========================================================
def select_ontology(l1_keywords: List[Dict]):
    logs = []
    detected = [k["l1_keyword"].lower() for k in l1_keywords]

    for fname in os.listdir(ONTOLOGY_DIR):
        if not fname.endswith(".json"):
            continue

        path = os.path.join(ONTOLOGY_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            ontology = json.load(f)

        ontology_keywords = [
            k.lower() for k in ontology.get("keywords", [])
        ]

        matched = [
            kw for kw in detected if kw in ontology_keywords
        ]

        logs.append({
            "ontology_id": ontology.get("ontology_id"),
            "file": fname,
            "matched_keywords": matched,
            "score": len(matched)
        })

    logs.sort(key=lambda x: x["score"], reverse=True)
    selected = logs[0] if logs and logs[0]["score"] > 0 else None
    return selected, logs


# =========================================================
# L1 SJ Engine (ENTRY POINT)
# =========================================================
def run_l1_engine(raw_data: str) -> Dict:
    # 1. LLM 관찰
    llm_result = llm_analyze_numeric(raw_data)

    # 2. L1 강화 (⭐ 핵심 변경)
    l1_keywords = strengthen_l1(llm_result["keywords"])

    # 3. SJ ontology 선택 시도
    selected, selection_log = select_ontology(l1_keywords)

    return {
        # -------- LLM 단계 --------
        "llm_pattern": llm_result["pattern"],
        "llm_keywords": llm_result["keywords"],

        # -------- L1 강화 --------
        "l1_keywords": l1_keywords,

        # -------- Ontology --------
        "ontology_selection_log": selection_log,
        "selected_ontology": selected,

        # -------- 한글로그 출력 --------
        "L1 강화 키워드 요약": render_l1_keywords_ko(l1_keywords),
        "과학적 정당화 제안": render_sj_proposal_ko(selected)
        
        
    }

# ===============================
# VIEW-ONLY FUNCTIONS (LOG OUTPUT)
# ===============================

def translate_evidence_for_log(l1_keyword: Dict) -> List[str]:
    """
    ⚠️ VIEW ONLY FUNCTION ⚠️
    - This function is NOT part of reasoning
    - NOT used for ontology selection
    - NOT used for L1 strengthening
    - ONLY for UI log readability
    """
    evidence = l1_keyword.get("evidence")
    
    if not isinstance(evidence, str) or not evidence.strip():
        return []

    prompt = (
        "Translate the following scientific observation sentences into Korean.\n"
        "Do NOT interpret. Do NOT explain. Only translate.\n\n"
        f"-{evidence}\n"
    )

    client=OpenAI()
    
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        
    )
    
    return [
        line.strip("- ").strip()
        for line in response.choices[0].message.content.split("\n")
        if line.strip()
    ]
    raw = response.choices[0].message.content
    print("RAW LLM RESPONSE >>>")
    print(raw)
    print("<<< END")
