# backend/llm_adapter.py
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
import re
import math
import hashlib
import time
import csv
from typing import Dict, Any, List, Optional, Tuple

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

    Output:
        {
            "pattern": str,
            "keywords": [{"keyword": str, "evidence": str}],
            "metrics": {
                "absI_decades_span": float,
                "v_knee": float|None,
                "v_knee_criterion": str|None
            },
            "regimes": [
                {"name":"low_|V|",  "v_range":[...,...], "delta_decades_robust":..., "mean_slope_log_absI_per_logV":...},
                {"name":"high_|V|", "v_range":[...,...], "delta_decades_robust":..., "mean_slope_log_absI_per_logV":...}
            ],
            "assumptions": [ ... ]
        }
    """
    parsed: Dict[str, Any] = {"pattern": "", "keywords": [], "metrics": {}}
    assumptions: List[Dict[str, Any]] = []

    user_prompt = _build_prompt(raw_data)
    system_prompt = _build_system_prompt_observation_only()

    try:
        # Prefer structured JSON output if supported
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except Exception:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )

        content = response.choices[0].message.content or ""
        parsed = _parse_llm_output(content)

        # ---------- code-based backfill/normalization (CODE is source of truth) ----------
        span_raw = compute_absI_decades_span_from_raw(raw_data, low_clip_percent=5.0)

        reg = compute_regimes_from_raw(raw_data)
        regimes = reg.get("regimes", []) or []
        threshold = reg.get("threshold") or {}

        metrics = parsed.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}

        # add threshold info
        metrics["v_knee"] = threshold.get("v_knee")
        metrics["v_knee_criterion"] = threshold.get("criterion")

        # ensure absI_decades_span is float + robust
        try:
            llm_val = float(metrics.get("absI_decades_span")) if "absI_decades_span" in metrics else None
        except Exception:
            llm_val = None

        if llm_val is None or abs(llm_val - span_raw) > 1.0:
            metrics["absI_decades_span"] = float(span_raw)
        else:
            metrics["absI_decades_span"] = float(llm_val)

        parsed["metrics"] = metrics
        parsed["regimes"] = regimes

        # ---- normalize pattern (NEVER None) ----
        parsed["pattern"] = str(parsed.get("pattern") or "")

        assumptions = _extract_observation_assumptions_from_json(parsed, raw_text=content)
        

        return {
            "pattern": parsed.get("pattern", ""),
            "keywords": parsed.get("keywords", []),
            "metrics": parsed.get("metrics", {}),
            "regimes": parsed.get("regimes", []),
            "assumptions": assumptions,
        }

    except Exception as e:
        # Still return stable schema
        parsed["pattern"] = str(parsed.get("pattern") or "")
        return {
            "pattern": parsed.get("pattern", "LLM analysis failed"),
            "keywords": parsed.get("keywords", []),
            "metrics": parsed.get("metrics", {}),
            "regimes": parsed.get("regimes", []),
            "assumptions": assumptions,
            "error": str(e),
        }


# =========================================================
# System prompt (observation only)
# =========================================================
def _build_system_prompt_observation_only() -> str:
    return (
        "You are a scientific observation assistant.\n"
        "You ONLY describe observable patterns in numeric data.\n"
        "You MUST NOT interpret mechanisms or causes.\n"
        "You MUST NOT mention physics models or mechanism names "
        "(e.g., tunneling, Schottky, Poole-Frenkel, Arrhenius, hopping, SCLC, FN, breakdown).\n"
        "You MUST NOT use ontology IDs.\n"
        "You MUST output valid JSON only, following the schema given by the user.\n"
        "If information is insufficient, state that as an observation limitation (still in JSON).\n"
    )


# =========================================================
# Prompt builder (user prompt)
# =========================================================
def _build_prompt(raw_data: str) -> str:
    return f"""
You are given raw experimental numeric data.

TASK:
1) Describe ONLY observable patterns.
2) Extract descriptive L1 keywords.
3) Report minimal observation metrics for downstream rule checks.

