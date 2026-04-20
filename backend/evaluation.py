from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


EVALUATION_FILE = "evaluation.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def round_score(value: float) -> float:
    return round(clamp(value), 3)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_json(path: Path, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback or {})


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _tokenize(text: str) -> List[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9가-힣_+-]+", str(text or "").lower())
    stopwords = {
        "the", "and", "that", "this", "with", "from", "into", "about", "have", "will", "should",
        "실험", "목적", "목표", "현재", "사용자", "기준", "설명", "분석", "결과", "하고", "있는", "으로", "에서",
        "하다", "있다", "그리고", "저런", "이런", "그런", "하기", "되는", "대한",
    }
    return [token for token in raw_tokens if len(token) >= 2 and token not in stopwords]


def _latest_assistant_text(chat_history: Sequence[Dict[str, Any]] | None) -> str:
    for item in reversed(list(chat_history or [])):
        if item.get("role") == "assistant":
            text = str(item.get("text") or "").strip()
            if text:
                return text
    return ""


def _normalize_fraction(num: float, den: float, default: float = 0.0) -> float:
    if den <= 0:
        return clamp(default)
    return clamp(num / den)


def _count_metric_fields(metrics: Dict[str, Any]) -> int:
    count = 0
    for key in (
        "absI_decades_span",
        "v_knee",
        "v_knee_criterion",
        "current_ratio",
        "rectification_ratio",
        "threshold_voltage",
        "turn_on_voltage",
    ):
        value = metrics.get(key)
        if value not in (None, "", []):
            count += 1
    return count


def _keywords_hit_count(text: str, keywords: Iterable[str]) -> int:
    lowered = str(text or "").lower()
    count = 0
    for keyword in keywords:
        token = str(keyword or "").strip().lower()
        if token and token in lowered:
            count += 1
    return count


def _score_ontology_reasoning(
    proposals: Sequence[Dict[str, Any]],
    measurement_validation: Dict[str, Any],
    assumption_states: Dict[str, Any],
) -> Dict[str, Any]:
    top = proposals[0] if proposals else {}
    second = proposals[1] if len(proposals) >= 2 else {}
    required_features = top.get("required_features", []) or []
    matched_features = top.get("matched_features", []) or []
    assumptions = top.get("sj_assumptions", []) or []
    warnings = measurement_validation.get("warnings", []) or []
    errors = measurement_validation.get("errors", []) or []
    top_score = _safe_float(top.get("score", 0.0))
    second_score = _safe_float(second.get("score", 0.0))

    if required_features:
        evidence_coverage = _normalize_fraction(len(matched_features), len(required_features), default=0.0)
    elif matched_features:
        evidence_coverage = 0.8
    else:
        evidence_coverage = 0.0

    ranking_margin = clamp((top_score - second_score) / max(top_score, 1.0)) if top else 0.0

    validation_cleanliness = 1.0
    validation_cleanliness -= min(len(warnings), 4) * 0.12
    validation_cleanliness -= min(len(errors), 3) * 0.22
    if measurement_validation.get("valid") is False:
        validation_cleanliness -= 0.1
    validation_cleanliness = clamp(validation_cleanliness)

    if not assumptions:
        assumption_compatibility = 0.72
    else:
        rejected = sum(1 for item in assumptions if assumption_states.get(item) == "rejected")
        confirmed = sum(1 for item in assumptions if assumption_states.get(item) == "confirmed")
        approved = sum(1 for item in assumptions if assumption_states.get(item) == "approved")
        assumption_compatibility = 0.65
        if rejected:
            assumption_compatibility -= 0.45 * _normalize_fraction(rejected, len(assumptions))
        assumption_compatibility += 0.2 * _normalize_fraction(confirmed, len(assumptions))
        assumption_compatibility += 0.25 * _normalize_fraction(approved, len(assumptions))
        assumption_compatibility = clamp(assumption_compatibility)

    score = (
        0.45 * evidence_coverage
        + 0.25 * ranking_margin
        + 0.2 * validation_cleanliness
        + 0.1 * assumption_compatibility
    )
    return {
        "score": round_score(score),
        "status": "available" if top else "no_proposal",
        "components": {
            "evidence_coverage": round_score(evidence_coverage),
            "ranking_margin": round_score(ranking_margin),
            "validation_cleanliness": round_score(validation_cleanliness),
            "assumption_compatibility": round_score(assumption_compatibility),
        },
        "reason": "Top ontology proposal support, competition margin, validation quality, and assumption fit.",
    }


