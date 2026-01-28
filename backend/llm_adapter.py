# llm_adapter.py
"""
LLM Adapter for L1 Observation (Scientific Justification)

Role:
- L0 numeric data -> L1 observation
- NO interpretation
- NO ontology awareness
- NO model/mechanism naming
"""

import os
import json
from typing import Dict, Any, List

from openai import OpenAI


# =========================================================
# Init OpenAI client
# =========================================================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =========================================================
# Public API
# =========================================================
def llm_analyze_numeric(raw_data: str) -> Dict[str, Any]:
    """
    Entry point used by L1 engine.

    Input:
        raw_data (str): raw numeric experimental data (L0)

    Output:
        {
            "pattern": str,
            "keywords": [
                {
                    "keyword": str,
                    "evidence": str
                }
            ]
        }
    """

    prompt = _build_prompt(raw_data)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a scientific observation assistant.\n"
                        "You ONLY describe observable patterns in numeric data.\n"
                        "You NEVER interpret mechanisms or models,\n\n"
                        "In addition, you MUST explicitly state any criteria or thresholds\n"
                        "you relied on to describe patterns (e.g. range definitions,\n"
                        "noise assumptions, qualitative thresholds).\n"
                        "These are NOT mechanisms, but observation assumptions."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0
        )

        content = response.choices[0].message.content
        parsed = _parse_llm_output(content)
        

        assumptions =_extract_observation_assumptions(content) 

        return{
            "pattern": parsed.get("pattern",""),
            "keywords": parsed.get("keywords",[]),
            "assumptions": assumptions
        }

    except Exception as e:
        # ---------- Safe fallback ----------
        return {
            "pattern": "LLM analysis failed",
            "keywords": [],
            "error": str(e)
        }

#========================================================
# Extract observation assumptions
#========================================================
def _extract_observation_assumptions(content: str) -> List[Dict[str, Any]]:
    """
    Extract explicit observation assumptions from LLM output.
    These assumptions define HOW observations were categorized,
    not WHY they occur.
    """

    # 초기 버전: rule / prompt 기반 단순 추출
    # (나중에 LLM 2-pass로 고도화 가능)

    assumptions = []

    if "below" in content or "low-field" in content:
        assumptions.append({
            "assumption_id": "A_REGIME_LOW",
            "statement": "Low-field region was defined using a lower-range threshold",
            "impact_axis": ["regime"]
        })

    if "abrupt" in content or "sharp" in content:
        assumptions.append({
            "assumption_id": "A_SLOPE_ABRUPT",
            "statement": "Abrupt slope was identified based on qualitative rate of change",
            "impact_axis": ["slope"]
        })

    if "noise" in content:
        assumptions.append({
            "assumption_id": "A_MAG_NOISE",
            "statement": "Lower magnitude values were treated as near noise floor",
            "impact_axis": ["magnitude"]
        })

    return assumptions

# =========================================================
# Prompt builder
# =========================================================
def _build_prompt(raw_data: str) -> str:
    return f"""
You are given raw experimental numeric data.

TASK:
1. Describe ONLY observable patterns.
2. Extract descriptive L1 keywords.
3. For each keyword, provide evidence grounded in the data.

STRICT RULES:
- Do NOT mention physical mechanisms.
- Do NOT mention models (Arrhenius, hopping, tunneling, etc.).
- Do NOT explain causes.
- Use neutral, observational scientific language only.

KEYWORD RULES:
- Keywords must be descriptive (e.g., "temperature dependence", "voltage dependence").
- Keywords must NOT imply interpretation.

OUTPUT FORMAT (JSON ONLY):

{{
  "pattern": "<short summary of observed patterns>",
  "keywords": [
    {{
      "keyword": "<descriptive keyword>",
      "evidence": "<sentence citing numeric evidence>"
    }}
  ]
}}

RAW DATA:
{raw_data}
"""


# =========================================================
# Output parser
# =========================================================
def _parse_llm_output(text: str) -> Dict[str, Any]:
    """
    Parse LLM output safely.
    Ensures minimal schema validity.
    """

    try:
        data = json.loads(text)

        # --- minimal schema enforcement ---
        pattern = data.get("pattern", "no pattern described")
        keywords = data.get("keywords", [])

        clean_keywords: List[Dict[str, str]] = []

        for kw in keywords:
            if not isinstance(kw, dict):
                continue
            if "keyword" not in kw or "evidence" not in kw:
                continue

            clean_keywords.append({
                "keyword": str(kw["keyword"]).strip(),
                "evidence": str(kw["evidence"]).strip()
            })

        return {
            "pattern": pattern,
            "keywords": clean_keywords
        }

    except Exception:
        # ---------- Hard fallback ----------
        return {
            "pattern": "Unparseable LLM output",
            "keywords": []
        }
