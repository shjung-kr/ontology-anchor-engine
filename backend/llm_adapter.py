# backend/llm_adapter.py
"""
LLM Adapter for L1 Observation.

This module must remain usable without OpenAI installed or configured.
Numeric fallbacks are the source of truth; the LLM is optional enrichment.
"""

import csv
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.domains.iv.common import (
    format_confirmed_conditions_ko,
    join_term_labels,
    summarize_observation_pattern_ko,
    term_description,
    term_label,
)
from backend.measurement_validations.parser import parse_vi

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
PROMPTS_DIR = BASE_DIR.parent / "prompts"
DEFAULT_MODEL = "gpt-5.4"


def _get_openai_client():
    if OpenAI is None:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _normalize_pattern_to_korean(pattern: str) -> str:
    normalized = summarize_observation_pattern_ko(pattern)
    return normalized or str(pattern or "").strip()


def _extract_goal_like_note(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    goal_markers = (
        "목적",
        "목표",
        "goal",
        "aim",
        "줄이는거",
        "줄이고",
        "낮추고",
        "억제",
        "증가",
        "늘리",
        "향상",
        "개선",
        "without carrier loss",
        "캐리어 손실없이",
        "캐리어 손실 없이",
    )
    domain_markers = (
        "누설전류",
        "leakage",
        "턴온",
        "turn-on",
        "turn on",
        "터널링",
        "tunneling",
        "전류",
        "장벽",
        "carrier",
        "캐리어",
    )
    if any(marker in lowered for marker in goal_markers) and any(marker in lowered for marker in domain_markers):
        return value
    return ""


def _resolve_research_goal(intent_profile: Dict[str, Any]) -> str:
    research_goal = str(intent_profile.get("research_goal") or "").strip()
    if research_goal:
        return research_goal
    for note in reversed(intent_profile.get("notes", [])):
        candidate = _extract_goal_like_note(str(note))
        if candidate:
            return candidate
    return ""


def llm_analyze_numeric(raw_data: str) -> Dict[str, Any]:
    """
    Entry point used by L1 engine.
    Returns a stable schema even when the LLM path is unavailable.
    """
    span_raw = compute_absI_decades_span_from_raw(raw_data, low_clip_percent=5.0)
    reg = compute_regimes_from_raw(raw_data)
    regimes = reg.get("regimes", []) or []
    threshold = reg.get("threshold") or {}

    fallback = _build_numeric_observation(raw_data, span_raw, regimes, threshold)
    parsed: Dict[str, Any] = {
        "pattern": fallback["pattern"],
        "keywords": fallback["keywords"],
        "metrics": fallback["metrics"],
        "regimes": regimes,
    }
    assumptions: List[Dict[str, Any]] = []
    llm_trace: Dict[str, Any] = {
        "used_llm": False,
        "status": "numeric_fallback",
        "model": DEFAULT_MODEL,
    }

    client = _get_openai_client()
    system_prompt = _build_system_prompt_observation_only()
    user_prompt = _build_prompt(raw_data)

    if client is not None:
        try:
            try:
                response = client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
            except Exception:
                response = client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                )

            content = response.choices[0].message.content or ""
            llm_parsed = _parse_llm_output(content)
            metrics = llm_parsed.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}

            metrics["v_knee"] = threshold.get("v_knee")
            metrics["v_knee_criterion"] = threshold.get("criterion")

            try:
                llm_val = float(metrics.get("absI_decades_span")) if "absI_decades_span" in metrics else None
            except Exception:
                llm_val = None
            metrics["absI_decades_span"] = float(span_raw if llm_val is None or abs(llm_val - span_raw) > 1.0 else llm_val)

            parsed = {
                "pattern": str(llm_parsed.get("pattern") or fallback["pattern"]),
                "keywords": llm_parsed.get("keywords") or fallback["keywords"],
                "metrics": metrics,
                "regimes": regimes,
            }
            llm_trace = {
                "used_llm": True,
                "status": "ok",
                "model": DEFAULT_MODEL,
                "raw_response": content,
            }
        except Exception as exc:
            llm_trace = {
                "used_llm": False,
                "status": "fallback_after_llm_error",
                "model": DEFAULT_MODEL,
                "error": str(exc),
            }
            parsed = fallback

    assumptions = _extract_observation_assumptions_from_json(parsed)
    return {
        "pattern": _normalize_pattern_to_korean(str(parsed.get("pattern", ""))),
        "keywords": parsed.get("keywords", []),
        "metrics": parsed.get("metrics", {}),
        "regimes": parsed.get("regimes", []),
        "assumptions": assumptions,
        "llm_trace": llm_trace,
        "prompt_bundle": {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "model": DEFAULT_MODEL,
            "temperature": 0.0,
            "top_p": 1.0,
        },
    }


