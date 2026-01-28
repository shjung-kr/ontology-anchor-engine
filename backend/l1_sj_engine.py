# l1_sj_engine.py
import os
import json
from typing import Dict, List

from llm_adapter import llm_analyze_numeric
from ko_renderer import (
    render_l1_state_ko,
    render_sj_proposal_ko
    , render_assumptions_ko
    )

ONTOLOGY_DIR = "./ontology/04_scientific_justification"
MEASUREMENT_RULE_DIR = "./ontology/02_measurement_validation"

# =========================================================
# 1. Measurement validation (gate)
# =========================================================
def validate_measurement(raw_data: str) -> Dict:
    """
    Check whether measurement is above noise / usable for SJ
    """
    rules = []

    for fname in os.listdir(MEASUREMENT_RULE_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(MEASUREMENT_RULE_DIR, fname), "r", encoding="utf-8") as f:
            rules.append(json.load(f))

    # 👉 현재는 단순 통과 (게이트 구조만 확보)
    return {
        "valid": True,
        "applied_rules": [r.get("validation_id") for r in rules]
    }


# =========================================================
# 2. Build L1 state (4-axis coordinate)
# =========================================================
def build_l1_state(llm_keywords: List[Dict]) -> Dict:
    state = {
        "regime": set(),
        "slope": set(),
        "magnitude": set(),
        "structure": "single_regime",
        "evidence": []
    }

    for entry in llm_keywords:
        kw = entry["keyword"].lower()
        ev = entry["evidence"].lower()

        # -------- regime --------
        if "low" in kw or "0." in ev or "1." in ev:
            state["regime"].add("low_field")
        if "threshold" in kw or "2." in ev:
            state["regime"].add("intermediate_field")
        if "high" in kw or "5." in ev:
            state["regime"].add("high_field")

        # -------- slope --------
        if "sharp" in kw or "rapid" in ev:
            state["slope"].add("abrupt")
        if "gradual" in kw or "slow" in ev:
            state["slope"].add("gradual")

        # -------- magnitude --------
        if "e-12" in ev or "e-11" in ev:
            state["magnitude"].add("near_noise")
        elif "e-9" in ev or "e-6" in ev:
            state["magnitude"].add("finite")
        elif "e-3" in ev or "e-2" in ev:
            state["magnitude"].add("large")

        state["evidence"].append(entry["evidence"])

    if len(state["regime"]) > 1:
        state["structure"] = "multi_regime"

    # set → list (JSON-safe)
    state["regime"] = list(state["regime"])
    state["slope"] = list(state["slope"])
    state["magnitude"] = list(state["magnitude"])

    return state


# =========================================================
# 3. Evaluate Scientific Justification (file-by-file)
# =========================================================
def evaluate_scientific_justification(l1_state: Dict) -> List[Dict]:
    proposals = []

    for fname in os.listdir(ONTOLOGY_DIR):
        if not fname.endswith(".json"):
            continue

        with open(os.path.join(ONTOLOGY_DIR, fname), "r", encoding="utf-8") as f:
            sj = json.load(f)["scientific_justification"]

        for mech in sj.get("mechanism_proposals", []):
            score = 0

            for coord in mech.get("supported_coordinates", []):
                if (
                    coord["regime"] in l1_state["regime"]
                    and coord["slope"] in l1_state["slope"]
                    and coord["magnitude"] in l1_state["magnitude"]
                ):
                    score += 1

            if score > 0:
                proposals.append({
                    "ontology_file": fname,
                    "justification_id": sj["justification_id"],
                    "mechanism_id": mech["mechanism_id"],
                    "score": score,
                    "interpretation": mech.get("interpretation_note")
                })

    proposals.sort(key=lambda x: x["score"], reverse=True)
    return proposals


# =========================================================
# 4. ENTRY POINT
# =========================================================
def run_l1_engine(raw_data: str) -> Dict:
    try:
        # 1. Measurement gate
        validation = validate_measurement(raw_data)
        if not validation["valid"]:
            return {
                "error": "Measurement validation failed",
                "details": validation
            }

        # 2. LLM observation
        llm_result = llm_analyze_numeric(raw_data)

        # 3. Build L1 coordinate
        l1_state = build_l1_state(llm_result["keywords"])

        # 4. SJ evaluation
        sj_proposals = evaluate_scientific_justification(l1_state)
        print("ASSUMPTIONS:", llm_result.get("assumptions"))


        return {
            "measurement_validation": validation,
            "llm_pattern": llm_result["pattern"],
            "llm_keywords": llm_result["keywords"],
            "assumptions": llm_result.get("assumptions", []),
            "l1_state": l1_state,
            "sj_proposals": sj_proposals,
            
            #---------- 상용자에게 보여줄 최종 서술
            "system_narrative": "\n\n".join([
                render_l1_state_ko(l1_state),
                render_assumptions_ko(llm_result.get("assumptions", [])),
                render_sj_proposal_ko(sj_proposals)
            ]),                        
            # ---- UI logs ----
            "L1 좌표 요약": render_l1_state_ko(l1_state),
            "과학적 정당화 제안": render_sj_proposal_ko(sj_proposals)
        }
    except Exception as e:
        return {
            "error": "L1 SJ engine failed",
            "details": str(e)
        }