STRICT RULES:
- Do NOT mention physical mechanisms.
- Do NOT mention models (Arrhenius, hopping, tunneling, Schottky, Poole-Frenkel, SCLC, FN, breakdown, etc.).
- Do NOT explain causes.
- Use neutral, observational scientific language only.
- Output JSON ONLY. No markdown, no extra text.

METRICS TO INCLUDE:
- absI_decades_span: the decades spanned by |I| over the dataset.
  (If you cannot compute reliably, omit it; the caller may backfill.)

OUTPUT FORMAT (JSON ONLY):
{{
  "pattern": "<short summary of observed patterns>",
  "metrics": {{
    "absI_decades_span": <number>
  }},
  "keywords": [
    {{
      "keyword": "<descriptive keyword>",
      "evidence": "<sentence citing numeric evidence>"
    }}
  ]
}}

RAW DATA:
{raw_data}
""".strip()


# =========================================================
# Robust metric computation
# =========================================================
def compute_absI_decades_span_from_raw(raw_data: str, low_clip_percent: float = 1.0) -> float:
    """
    Robust decades span:
    - Parse I column
    - Compute log10(max(|I|)) - log10(P_low(|I|))
    """
    absI: List[float] = []

    for line in raw_data.splitlines():
        line = line.strip()
        if not line:
            continue

        ll = line.lower()
        if ("voltage" in ll) or ("current" in ll) or ll.startswith("v,") or ll.startswith("v\t") or ll.startswith("v "):
            continue

        parts = [p for p in re.split(r"[,\s\t]+", line) if p]
        if len(parts) < 2:
            continue

        try:
            i = float(parts[1])
        except Exception:
            continue

        ai = abs(i)
        if ai > 0 and math.isfinite(ai):
            absI.append(ai)

    if len(absI) < 2:
        return 0.0

    absI.sort()
    mx = absI[-1]

    p = float(low_clip_percent)
    p = max(0.0, min(p, 50.0))
    idx = int((p / 100.0) * (len(absI) - 1))
    idx = max(0, min(idx, len(absI) - 1))
    mn = absI[idx]

    if mn <= 0 or not math.isfinite(mn) or mx <= 0 or not math.isfinite(mx):
        return 0.0

    return math.log10(mx) - math.log10(mn)


# =========================================================
# Parse (V,I) and save CSV
# =========================================================
def parse_vi_from_raw(raw_data: str) -> List[Tuple[float, float]]:
    """
    Parse (V, I) pairs from raw text. Accepts CSV / whitespace / tab.
    Saves a CSV to ./runs for later plotting.
    """
    pairs: List[Tuple[float, float]] = []

    for line in raw_data.splitlines():
        line = line.strip()
        if not line:
            continue

        ll = line.lower()
        if ("voltage" in ll) or ("current" in ll) or ll.startswith("v,") or ll.startswith("v\t") or ll.startswith("v "):
            continue

        parts = [p for p in re.split(r"[,\s\t]+", line) if p]
        if len(parts) < 2:
            continue

        try:
            v = float(parts[0])
            i = float(parts[1])
        except Exception:
            continue

        if math.isfinite(v) and math.isfinite(i):
            pairs.append((v, i))

    # save (best-effort)
    try:
        runs_dir = "./runs"
        os.makedirs(runs_dir, exist_ok=True)
        raw_hash = hashlib.sha256(raw_data.encode("utf-8", errors="ignore")).hexdigest()[:10]
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(runs_dir, f"parsed_vi_{ts}_{raw_hash}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["V", "I"])
            w.writerows(pairs)
    except Exception:
        pass

    return pairs


# =========================================================
# Regime extraction (numeric)
# =========================================================
def compute_regimes_from_raw(raw_data: str, v_min_abs: float = 1e-3) -> Dict[str, Any]:
    """
    Robust 2-regime summary using |V| and log-log slopes.
    Split by |V| 30th percentile for stability.
    """
    pairs = parse_vi_from_raw(raw_data)
    if len(pairs) < 10:
        return {"regimes": [], "threshold": None}

    x: List[float] = []   # |V|
    lx: List[float] = []  # log10(|V|)
    ly: List[float] = []  # log10(|I|)

    for v, i in pairs:
        av = abs(v)
        ai = abs(i)
        if av < v_min_abs:
            continue
        if ai <= 0 or not math.isfinite(ai):
            continue
        x.append(av)
        lx.append(math.log10(av))
        ly.append(math.log10(ai))

    if len(x) < 10:
        return {"regimes": [], "threshold": None}

    order = sorted(range(len(x)), key=lambda k: x[k])
    x = [x[k] for k in order]
    lx = [lx[k] for k in order]
    ly = [ly[k] for k in order]

    split_idx = int(0.30 * (len(x) - 1))
    split_idx = max(1, min(split_idx, len(x) - 2))
    v_split = x[split_idx]

    low_pts = list(zip(x[: split_idx + 1], lx[: split_idx + 1], ly[: split_idx + 1]))
    high_pts = list(zip(x[split_idx + 1 :], lx[split_idx + 1 :], ly[split_idx + 1 :]))

    def _pct(arr: List[float], p: float) -> float:
        arr2 = sorted(arr)
        idx = int((p / 100.0) * (len(arr2) - 1))
        idx = max(0, min(idx, len(arr2) - 1))
        return arr2[idx]

    def summarize(points: List[Tuple[float, float, float]], name: str) -> Dict[str, Any]:
        if len(points) < 3:
            return {
                "name": name,
                "v_range": None,
                "delta_decades_robust": 0.0,
                "mean_slope_log_absI_per_logV": 0.0,
            }

        vx = [p[0] for p in points]
        lxx = [p[1] for p in points]
        lyy = [p[2] for p in points]

        vmin, vmax = min(vx), max(vx)

        p1 = _pct(lyy, 1.0)
        p99 = _pct(lyy, 99.0)
        delta_dec_robust = p99 - p1

        slopes: List[float] = []
        for k in range(1, len(points)):
            dlx = lxx[k] - lxx[k - 1]
            if abs(dlx) < 1e-9:
                continue
            slopes.append((lyy[k] - lyy[k - 1]) / dlx)

        mean_s = sum(slopes) / len(slopes) if slopes else 0.0

        return {
            "name": name,
            "v_range": [float(vmin), float(vmax)],
            "delta_decades_robust": float(delta_dec_robust),
            "mean_slope_log_absI_per_logV": float(mean_s),
        }

    regimes = [
        summarize(low_pts, "low_|V|"),
        summarize(high_pts, "high_|V|"),
    ]

    return {
        "regimes": regimes,
        "threshold": {"v_knee": float(v_split), "criterion": "percentile_split_30"},
    }


# =========================================================
# Extract observation assumptions (lightweight)
# =========================================================
from typing import Any, Dict, List

def _extract_observation_assumptions_from_json(parsed: Dict[str, Any], raw_text: str = "") -> List[Dict[str, Any]]:
    """
    변형 포인트
    - 이 함수는 '어떤 가정이 적용되는지'를 선택한다.
    - 가정의 statement/impact_axis는 가능하면 '온톨로지(레지스트리)'에서 조회해서 사용한다.
    - 레지스트리가 없으면(개발 중) 기존 기본 문장을 fallback으로 사용한다.
    """

    assumptions: List[Dict[str, Any]] = []

    # -----------------------------
    # 1) 텍스트 blob 구성 (기존 유지 + 방어)
    # -----------------------------
    pattern = str(parsed.get("pattern", "")).lower()
    #print(f"Pattern: {pattern}")
    keywords = parsed.get("keywords", [])
    #print(f"Keywords: {keywords}")

    kw_parts: List[str] = []
    if isinstance(keywords, list):
        for k in keywords:
            if isinstance(k, dict):
                kw_parts.append(str(k.get("keyword", "")))
                kw_parts.append(str(k.get("evidence", "")))
            else:
                kw_parts.append(str(k))

    kw_text = " ".join(kw_parts).lower()
    blob = (pattern + "\n" + kw_text + "\n" + (raw_text or "").lower())

    # 디버그 출력은 필요하면 유지
    print(f"Blob: {blob}")

    # -----------------------------
    # 2) 온톨로지 assumption 레지스트리 조회 (있으면 사용)
    #    - parsed에 실려오게 하거나, 상위에서 주입하는 방식으로 연결 가능
    #    - 예: parsed["assumption_registry"] = {"A_MAG_NOISE": {...}, ...}
    # -----------------------------
    registry = parsed.get("assumption_registry", None)
    if not isinstance(registry, dict):
        registry = {}

    def _lookup_assumption_card(assumption_id: str, fallback_statement: str, fallback_axis: List[str]) -> Dict[str, Any]:
        """
        온톨로지에 정의된 가정이면 그 정의를 그대로 사용하고,
        없으면 fallback 사용.
        """
        ref = registry.get(assumption_id)
        if isinstance(ref, dict):
            # 온톨로지 정의를 우선 사용 (statement/impact_axis 등)
            card = {
                "assumption_id": assumption_id,
                "statement": ref.get("statement", fallback_statement),
                "impact_axis": ref.get("impact_axis", fallback_axis),
            }
            # 온톨로지에서 추가 필드가 있으면 그대로 포함(선택)
            # 예: severity, source, description_ko 등
            for extra_key in ("severity", "source", "description", "description_ko", "note"):
                if extra_key in ref and extra_key not in card:
                    card[extra_key] = ref[extra_key]
            return card

        # 온톨로지 정의가 없으면 fallback
        return {
            "assumption_id": assumption_id,
            "statement": fallback_statement,
            "impact_axis": fallback_axis,
        }

    # -----------------------------
    # 3) 룰: 트리거 감지 → assumption_id 선택
    #    (선택된 ID는 온톨로지 정의로 '표현'되도록 lookup)
    # -----------------------------

    # A_MAG_NOISE
    if ("noise" in blob) or ("floor" in blob) or ("clamp" in blob) or ("limit" in blob):
        assumptions.append(
            _lookup_assumption_card(
                "A_MAG_NOISE",
                fallback_statement="Very small magnitudes may have been treated as near the measurement floor/noise level.",
                fallback_axis=["magnitude"],
            )
        )

    # A_SLOPE_ABRUPT
    if ("threshold" in blob) or ("knee" in blob) or ("abrupt" in blob) or ("sharp" in blob):
        assumptions.append(
            _lookup_assumption_card(
                "A_SLOPE_ABRUPT",
                fallback_statement="A rapid change was flagged using a heuristic rate-of-change criterion.",
                fallback_axis=["slope"],
            )
        )

    # -----------------------------
    # 4) 중복 제거 (assumption_id 기준)
    # -----------------------------
    dedup: Dict[str, Dict[str, Any]] = {}
    for a in assumptions:
        aid = a.get("assumption_id")
        if aid:
            dedup[aid] = a

    return list(dedup.values())


# =========================================================
# Output parser
# =========================================================
def _parse_llm_output(text: str) -> Dict[str, Any]:
    data = _safe_json_loads(text)
    if data is None:
        return {"pattern": "Unparseable LLM output", "keywords": [], "metrics": {}}

    pattern = str(data.get("pattern", "no pattern described")).strip()
    keywords = data.get("keywords", [])
    metrics = data.get("metrics", {}) if isinstance(data.get("metrics", {}), dict) else {}

    clean_keywords: List[Dict[str, str]] = []
    if isinstance(keywords, list):
        for kw in keywords:
            if not isinstance(kw, dict):
                continue
            if "keyword" not in kw or "evidence" not in kw:
                continue
            clean_keywords.append({
                "keyword": str(kw["keyword"]).strip(),
                "evidence": str(kw["evidence"]).strip(),
            })

    clean_metrics: Dict[str, Any] = {}
    if "absI_decades_span" in metrics:
        try:
            clean_metrics["absI_decades_span"] = float(metrics["absI_decades_span"])
        except Exception:
            pass

    return {"pattern": pattern, "keywords": clean_keywords, "metrics": clean_metrics}


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
