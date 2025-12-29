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
                        "You NEVER interpret mechanisms or models."
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
        return _parse_llm_output(content)

    except Exception as e:
        # ---------- Safe fallback ----------
        return {
            "pattern": "LLM analysis failed",
            "keywords": [],
            "error": str(e)
        }


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