def answer_with_analysis_context(
    user_text: str,
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
    chat_history: Optional[List[Dict[str, Any]]] = None,
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    완성된 분석 결과를 컨텍스트로 사용해 자유 질의응답을 수행한다.
    OpenAI 사용이 불가하면 used_llm=False 상태로 반환한다.
    """

    client = _get_openai_client()
    if client is None:
        return {"used_llm": False, "status": "llm_unavailable", "answer": ""}

    system_prompt = (
        "You are a scientific analysis assistant for experimental I-V data.\n"
        "Answer in natural Korean.\n"
        "Your first job is to ground every answer in the provided numeric evidence.\n"
        "Do not give generic mechanism talk without citing concrete observations from the run.\n"
        "Every answer must include at least two concrete evidence items when available, such as:\n"
        "- numeric ranges\n"
        "- slope values\n"
        "- knee voltage\n"
        "- current span in decades\n"
        "- validation warnings\n"
        "- observed low-field/high-field regime behavior\n"
        "Prefer this order: observed data -> interpretation -> remaining uncertainty.\n"
        "Do not simply restate the whole summary unless necessary.\n"
        "Prioritize the user's intent and focus only on relevant evidence.\n"
        "Avoid ontology IDs unless the user explicitly asks for them.\n"
        "Explain what values/features mean in plain language when helpful.\n"
        "If evidence is insufficient, say exactly what is missing.\n"
        "Keep answers concise but specific.\n"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for item in (chat_history or [])[-6:]:
        role = item.get("role")
        text = str(item.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            messages.append({"role": role, "content": text})

    messages.append(
        {
            "role": "user",
            "content": _build_analysis_context_prompt(
                user_text,
                snapshot,
                intent_profile,
                reranked_proposals,
                run_dir=run_dir,
            ),
        }
    )

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.15,
        )
        content = response.choices[0].message.content or ""
        return {
            "used_llm": True,
            "status": "ok",
            "answer": content.strip(),
            "model": DEFAULT_MODEL,
        }
    except Exception as exc:
        return {
            "used_llm": False,
            "status": "llm_error",
            "answer": "",
            "error": str(exc),
            "model": DEFAULT_MODEL,
        }


def _build_analysis_context_prompt(
    user_text: str,
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
    run_dir: Optional[Path] = None,
) -> str:
    top = reranked_proposals[0] if reranked_proposals else {}
    claim = term_label(str(top.get("claim_concept") or "")) or "해석 후보 없음"
    matched = top.get("matched_features", []) or []
    assumptions = top.get("sj_assumptions", []) or []
    required_features = top.get("required_features", []) or []
    measurement_validation = snapshot.get("measurement_validation", {}) or {}
    warnings = measurement_validation.get("warnings", []) or []
    conditions = intent_profile.get("confirmed_conditions", {}) or {}
    research_goal = _resolve_research_goal(intent_profile)
    metrics = snapshot.get("metrics", {}) or {}
    regimes = snapshot.get("regimes", []) or []

    prioritized_evidence = _select_prioritized_evidence(user_text, snapshot, top)
    regime_summary = _format_regime_summary(regimes)
    metric_summary = _format_metric_summary(metrics)
    warning_lines = [f"- {warning}" for warning in warnings[:4]]
    proposal_evidence = _format_proposal_evidence(top)

    feature_notes: List[str] = []
    for feature_id in matched[:3]:
        label = term_label(str(feature_id))
        desc = term_description(str(feature_id))
        feature_notes.append(f"- {label}: {desc or '설명 정보 없음'}")

    assumption_notes: List[str] = []
    for assumption_id in assumptions[:3]:
        label = term_label(str(assumption_id))
        desc = term_description(str(assumption_id))
        assumption_notes.append(f"- {label}: {desc or '설명 정보 없음'}")

    context_lines = [
        f"[user_question]\n{user_text}",
        f"[user_goal]\n{research_goal or '(none)'}",
        "[response_contract]\n"
        "- 답변은 질문에 바로 답하기\n"
        "- 먼저 데이터 관측 근거를 말한 뒤 해석을 붙이기\n"
        "- 가능하면 최소 2개의 수치 또는 구간 근거를 포함하기\n"
        "- 데이터에서 직접 읽히지 않는 일반론만 길게 말하지 않기\n"
        "- 마지막에는 남는 불확실성 또는 추가 확인 포인트를 짧게 덧붙이기",
        "[prioritized_evidence]\n" + ("\n".join(prioritized_evidence) if prioritized_evidence else "- 직접 인용할 강한 evidence가 아직 부족함"),
        "[measurement_metrics]\n" + ("\n".join(metric_summary) if metric_summary else "- (none)"),
        "[regime_summary]\n" + ("\n".join(regime_summary) if regime_summary else "- (none)"),
        f"[top_mechanism]\n- 최상위 해석: {claim}\n- score: {top.get('final_score', top.get('score'))}",
        "[proposal_evidence]\n" + ("\n".join(proposal_evidence) if proposal_evidence else "- (none)"),
        f"[observed_features]\n- 매칭 feature: {join_term_labels(matched) if matched else '(none)'}",
        f"[feature_meanings]\n" + ("\n".join(feature_notes) if feature_notes else "- (none)"),
        f"[assumptions]\n- 주요 가정: {join_term_labels(assumptions) if assumptions else '(none)'}",
        f"[assumption_meanings]\n" + ("\n".join(assumption_notes) if assumption_notes else "- (none)"),
        f"[required_features]\n- {join_term_labels(required_features) if required_features else '(none)'}",
        f"[conditions]\n- {format_confirmed_conditions_ko(conditions)}",
        f"[llm_observation]\n- {snapshot.get('llm_pattern') or '(none)'}",
        "[warnings]\n" + ("\n".join(warning_lines) if warning_lines else "- 경고 없음"),
    ]
    context_lines.append(
        "[answer_style]\n- [user_goal]이 있으면 그 목표를 답변의 최우선 제약으로 사용하기\n- 질문에 직접 관련된 evidence만 먼저 선택해서 설명하기\n- 저전압 누설 억제, 캐리어 손실 최소화, 터널링 전류 증가 같은 목표가 있으면 그 관점에서 관측값의 의미를 해석하기\n- 사용자가 묻지 않은 run 요약 반복하지 않기\n- 기계적으로 ontology label을 나열하지 말고, 관측값이 왜 그 해석을 지지하는지 설명하기"
    )
    if run_dir is not None:
        artifact_context = _build_run_artifacts_context(run_dir, include_all_json=False)
        if artifact_context:
            context_lines.append("[compact_run_artifacts]\n" + artifact_context)
    return "\n\n".join(context_lines)


def _build_run_artifacts_context(run_dir: Path, include_all_json: bool = False) -> str:
    if not run_dir.is_dir():
        return ""

    sections: List[str] = []
    candidate_paths = (
        sorted(run_dir.glob("*.json"))
        if include_all_json
        else [run_dir / name for name in ("manifest.json", "derived.json", "inference.json", "ontology_patch.json")]
    )
    for path in candidate_paths:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            content = _compact_json_for_prompt(path.name, parsed)
        except Exception:
            content = raw.strip() if "raw" in locals() else ""
        if not content:
            continue
        sections.append(f"## {path.name}\n{content}")
    return "\n\n".join(sections)


def _compact_json_for_prompt(name: str, parsed: Dict[str, Any]) -> str:
    if name == "manifest.json":
        return json.dumps(
            {
                "run_id": parsed.get("run_id"),
                "created_at_utc": parsed.get("created_at_utc"),
                "requested_run_id": parsed.get("requested_run_id"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if name == "derived.json":
        return json.dumps(
            {
                "metrics": parsed.get("metrics", {}),
                "regimes": parsed.get("regimes", []),
                "llm_pattern": parsed.get("llm_pattern", ""),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if name == "inference.json":
        return json.dumps(
            {
                "measurement_validation": parsed.get("measurement_validation", {}),
                "l1_state": parsed.get("l1_state", {}),
                "top_sj_proposal": ((parsed.get("sj_proposals") or [{}])[0] if parsed.get("sj_proposals") else {}),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if name == "ontology_patch.json":
        return json.dumps(
            {
                "claims": parsed.get("claims", []),
                "assumptions": parsed.get("assumptions", []),
                "measurement_conditions": parsed.get("measurement_conditions", []),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def _format_metric_summary(metrics: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    span = metrics.get("absI_decades_span")
    if isinstance(span, (int, float)):
        lines.append(f"- |I| dynamic range: 약 {float(span):.2f} decades")
    v_knee = metrics.get("v_knee")
    if isinstance(v_knee, (int, float)):
        lines.append(f"- knee voltage estimate: |V|≈{float(v_knee):.4g}")
    criterion = metrics.get("v_knee_criterion")
    if criterion:
        lines.append(f"- knee criterion: {criterion}")
    for key in ("current_ratio", "rectification_ratio", "threshold_voltage", "turn_on_voltage"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            lines.append(f"- {key}: {float(value):.4g}")
    return lines


def _format_regime_summary(regimes: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for regime in regimes[:2]:
        name = regime.get("name") or "regime"
        v_range = regime.get("v_range") or []
        delta = regime.get("delta_decades_robust")
        slope = regime.get("mean_slope_log_absI_per_logV")
        parts = [f"- {name}"]
        if isinstance(v_range, list) and len(v_range) == 2:
            parts.append(f"|V| range {float(v_range[0]):.4g}→{float(v_range[1]):.4g}")
        if isinstance(delta, (int, float)):
            parts.append(f"Δ|I|≈{float(delta):.2f} decades")
        if isinstance(slope, (int, float)):
            parts.append(f"log-log slope≈{float(slope):.2f}")
        lines.append(", ".join(parts))
    return lines


def _format_proposal_evidence(top: Dict[str, Any]) -> List[str]:
    if not top:
        return []
    lines: List[str] = []
    matched = top.get("matched_features", []) or []
    missing = [item for item in (top.get("required_features", []) or []) if item not in set(matched)]
    if matched:
        lines.append(f"- matched features: {join_term_labels(matched)}")
    if missing:
        lines.append(f"- still missing features: {join_term_labels(missing[:3])}")
    rerank_reasons = [str(item).strip() for item in (top.get("rerank_reasons", []) or []) if str(item).strip()]
    if rerank_reasons:
        lines.extend([f"- rerank reason: {item}" for item in rerank_reasons[:2]])
    return lines


def _select_prioritized_evidence(
    user_text: str,
    snapshot: Dict[str, Any],
    top: Dict[str, Any],
) -> List[str]:
    text = (user_text or "").lower()
    metrics = snapshot.get("metrics", {}) or {}
    regimes = snapshot.get("regimes", []) or []
    measurement_validation = snapshot.get("measurement_validation", {}) or {}
    warnings = measurement_validation.get("warnings", []) or []
    selected: List[str] = []

    span = metrics.get("absI_decades_span")
    if isinstance(span, (int, float)):
        selected.append(f"- 데이터 전체에서 |I| 변화폭은 약 {float(span):.2f} decades 입니다.")

    v_knee = metrics.get("v_knee")
    if isinstance(v_knee, (int, float)):
        selected.append(f"- 전류 거동이 바뀌는 knee는 |V|≈{float(v_knee):.4g} 부근으로 추정됩니다.")

    low = next((r for r in regimes if r.get("name") == "low_|V|"), None)
    high = next((r for r in regimes if r.get("name") == "high_|V|"), None)
    if low and isinstance(low.get("mean_slope_log_absI_per_logV"), (int, float)):
        selected.append(f"- 저전계 구간 log-log slope는 약 {float(low['mean_slope_log_absI_per_logV']):.2f} 입니다.")
    if high and isinstance(high.get("mean_slope_log_absI_per_logV"), (int, float)):
        selected.append(f"- 고전계 구간 log-log slope는 약 {float(high['mean_slope_log_absI_per_logV']):.2f} 입니다.")
    if high and isinstance(high.get("delta_decades_robust"), (int, float)):
        selected.append(f"- 고전계 구간에서 |I|는 약 {float(high['delta_decades_robust']):.2f} decades 변합니다.")

    if warnings:
        selected.append(f"- validation warning은 {len(warnings)}건이며 대표적으로 '{warnings[0]}' 가 있습니다.")

    matched = top.get("matched_features", []) or []
    if matched:
        selected.append(f"- 현재 상위 해석과 직접 맞물린 관측 feature는 {join_term_labels(matched[:3])} 입니다.")

    if any(token in text for token in ("왜", "이유", "cause", "reason", "메커니즘")):
        return selected[:5]
    if any(token in text for token in ("다음 실험", "실험", "next experiment", "plan")):
        prioritized = [item for item in selected if "warning" in item or "knee" in item or "slope" in item]
        return (prioritized + selected)[:5]
    if any(token in text for token in ("누설", "leakage", "turn-on", "턴온")):
        prioritized = [item for item in selected if "decades" in item or "knee" in item or "slope" in item]
        return (prioritized + selected)[:5]
    return selected[:5]


def _build_numeric_observation(
    raw_data: str,
    span_raw: float,
    regimes: List[Dict[str, Any]],
    threshold: Dict[str, Any],
) -> Dict[str, Any]:
    pattern_parts: List[str] = []
    keywords: List[Dict[str, str]] = []

    if span_raw >= 2.0:
        pattern_parts.append(f"데이터 전체에서 |I| 변화폭은 약 {span_raw:.2f} decades 입니다")
        keywords.append({
            "keyword": "broad current dynamic range",
            "evidence": f"|I| spans approximately {span_raw:.2f} decades.",
        })
    else:
        pattern_parts.append(f"|I| 변화폭은 약 {span_raw:.2f} decades 입니다")

    if threshold.get("v_knee") is not None:
        pattern_parts.append(f"|V|≈{float(threshold['v_knee']):.4g} 부근에서 전류 거동이 바뀌는 구간 분리가 관측됩니다")

    high = next((r for r in regimes if r.get("name") == "high_|V|"), None)
    low = next((r for r in regimes if r.get("name") == "low_|V|"), None)

    slope_ref = None
    if low and low.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(low["mean_slope_log_absI_per_logV"])
    elif high and high.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(high["mean_slope_log_absI_per_logV"])
    if slope_ref is not None:
        desc = "거의 선형에 가까운" if 0.85 <= slope_ref <= 1.15 else "선형보다 더 가파른 초선형"
        pattern_parts.append(f"저전압 구간의 log-log 기울기는 {slope_ref:.2f}로, {desc} 스케일링을 보입니다")
        keywords.append({
            "keyword": desc,
            "evidence": f"Representative log-log slope is {slope_ref:.2f}.",
        })

    if high:
        delta = float(high.get("delta_decades_robust", 0.0) or 0.0)
        high_slope = float(high.get("mean_slope_log_absI_per_logV", 0.0) or 0.0)
        if delta >= 2.0 and high_slope >= 2.0:
            keywords.append({
                "keyword": "field-enhanced current rise",
                "evidence": f"High-field regime spans {delta:.2f} decades with slope {high_slope:.2f}.",
            })

    return {
        "pattern": ". ".join(pattern_parts) if pattern_parts else "수치 기반 관측 요약을 생성하지 못했습니다.",
        "keywords": keywords,
        "metrics": {
            "absI_decades_span": float(span_raw),
            "v_knee": threshold.get("v_knee"),
            "v_knee_criterion": threshold.get("criterion"),
        },
        "regimes": regimes,
    }


def _read_prompt_file(name: str, fallback: str) -> str:
    path = PROMPTS_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return fallback


def _build_system_prompt_observation_only() -> str:
    fallback = (
        "You are a scientific observation assistant.\n"
        "You ONLY describe observable patterns in numeric data.\n"
        "You MUST NOT interpret mechanisms or causes.\n"
        "You MUST NOT use ontology IDs.\n"
        "You MUST output valid JSON only.\n"
    )
    return _read_prompt_file("system_prompt_v1.md", fallback)


def _build_prompt(raw_data: str) -> str:
    fallback = (
        "You are given raw experimental numeric data.\n\n"
        "TASK:\n"
        "1) Describe ONLY observable patterns.\n"
        "2) Extract descriptive L1 keywords.\n"
        "3) Report minimal observation metrics for downstream rule checks.\n\n"
        "OUTPUT FORMAT (JSON ONLY):\n"
        "{\n"
        '  "pattern": "<short summary>",\n'
        '  "metrics": {"absI_decades_span": <number>},\n'
        '  "keywords": [{"keyword": "<keyword>", "evidence": "<evidence>"}]\n'
        "}\n\n"
        "RAW DATA:\n"
        "{raw_data}\n"
    )
    template = _read_prompt_file("user_template_v1.md", fallback)
    return template.replace("{raw_data}", raw_data)


def compute_absI_decades_span_from_raw(raw_data: str, low_clip_percent: float = 1.0) -> float:
    _, I = parse_vi(raw_data)
    abs_i = [abs(x) for x in I if isinstance(x, (int, float)) and math.isfinite(x) and abs(x) > 0]
    if len(abs_i) < 2:
        return 0.0

    abs_i.sort()
    mx = abs_i[-1]
    p = max(0.0, min(float(low_clip_percent), 50.0))
    idx = int((p / 100.0) * (len(abs_i) - 1))
    idx = max(0, min(idx, len(abs_i) - 1))
    mn = abs_i[idx]
    if mn <= 0 or mx <= 0:
        return 0.0
    return math.log10(mx) - math.log10(mn)


def parse_vi_from_raw(raw_data: str) -> List[Tuple[float, float]]:
    V, I = parse_vi(raw_data)
    pairs = [
        (float(v), float(i))
        for v, i in zip(V, I)
        if isinstance(v, (int, float)) and isinstance(i, (int, float)) and math.isfinite(v) and math.isfinite(i)
    ]

    try:
        from backend.user_storage import get_user_runs_dir

        runs_dir = get_user_runs_dir()
        runs_dir.mkdir(parents=True, exist_ok=True)
        raw_hash = hashlib.sha256(raw_data.encode("utf-8", errors="ignore")).hexdigest()[:10]
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = runs_dir / f"parsed_vi_{ts}_{raw_hash}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["V", "I"])
            w.writerows(pairs)
    except Exception:
        pass

    return pairs


def compute_regimes_from_raw(raw_data: str, v_min_abs: float = 1e-3) -> Dict[str, Any]:
    pairs = parse_vi_from_raw(raw_data)
    if len(pairs) < 10:
        return {"regimes": [], "threshold": None}

    x: List[float] = []
    lx: List[float] = []
    ly: List[float] = []

    for v, i in pairs:
        av = abs(v)
        ai = abs(i)
        if av < v_min_abs or ai <= 0 or not math.isfinite(ai):
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

        p1 = _pct(lyy, 1.0)
        p99 = _pct(lyy, 99.0)

        slopes: List[float] = []
        for idx in range(1, len(points)):
            dlx = lxx[idx] - lxx[idx - 1]
            if abs(dlx) < 1e-9:
                continue
            slopes.append((lyy[idx] - lyy[idx - 1]) / dlx)

        return {
            "name": name,
            "v_range": [float(min(vx)), float(max(vx))],
            "delta_decades_robust": float(p99 - p1),
            "mean_slope_log_absI_per_logV": float(sum(slopes) / len(slopes) if slopes else 0.0),
        }

    return {
        "regimes": [
            summarize(low_pts, "low_|V|"),
            summarize(high_pts, "high_|V|"),
        ],
        "threshold": {"v_knee": float(v_split), "criterion": "percentile_split_30"},
    }


def _extract_observation_assumptions_from_json(parsed: Dict[str, Any], raw_text: str = "") -> List[Dict[str, Any]]:
    assumptions: List[Dict[str, Any]] = []
    pattern = str(parsed.get("pattern", "")).lower()
    keywords = parsed.get("keywords", [])

    kw_parts: List[str] = []
    if isinstance(keywords, list):
        for item in keywords:
            if isinstance(item, dict):
                kw_parts.append(str(item.get("keyword", "")))
                kw_parts.append(str(item.get("evidence", "")))
            else:
                kw_parts.append(str(item))

    blob = (pattern + "\n" + " ".join(kw_parts).lower() + "\n" + (raw_text or "").lower())
    registry = parsed.get("assumption_registry", {})
    if not isinstance(registry, dict):
        registry = {}

    def _lookup_assumption_card(assumption_id: str, fallback_statement: str, fallback_axis: List[str]) -> Dict[str, Any]:
        ref = registry.get(assumption_id)
        if isinstance(ref, dict):
            card = {
                "assumption_id": assumption_id,
                "statement": ref.get("statement", fallback_statement),
                "impact_axis": ref.get("impact_axis", fallback_axis),
            }
            for extra_key in ("severity", "source", "description", "description_ko", "note"):
                if extra_key in ref:
                    card[extra_key] = ref[extra_key]
            return card
        return {
            "assumption_id": assumption_id,
            "statement": fallback_statement,
            "impact_axis": fallback_axis,
        }

    if ("noise" in blob) or ("floor" in blob) or ("clamp" in blob) or ("limit" in blob):
        assumptions.append(
            _lookup_assumption_card(
                "A_MAG_NOISE",
                "Very small magnitudes may have been treated as near the measurement floor/noise level.",
                ["magnitude"],
            )
        )

    if ("threshold" in blob) or ("knee" in blob) or ("abrupt" in blob) or ("sharp" in blob):
        assumptions.append(
            _lookup_assumption_card(
                "A_SLOPE_ABRUPT",
                "A rapid change was flagged using a heuristic rate-of-change criterion.",
                ["slope"],
            )
        )

    dedup: Dict[str, Dict[str, Any]] = {}
    for assumption in assumptions:
        aid = assumption.get("assumption_id")
        if aid:
            dedup[aid] = assumption
    return list(dedup.values())


def _parse_llm_output(text: str) -> Dict[str, Any]:
    data = _safe_json_loads(text)
    if data is None:
        return {"pattern": "LLM 응답을 해석하지 못했습니다.", "keywords": [], "metrics": {}}

    pattern = _normalize_pattern_to_korean(str(data.get("pattern", "관측 패턴 요약이 제공되지 않았습니다.")).strip())
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
    try:
        obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