def _score_llm_interpretation(
    llm_trace: Dict[str, Any],
    derived: Dict[str, Any],
    proposals: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    used_llm = bool(llm_trace.get("used_llm"))
    if not used_llm:
        return {
            "score": 0.0,
            "status": "unavailable",
            "components": {
                "structured_output": 0.0,
                "observation_density": 0.0,
                "proposal_support": 0.0,
            },
            "reason": "LLM observation path was not used; numeric fallback handled the run.",
        }

    pattern = str(derived.get("llm_pattern") or "").strip()
    metrics = derived.get("metrics", {}) or {}
    regimes = derived.get("regimes", []) or []
    keywords = derived.get("llm_keywords", []) or []

    structured_output = (
        0.3 * (1.0 if pattern else 0.0)
        + 0.25 * (1.0 if metrics else 0.0)
        + 0.2 * clamp(len(regimes) / 2.0)
        + 0.25 * clamp(len(keywords) / 4.0)
    )
    observation_density = (
        0.5 * clamp(_count_metric_fields(metrics) / 5.0)
        + 0.25 * clamp(len(regimes) / 2.0)
        + 0.25 * clamp(len(keywords) / 4.0)
    )
    proposal_support = 1.0 if proposals else 0.35

    score = 0.4 * structured_output + 0.35 * observation_density + 0.25 * proposal_support
    return {
        "score": round_score(score),
        "status": "available",
        "components": {
            "structured_output": round_score(structured_output),
            "observation_density": round_score(observation_density),
            "proposal_support": round_score(proposal_support),
        },
        "reason": "LLM confidence based on whether the LLM path ran and how complete the observation payload is.",
    }


def _score_intent_alignment(
    intent_profile: Dict[str, Any],
    proposals: Sequence[Dict[str, Any]],
    explanation_text: str,
) -> Dict[str, Any]:
    top = proposals[0] if proposals else {}
    top_claim = str(top.get("claim_concept") or "")
    focus_claims = set(intent_profile.get("focus_claims", []) or [])
    exclude_claims = set(intent_profile.get("exclude_claims", []) or [])
    confirmed_conditions = intent_profile.get("confirmed_conditions", {}) or {}
    analysis_priority = str(intent_profile.get("analysis_priority") or "")
    research_goal = str(intent_profile.get("research_goal") or "").strip()

    if top_claim and top_claim in exclude_claims:
        claim_alignment = 0.0
    elif focus_claims:
        claim_alignment = 1.0 if top_claim in focus_claims else 0.35
    else:
        claim_alignment = 0.78

    if not research_goal:
        goal_alignment = 0.75
    else:
        goal_tokens = _tokenize(research_goal)
        overlap = _keywords_hit_count(explanation_text, goal_tokens)
        goal_alignment = max(0.2, _normalize_fraction(overlap, max(1, min(len(goal_tokens), 4)), default=0.2))

    priority_keywords = {
        "mechanism_identification": ("메커니즘", "해석", "근거", "장벽", "transport"),
        "measurement_anomaly_diagnosis": ("warning", "artifact", "측정", "재현", "안정성"),
        "next_experiment_planning": ("다음 실험", "비교", "변수", "split", "확인"),
    }
    if analysis_priority:
        hits = _keywords_hit_count(explanation_text, priority_keywords.get(analysis_priority, ()))
        priority_alignment = max(0.2, clamp(hits / 2.0))
    else:
        priority_alignment = 0.72

    condition_hits = _keywords_hit_count(explanation_text, confirmed_conditions.values())
    condition_alignment = 0.7 if not confirmed_conditions else max(
        0.25,
        _normalize_fraction(condition_hits, max(1, min(len(confirmed_conditions), 3)), default=0.25),
    )

    score = (
        0.35 * claim_alignment
        + 0.3 * goal_alignment
        + 0.2 * priority_alignment
        + 0.15 * condition_alignment
    )
    return {
        "score": round_score(score),
        "status": "available",
        "components": {
            "claim_alignment": round_score(claim_alignment),
            "goal_alignment": round_score(goal_alignment),
            "priority_alignment": round_score(priority_alignment),
            "condition_alignment": round_score(condition_alignment),
        },
        "reason": "Measures whether the answer follows user goals, preferred claims, and current analysis priority.",
    }


def _score_explanation_quality(
    explanation_text: str,
    proposals: Sequence[Dict[str, Any]],
    measurement_validation: Dict[str, Any],
) -> Dict[str, Any]:
    text = str(explanation_text or "").strip()
    if not text:
        return {
            "score": 0.0,
            "status": "missing_text",
            "components": {
                "specificity": 0.0,
                "evidence_reference": 0.0,
                "structure": 0.0,
                "readability": 0.0,
            },
            "reason": "No narrative or answer text was available to evaluate.",
        }

    top = proposals[0] if proposals else {}
    matched = [str(item) for item in (top.get("matched_features", []) or [])]
    required = [str(item) for item in (top.get("required_features", []) or [])]
    sentence_count = max(1, len(re.findall(r"[.!?]|[다요]\s", text)))
    digits_present = bool(re.search(r"\d", text))
    evidence_hits = _keywords_hit_count(text, matched + required + ["warning", "slope", "knee", "온도", "전압", "전류"])
    uncertainty_hits = _keywords_hit_count(text, ("불확실", "다만", "추가", "확인", "안전", "uncertain"))
    ontology_id_like = len(re.findall(r"\b(?:iv_|physical_assumption|measurement_conditions|iv_features)\S*", text))

    specificity = clamp(min(len(text), 1200) / 650.0)
    evidence_reference = (
        0.55 * (1.0 if digits_present else 0.0)
        + 0.45 * clamp(evidence_hits / 4.0)
    )
    structure = (
        0.5 * clamp(sentence_count / 4.0)
        + 0.5 * (1.0 if uncertainty_hits else 0.45)
    )
    readability = clamp(1.0 - min(ontology_id_like, 4) * 0.18)

    if measurement_validation.get("warnings"):
        structure = clamp(structure + 0.05)

    score = (
        0.3 * specificity
        + 0.3 * evidence_reference
        + 0.2 * structure
        + 0.2 * readability
    )
    return {
        "score": round_score(score),
        "status": "available",
        "components": {
            "specificity": round_score(specificity),
            "evidence_reference": round_score(evidence_reference),
            "structure": round_score(structure),
            "readability": round_score(readability),
        },
        "reason": "Checks whether the explanation is specific, evidence-grounded, structured, and readable.",
    }


def _load_prior_top_claims(run_dir: Path, domain: str) -> List[str]:
    sibling_dir = run_dir.parent
    if not sibling_dir.is_dir():
        return []

    paths = [path for path in sibling_dir.iterdir() if path.is_dir() and path.name != run_dir.name]
    paths.sort(key=lambda path: path.name, reverse=True)
    claims: List[str] = []
    for path in paths[:6]:
        manifest = _load_json(path / "manifest.json")
        if domain and manifest.get("domain") not in (None, "", domain):
            # Older manifests may not include domain, so allow empty.
            pass
        inference = _load_json(path / "inference.json")
        proposals = inference.get("sj_proposals", []) or []
        if proposals:
            claim = str((proposals[0] or {}).get("claim_concept") or "").strip()
            if claim:
                claims.append(claim)
    return claims


def _score_cross_run_stability(run_dir: Path, proposals: Sequence[Dict[str, Any]], domain: str) -> Dict[str, Any]:
    top_claim = str((proposals[0] or {}).get("claim_concept") or "").strip() if proposals else ""
    prior_claims = _load_prior_top_claims(run_dir, domain)
    if not top_claim:
        return {
            "score": 0.0,
            "status": "no_top_claim",
            "components": {
                "claim_consistency": 0.0,
                "sample_size_factor": 0.0,
            },
            "reason": "No top claim is available for cross-run comparison.",
        }
    if not prior_claims:
        return {
            "score": 0.5,
            "status": "limited_context",
            "components": {
                "claim_consistency": 0.5,
                "sample_size_factor": 0.0,
            },
            "reason": "No prior comparable runs were found; defaulting to neutral stability.",
        }

    same_count = sum(1 for claim in prior_claims if claim == top_claim)
    consistency = _normalize_fraction(same_count, len(prior_claims), default=0.5)
    sample_size_factor = clamp(len(prior_claims) / 5.0)
    score = 0.75 * consistency + 0.25 * sample_size_factor
    return {
        "score": round_score(score),
        "status": "available",
        "components": {
            "claim_consistency": round_score(consistency),
            "sample_size_factor": round_score(sample_size_factor),
        },
        "reason": "Measures how stable the top claim is across recent sibling runs.",
    }


def evaluate_run(
    run_dir: Path,
    *,
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: Sequence[Dict[str, Any]],
    system_narrative: str,
    llm_trace: Dict[str, Any],
    derived: Dict[str, Any],
    domain: str = "iv",
    chat_history: Sequence[Dict[str, Any]] | None = None,
    latest_assistant_text: str = "",
) -> Dict[str, Any]:
    measurement_validation = snapshot.get("measurement_validation", {}) or {}
    assumption_states = intent_profile.get("assumption_states", {}) or {}
    explanation_text = str(latest_assistant_text or _latest_assistant_text(chat_history) or system_narrative or "").strip()

    ontology = _score_ontology_reasoning(reranked_proposals, measurement_validation, assumption_states)
    llm = _score_llm_interpretation(llm_trace, derived, reranked_proposals)
    intent = _score_intent_alignment(intent_profile, reranked_proposals, explanation_text)
    explanation = _score_explanation_quality(explanation_text, reranked_proposals, measurement_validation)
    stability = _score_cross_run_stability(run_dir, reranked_proposals, domain)

    categories = {
        "ontology_reasoning_confidence": ontology,
        "llm_interpretation_confidence": llm,
        "intent_alignment_score": intent,
        "explanation_quality_score": explanation,
        "cross_run_stability_score": stability,
    }

    weights = {
        "ontology_reasoning_confidence": 0.32,
        "llm_interpretation_confidence": 0.16,
        "intent_alignment_score": 0.2,
        "explanation_quality_score": 0.2,
        "cross_run_stability_score": 0.12,
    }

    numerator = 0.0
    denominator = 0.0
    for key, entry in categories.items():
        if entry.get("status") == "unavailable":
            continue
        weight = weights[key]
        numerator += weight * _safe_float(entry.get("score", 0.0))
        denominator += weight
    overall = round_score(numerator / denominator) if denominator else 0.0

    payload = {
        "run_id": run_dir.name,
        "generated_at_utc": utc_now_iso(),
        "domain": domain,
        "overall_confidence": overall,
        "score_order": list(weights.keys()),
        "categories": categories,
        "summary": {
            "ontology_reasoning_confidence": ontology.get("score", 0.0),
            "llm_interpretation_confidence": llm.get("score", 0.0),
            "intent_alignment_score": intent.get("score", 0.0),
            "explanation_quality_score": explanation.get("score", 0.0),
            "cross_run_stability_score": stability.get("score", 0.0),
        },
    }
    return payload


def save_evaluation(run_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    _write_json(run_dir / EVALUATION_FILE, payload)
    return payload


def load_evaluation(run_dir: Path) -> Dict[str, Any]:
    return _load_json(run_dir / EVALUATION_FILE, fallback={})
