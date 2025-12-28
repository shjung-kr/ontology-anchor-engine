import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

# =========================================================
# Init
# =========================================================
app = FastAPI(title="V14.0 SJ Ontology Engine")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ONTOLOGY_DIR = "./ontology/scientific_justification"

# =========================================================
# Models
# =========================================================
class RawInput(BaseModel):
    raw_data: str


# =========================================================
# LLM: numeric data → pattern + keyword + evidence
# =========================================================
def llm_analyze_numeric(raw_data: str) -> dict:
    """
    LLM MUST:
    - read numeric/tabular data only
    - infer pattern from trends
    - extract keywords with numerical evidence
    - NO questions, NO assumptions, NO dialogue
    """

    prompt = f"""
You are given RAW experimental IV transport data.

Rules:
- Input contains numeric or tabular experimental data.
- Do NOT ask questions.
- Do NOT rely on human explanations.
- Infer patterns ONLY from numerical trends.

Tasks:
1. Identify the dominant transport pattern
   (e.g. exponential, linear, nonlinear, saturation).
2. Extract IMPLIED physical keywords.
3. For EACH keyword, provide numerical evidence.

Return ONLY valid JSON in EXACT format:
{{
  "pattern": "<pattern>",
  "keywords": [
    {{
      "keyword": "<keyword>",
      "evidence": "<numerical or trend-based justification>"
    }}
  ]
}}

Raw experimental data:
{raw_data}
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return json.loads(res.choices[0].message.content)


# =========================================================
# Engine: ontology FILE selection (keyword-grounded)
# =========================================================
def select_ontology(keyword_objs):
    logs = []
    detected_keywords = [k["keyword"].lower() for k in keyword_objs]

    for fname in os.listdir(ONTOLOGY_DIR):
        if not fname.endswith(".json"):
            continue

        path = os.path.join(ONTOLOGY_DIR, fname)
        ontology = json.load(open(path))

        ontology_keywords = [k.lower() for k in ontology.get("keywords", [])]

        matched = [
            kw for kw in detected_keywords
            if kw in ontology_keywords
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
# Ontology-driven next question generation
# =========================================================
def generate_next_questions(selected):
    if not selected:
        return []

    path = os.path.join(ONTOLOGY_DIR, selected["file"])
    ontology = json.load(open(path))
    return ontology.get("next_questions", [])


# =========================================================
# API
# =========================================================
@app.post("/v14/run")
def run_engine(data: RawInput):
    # 1. LLM numeric analysis
    llm_result = llm_analyze_numeric(data.raw_data)

    # 2. Ontology selection
    selected, selection_log = select_ontology(
        llm_result["keywords"]
    )

    # 3. Ontology-driven questions
    next_questions = generate_next_questions(selected)

    # 4. Full structured log (V14 output)
    return {
        "llm_pattern": llm_result["pattern"],
        "llm_keyword_log": llm_result["keywords"],

        "ontology_selection_log": selection_log,
        "selected_ontology": selected,

        "next_questions_generated": next_questions
    }


from fastapi.staticfiles import StaticFiles

app.mount("/",
    "/static", StaticFiles(directory="../frontend"), 
                                 name="frontend", html=True)