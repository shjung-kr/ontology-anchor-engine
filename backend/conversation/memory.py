"""
Run-scoped conversational memory, strict Q/A handling, and curated overlay helpers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from backend.conversation.models import ChatTurnRequest, DomainChatQuestion, IntentUpdate, StructuredAnswer
from backend.domains.iv.common import (
    format_confirmed_conditions_ko,
    join_term_labels,
    term_description,
    term_label,
)
from backend.llm_adapter import answer_with_analysis_context


RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"
OVERLAY_DIR = Path(__file__).resolve().parents[1] / "ontology_overlays"
CURATED_OVERLAY_PATH = OVERLAY_DIR / "iv_user_overlay.json"
REVIEW_QUEUE_PATH = OVERLAY_DIR / "iv_review_queue.json"
REVIEW_STATE_PATH = OVERLAY_DIR / "iv_review_state.json"
CANDIDATE_HYPOTHESES_FILE = "candidate_hypotheses.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_run_dir(run_id: str) -> Path:
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"unknown run_id: {run_id}")
    return run_dir


def default_intent_profile(run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "analysis_priority": None,
        "focus_claims": [],
        "exclude_claims": [],
        "keep_open_claims": [],
        "confirmed_conditions": {},
        "uncertain_conditions": [],
        "assumption_states": {},
        "approved_patch_items": {
            "claims": [],
            "assumptions": [],
            "measurement_conditions": [],
        },
        "notes": [],
        "history": [],
        "updated_at_utc": utc_now_iso(),
    }


def default_patch_payload(run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "candidate_overlay",
        "generated_at_utc": utc_now_iso(),
        "claims": [],
        "assumptions": [],
        "measurement_conditions": [],
    }


def default_candidate_hypotheses(run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at_utc": utc_now_iso(),
        "coverage_status": "unknown",
        "items": [],
    }


def default_curated_overlay() -> Dict[str, Any]:
    return {
        "overlay_id": "iv_user_overlay",
        "domain": "iv",
        "generated_at_utc": utc_now_iso(),
        "claims": [],
        "assumptions": [],
        "measurement_conditions": [],
    }


def default_review_queue() -> Dict[str, Any]:
    return {
        "queue_id": "iv_review_queue",
        "domain": "iv",
        "generated_at_utc": utc_now_iso(),
        "items": [],
    }


def default_review_state() -> Dict[str, Any]:
    return {
        "review_id": "iv_review_state",
        "domain": "iv",
        "updated_at_utc": utc_now_iso(),
        "items": [],
    }


def ensure_memory_files(run_dir: Path) -> None:
    run_id = run_dir.name
    chat_path = run_dir / "chat_history.jsonl"
    intent_path = run_dir / "intent_profile.json"
    patch_path = run_dir / "ontology_patch.json"
    candidate_path = run_dir / CANDIDATE_HYPOTHESES_FILE

    if not chat_path.exists():
        chat_path.write_text("", encoding="utf-8")
    if not intent_path.exists():
        write_json(intent_path, default_intent_profile(run_id))
    if not patch_path.exists():
        write_json(patch_path, default_patch_payload(run_id))
    if not candidate_path.exists():
        write_json(candidate_path, default_candidate_hypotheses(run_id))


def load_json(path: Path, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback or {})


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_chat_event(run_dir: Path, event: Dict[str, Any]) -> None:
    ensure_memory_files(run_dir)
    path = run_dir / "chat_history.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_chat_history(run_dir: Path) -> List[Dict[str, Any]]:
    ensure_memory_files(run_dir)
    path = run_dir / "chat_history.jsonl"
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def build_run_summary(run_dir: Path) -> Dict[str, Any]:
    ensure_memory_files(run_dir)
    manifest = load_json(run_dir / "manifest.json")
    chat_state = build_chat_response(run_dir)
    snapshot = load_analysis_snapshot(run_dir)
    reranked = chat_state.get("reranked_sj_proposals", []) or []
    top = reranked[0] if reranked else {}
    validation = snapshot.get("measurement_validation", {}) or {}
    return {
        "run_id": run_dir.name,
        "created_at_utc": manifest.get("created_at_utc"),
        "domain": (chat_state.get("curated_overlay", {}) or {}).get("domain") or "iv",
        "coverage_status": (chat_state.get("coverage_assessment", {}) or {}).get("status", "unknown"),
        "top_claim": top.get("claim_concept"),
        "fallback_status": (chat_state.get("exploratory_fallback", {}) or {}).get("status", "unknown"),
        "warning_count": len(validation.get("warnings", []) or []),
        "candidate_count": len((chat_state.get("candidate_hypotheses", {}) or {}).get("items", []) or []),
        "patch_counts": {
            "claims": len((chat_state.get("ontology_patch", {}) or {}).get("claims", []) or []),
            "assumptions": len((chat_state.get("ontology_patch", {}) or {}).get("assumptions", []) or []),
            "measurement_conditions": len((chat_state.get("ontology_patch", {}) or {}).get("measurement_conditions", []) or []),
        },
    }


def list_run_summaries(limit: int = 50) -> List[Dict[str, Any]]:
    run_dirs = [path for path in RUNS_DIR.iterdir() if path.is_dir()]
    run_dirs.sort(key=lambda path: path.name, reverse=True)
    summaries: List[Dict[str, Any]] = []
    for run_dir in run_dirs[: max(1, limit)]:
        try:
            summaries.append(build_run_summary(run_dir))
        except Exception:
            continue
    return summaries


def compare_runs(left_run_dir: Path, right_run_dir: Path) -> Dict[str, Any]:
    left_summary = build_run_summary(left_run_dir)
    right_summary = build_run_summary(right_run_dir)
    left_state = build_chat_response(left_run_dir)
    right_state = build_chat_response(right_run_dir)

    left_conditions = ((left_state.get("intent_profile", {}) or {}).get("confirmed_conditions", {}) or {})
    right_conditions = ((right_state.get("intent_profile", {}) or {}).get("confirmed_conditions", {}) or {})

    changed_items: List[Dict[str, Any]] = []
    shared_items: List[Dict[str, Any]] = []

    def compare_field(label: str, left_value: Any, right_value: Any) -> None:
        if left_value == right_value:
            shared_items.append({"field": label, "value": left_value})
        else:
            changed_items.append({"field": label, "left": left_value, "right": right_value})

    compare_field("coverage_status", left_summary.get("coverage_status"), right_summary.get("coverage_status"))
    compare_field("top_claim", left_summary.get("top_claim"), right_summary.get("top_claim"))
    compare_field("fallback_status", left_summary.get("fallback_status"), right_summary.get("fallback_status"))
    compare_field("confirmed_conditions", left_conditions, right_conditions)

    left_hypotheses = [item.get("label") for item in (left_state.get("candidate_hypotheses", {}) or {}).get("items", []) if isinstance(item, dict)]
    right_hypotheses = [item.get("label") for item in (right_state.get("candidate_hypotheses", {}) or {}).get("items", []) if isinstance(item, dict)]
    compare_field("candidate_hypotheses", left_hypotheses, right_hypotheses)

    left_ideas = [item.get("title") for item in (left_state.get("exploratory_fallback", {}) or {}).get("experiment_ideas", []) if isinstance(item, dict)]
    right_ideas = [item.get("title") for item in (right_state.get("exploratory_fallback", {}) or {}).get("experiment_ideas", []) if isinstance(item, dict)]

    return {
        "left_run": left_summary,
        "right_run": right_summary,
        "shared_items": shared_items,
        "changed_items": changed_items,
        "left_only": {
            "candidate_hypotheses": [item for item in left_hypotheses if item not in set(right_hypotheses)],
            "experiment_ideas": [item for item in left_ideas if item not in set(right_ideas)],
        },
        "right_only": {
            "candidate_hypotheses": [item for item in right_hypotheses if item not in set(left_hypotheses)],
            "experiment_ideas": [item for item in right_ideas if item not in set(left_ideas)],
        },
        "experiment_idea_diff": {
            "left": left_ideas,
            "right": right_ideas,
        },
    }


def sync_suggested_questions(run_dir: Path, suggested_questions: List[Dict[str, Any]]) -> None:
    existing = load_chat_history(run_dir)
    existing_keys = {
        (
            item.get("question_id"),
            item.get("role"),
            item.get("type"),
        )
        for item in existing
        if isinstance(item, dict)
    }

    for question in suggested_questions:
        key = (
            question.get("question_id"),
            "assistant",
            "question",
        )
        if key in existing_keys:
            continue
        append_chat_event(
            run_dir,
            {
                "timestamp_utc": utc_now_iso(),
                "role": "assistant",
                "type": "question",
                "question_id": question.get("question_id"),
                "text": question.get("prompt", ""),
                "category": question.get("category"),
                "target_ids": question.get("target_ids", []),
            },
        )
        existing_keys.add(key)


def load_analysis_snapshot(run_dir: Path) -> Dict[str, Any]:
    inference = load_json(run_dir / "inference.json")
    derived = load_json(run_dir / "derived.json")
    if not inference and not derived:
        result = load_json(run_dir / "result.json")
        return {
            "measurement_validation": result.get("measurement_validation", {}),
            "l1_state": result.get("l1_state", {}),
            "assumptions": {
                "assumptions": result.get("assumptions", []),
                "assumption_ids": result.get("assumption_ids", []),
                "assumptions_meta": result.get("assumptions_meta", {}),
            },
            "sj_proposals": result.get("sj_proposals", []),
            "llm_pattern": "",
            "metrics": result.get("metrics", {}),
            "regimes": [],
        }
    return {
        "measurement_validation": inference.get("measurement_validation", {}),
        "l1_state": inference.get("l1_state", {}),
        "assumptions": inference.get("assumptions", {}),
        "sj_proposals": inference.get("sj_proposals", []),
        "llm_pattern": derived.get("llm_pattern", ""),
        "metrics": derived.get("metrics", {}),
        "regimes": derived.get("regimes", []),
    }


def load_intent_profile(run_dir: Path) -> Dict[str, Any]:
    ensure_memory_files(run_dir)
    return load_json(run_dir / "intent_profile.json", fallback=default_intent_profile(run_dir.name))


def load_candidate_hypotheses(run_dir: Path) -> Dict[str, Any]:
    ensure_memory_files(run_dir)
    return load_json(run_dir / CANDIDATE_HYPOTHESES_FILE, fallback=default_candidate_hypotheses(run_dir.name))


def load_curated_overlay() -> Dict[str, Any]:
    return load_json(CURATED_OVERLAY_PATH, fallback=default_curated_overlay())


def load_review_queue() -> Dict[str, Any]:
    return load_json(REVIEW_QUEUE_PATH, fallback=default_review_queue())


def load_review_state() -> Dict[str, Any]:
    return load_json(REVIEW_STATE_PATH, fallback=default_review_state())


def _merge_unique(existing: Iterable[str], new_items: Iterable[str]) -> List[str]:
    seen = set()
    merged: List[str] = []
    for item in list(existing) + list(new_items):
        if not isinstance(item, str) or not item.strip() or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _remove_values(existing: Iterable[str], removed: Iterable[str]) -> List[str]:
    removed_set = {item for item in removed if isinstance(item, str)}
    return [item for item in existing if item not in removed_set]


def _normalize_text_detail(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def infer_structured_context_from_text(user_text: str) -> Dict[str, Any]:
    text = (user_text or "").strip()
    lowered = text.lower()
    conditions: Dict[str, Any] = {}

    if any(token in lowered for token in ("pulse", "pulsed", "펄스")):
        conditions["measurement_setup"] = "pulsed_bias"
    elif any(token in lowered for token in ("dc", "steady-state", "steady state", "직류")):
        conditions["measurement_setup"] = "steady_state_dc"

    if any(token in lowered for token in ("repeat", "reproduc", "재현", "반복 측정")):
        if any(token in lowered for token in ("not", "fail", "안", "불", "no")):
            conditions["reproducibility"] = "not_reproducible"
        else:
            conditions["reproducibility"] = "reproducible"

    if any(token in lowered for token in ("electrode", "au", "ag", "pt", "전극")):
        conditions["device_context"] = text
    if any(token in lowered for token in ("thickness", "nm", "두께", "oxide", "barrier", "절연층")):
        conditions["stack_or_thickness"] = text
    if any(token in lowered for token in ("sweep direction", "forward", "reverse", "hysteresis", "스윕", "히스테리시스")):
        conditions["sweep_context"] = text

    return conditions


def infer_intent_from_text(user_text: str) -> Dict[str, Any]:
    text = (user_text or "").lower()
    inferred: Dict[str, Any] = {}
    if any(
        phrase in text
        for phrase in (
            "next experiment",
            "follow-up experiment",
            "plan the next experiment",
            "다음 실험",
            "후속 실험",
            "실험 계획",
            "다음 실험 설계",
        )
    ):
        inferred["analysis_priority"] = "next_experiment_planning"
    elif any(
        phrase in text
        for phrase in (
            "anomaly",
            "artifact",
            "measurement issue",
            "diagnos",
            "이상",
            "아티팩트",
            "측정 문제",
            "오류 원인",
            "진단",
        )
    ):
        inferred["analysis_priority"] = "measurement_anomaly_diagnosis"
    elif any(
        phrase in text
        for phrase in (
            "mechanism",
            "identify the mechanism",
            "transport model",
            "메커니즘",
            "기구",
            "전도 메커니즘",
            "해석",
        )
    ):
        inferred["analysis_priority"] = "mechanism_identification"

    if (
        ("room temperature" in text or "상온" in text or "실온" in text)
        and any(word in text for word in ("confirmed", "yes", "is", "was", "measured at", "확인", "맞", "이다", "측정"))
    ):
        inferred.setdefault("confirmed_conditions", {})["temperature"] = "room_temperature"
    elif ("temperature" in text or "온도" in text) and any(word in text for word in ("uncertain", "unknown", "not sure", "불확실", "모름", "잘 모르")):
        inferred["uncertain_conditions"] = ["temperature"]

    focus_claims: List[str] = []
    exclude_claims: List[str] = []

    if any(term in text for term in ("fn tunneling", "fowler-nordheim", "포울러", "fn 터널링", "터널링")) and any(
        term in text for term in ("우선", "집중", "focus", "prioritize", "main", "주로")
    ):
        focus_claims.append("iv_interpretation.fn_tunneling_asserted")

    if any(term in text for term in ("ohmic", "옴", "ohmic transport")) and any(
        term in text for term in ("우선", "집중", "focus", "prioritize", "main", "주로")
    ):
        focus_claims.append("iv_interpretation.ohmic_transport_asserted")

    if any(term in text for term in ("self-heating", "자가발열", "자기발열", "heating")) and any(
        term in text for term in ("exclude", "deprioritize", "빼", "배제", "제외", "보류")
    ):
        exclude_claims.append("iv_interpretation.self_heating_artifact")

    if any(term in text for term in ("fn tunneling", "fowler-nordheim", "포울러", "fn 터널링", "터널링")) and any(
        term in text for term in ("exclude", "deprioritize", "빼", "배제", "제외")
    ):
        exclude_claims.append("iv_interpretation.fn_tunneling_asserted")

    if focus_claims:
        inferred["focus_claims"] = _merge_unique([], focus_claims)
    if exclude_claims:
        inferred["exclude_claims"] = _merge_unique([], exclude_claims)
    return inferred


def infer_contextual_intent_from_text(user_text: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    text = (user_text or "").lower()
    inferred: Dict[str, Any] = {}

    top = (snapshot.get("sj_proposals", []) or [{}])[0] if snapshot.get("sj_proposals") else {}
    top_assumptions = [item for item in (top.get("sj_assumptions", []) or []) if isinstance(item, str)]

    numbered_map = {
        "1": top_assumptions[0] if len(top_assumptions) >= 1 else None,
        "2": top_assumptions[1] if len(top_assumptions) >= 2 else None,
        "3": top_assumptions[2] if len(top_assumptions) >= 3 else None,
        "4": top_assumptions[3] if len(top_assumptions) >= 4 else None,
    }

    selected_assumptions: List[str] = []
    if any(token in text for token in ("가정 1", "1번 가정", "assumption 1", "assumption #1")) and numbered_map.get("1"):
        selected_assumptions.append(numbered_map["1"])
    if any(token in text for token in ("가정 2", "2번 가정", "assumption 2", "assumption #2")) and numbered_map.get("2"):
        selected_assumptions.append(numbered_map["2"])
    if any(token in text for token in ("가정 3", "3번 가정", "assumption 3", "assumption #3")) and numbered_map.get("3"):
        selected_assumptions.append(numbered_map["3"])
    if any(token in text for token in ("가정 4", "4번 가정", "assumption 4", "assumption #4")) and numbered_map.get("4"):
        selected_assumptions.append(numbered_map["4"])

    if any(token in text for token in ("가정 1,2", "가정1,2", "1,2번 가정", "가정 1번과 2번", "가정 1과 2")):
        selected_assumptions = [item for item in [numbered_map.get("1"), numbered_map.get("2")] if item]
    if any(token in text for token in ("가정 모두", "모든 가정", "all assumptions", "가정 전부")):
        selected_assumptions = top_assumptions[:4]

    selected_assumptions = _merge_unique([], selected_assumptions)
    if selected_assumptions:
        if any(token in text for token in ("인정", "확인", "동의", "accept", "confirm", "agree")):
            inferred["confirmed_assumptions"] = selected_assumptions
        if any(token in text for token in ("승인", "approve")):
            inferred["approved_assumptions"] = selected_assumptions
        if any(token in text for token in ("배제", "제외", "기각", "reject", "빼")):
            inferred["rejected_assumptions"] = selected_assumptions

    return inferred


def classify_user_message(user_text: str, structured_answers: List[StructuredAnswer]) -> str:
    text = (user_text or "").strip().lower()
    if structured_answers and not text:
        return "intent_update"
    if any(token in text for token in ("?", "어떻게", "왜", "무엇", "뭐", "가능", "어떤", "how", "why", "what", "which", "should")):
        return "direct_question"
    if len(text) >= 8 and any(token in text for token in ("해주세요", "알려", "설명", "추천", "제안", "보고 싶", "궁금")):
        return "direct_question"
    return "intent_update"


def classify_direct_question(user_text: str) -> str:
    text = (user_text or "").strip().lower()
    if not text:
        return "generic_summary"

    if any(token in text for token in ("턴온", "turn-on", "turn on")):
        if any(token in text for token in ("낮추", "줄이", "decrease", "lower", "reduce")):
            return "turn_on_reduction"
        if any(token in text for token in ("왜", "이유", "원인", "cause", "reason")):
            return "turn_on_cause"
        return "turn_on_meaning"

    if any(token in text for token in ("다음 실험", "후속 실험", "추천", "next experiment")):
        return "next_experiment"

    if any(token in text for token in ("가정", "assumption")):
        return "assumption_check"

    if any(token in text for token in ("왜", "이유", "근거", "why", "reason", "basis")):
        return "mechanism_why"

    if any(token in text for token in ("무슨 뜻", "의미", "meaning", "what does")):
        return "meaning_explanation"

    return "generic_summary"


def _build_answer_context(
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    top = reranked_proposals[0] if reranked_proposals else {}
    claim_id = str(top.get("claim_concept") or "")
    return {
        "top": top,
        "claim_id": claim_id,
        "claim_label": term_label(claim_id) if claim_id else "해석 후보 없음",
        "final_score": top.get("final_score", top.get("score")),
        "coverage": assess_ontology_coverage(snapshot, reranked_proposals),
        "confirmed_conditions": intent_profile.get("confirmed_conditions", {}) or {},
        "assumptions": top.get("sj_assumptions", []) or [],
        "required_features": top.get("required_features", []) or [],
        "matched": top.get("matched_features", []) or [],
        "warnings": snapshot.get("measurement_validation", {}).get("warnings", []) or [],
    }


def _append_common_caveats(answer_lines: List[str], context: Dict[str, Any], question_type: str) -> None:
    coverage = context.get("coverage", {}) or {}
    confirmed_conditions = context.get("confirmed_conditions", {}) or {}
    warnings = context.get("warnings", []) or []
    assumptions = context.get("assumptions", []) or []

    if coverage.get("status") != "sufficient":
        answer_lines.append("다만 현재 근거는 확정 결론이라기보다 탐색형 해석으로 보는 편이 안전합니다.")
    if question_type in {"mechanism_why", "generic_summary", "assumption_check"} and confirmed_conditions:
        answer_lines.append(f"현재 확인된 조건은 다음과 같습니다: {format_confirmed_conditions_ko(confirmed_conditions)}.")
    if warnings and question_type not in {"next_experiment"}:
        answer_lines.append(f"또한 validation warning이 {len(warnings)}건 있어 측정 조건 점검도 병행하는 편이 좋습니다.")
    if assumptions and question_type in {"mechanism_why", "generic_summary", "assumption_check"}:
        answer_lines.append(f"확인 또는 배제가 필요한 대표 가정은 {join_term_labels(assumptions, max_items=2)} 입니다.")


def _render_turn_on_cause_answer(context: Dict[str, Any]) -> str:
    matched = context.get("matched", []) or []
    assumptions = context.get("assumptions", []) or []
    claim = context.get("claim_label") or "현재 상위 해석"
    lines = [
        "턴온 전압이 왜 그렇게 보이는지를 묻는 질문이라면, 지금은 메커니즘 이름보다 초기 전류 주입이 왜 늦게 시작되는지를 봐야 합니다.",
        "현재 run에서는 비선형 I-V와 전계 강화 전류가 보여서, 낮은 전압에서는 전류가 잘 안 흐르다가 특정 전압 이상에서 급격히 커지는 장벽 지배 거동 가능성을 먼저 의심하게 됩니다.",
    ]
    if matched:
        lines.append(f"이 판단의 직접 근거는 {join_term_labels(matched)} 입니다.")
    if "physical_assumption.effective_potential_barrier_present" in set(assumptions):
        lines.append("즉 턴온이 높게 보인다면 유효 장벽의 높이 또는 두께, 계면 상태, 전극과의 일함수 차이 같은 요소가 원인일 가능성이 큽니다.")
    else:
        lines.append("다만 현재 데이터만으로는 장벽 효과와 측정 조건 영향을 완전히 분리하긴 어렵습니다.")
    lines.append(f"현재 최상위 해석이 {claim}인 것도, 이런 고전계 이후 급격한 전류 증가 패턴과 잘 맞기 때문입니다.")
    _append_common_caveats(lines, context, "turn_on_cause")
    return "\n".join(lines)


def _render_turn_on_reduction_answer(context: Dict[str, Any]) -> str:
    lines = [
        "턴온 전압을 낮추려면 초기 전류 주입을 막는 요인을 줄이는 방향으로 접근하는 것이 맞습니다.",
        "우선적으로 볼 변수는 장벽 높이, 유효 절연층 두께, 계면 trap/defect 상태, 전극 물질 조합입니다.",
        "실험적으로는 전극 변경, 절연층 두께 split, 계면 처리 전후 비교를 먼저 하는 것이 효율적입니다.",
    ]
    required_features = context.get("required_features", []) or []
    if required_features:
        lines.append(f"현재 상위 해석과 연결된 핵심 관측 feature는 {join_term_labels(required_features)} 이므로, 위 변수들을 바꿨을 때 그 패턴이 어떻게 이동하는지 같이 봐야 합니다.")
    _append_common_caveats(lines, context, "turn_on_reduction")
    return "\n".join(lines)


def _render_turn_on_meaning_answer(context: Dict[str, Any]) -> str:
    lines = [
        "턴온 전압은 전류가 눈에 띄게 증가하기 시작하는 기준 전압으로 이해하면 됩니다.",
        "물리적으로는 그 전압 이하에서는 전하 주입이나 이동이 억제되어 있다가, 그 이상에서 장벽을 넘거나 터널링/주입이 쉬워지면서 전류가 급격히 커진다는 뜻으로 읽습니다.",
        "그래서 턴온 전압 질문은 단순한 수치 하나보다 장벽, 계면, 두께, 전극 조건과 함께 해석해야 의미가 있습니다.",
    ]
    _append_common_caveats(lines, context, "turn_on_meaning")
    return "\n".join(lines)


def _render_mechanism_why_answer(context: Dict[str, Any]) -> str:
    claim = context.get("claim_label") or "해석 후보 없음"
    final_score = context.get("final_score")
    matched = context.get("matched", []) or []
    assumptions = context.get("assumptions", []) or []
    lines = [f"현재 run 기준 최상위 해석은 {claim}이고 score는 {final_score} 입니다."]
    if matched:
        lines.append(f"이 해석이 올라온 직접 근거는 {join_term_labels(matched)} 입니다.")
    if assumptions:
        lines.append(f"다만 이 해석은 {join_term_labels(assumptions, max_items=3)} 같은 가정이 성립할 때 더 설득력이 생깁니다.")
    _append_common_caveats(lines, context, "mechanism_why")
    return "\n".join(lines)


def _render_meaning_explanation_answer(context: Dict[str, Any]) -> str:
    matched = context.get("matched", []) or []
    lines = []
    if matched:
        lines.append(f"지금 중요하게 본 관측은 {join_term_labels(matched)} 입니다.")
        detailed_feature_lines = []
        for feature_id in matched[:2]:
            description = term_description(str(feature_id))
            if description:
                detailed_feature_lines.append(description)
        if detailed_feature_lines:
            lines.append("쉽게 풀면, 현재 데이터에서는 " + " ".join(detailed_feature_lines))
    else:
        lines.append("현재 run에서 의미를 풀어 설명할 만한 핵심 feature가 아직 충분히 정리되지 않았습니다.")
    _append_common_caveats(lines, context, "meaning_explanation")
    return "\n".join(lines)


def _render_assumption_check_answer(context: Dict[str, Any]) -> str:
    assumptions = context.get("assumptions", []) or []
    if not assumptions:
        return "현재 상위 해석에 대해 별도로 확인이 필요한 대표 가정이 두드러지지 않습니다."

    lines = ["현재 해석이 유지되려면 다음 가정들이 중요합니다."]
    for assumption_id in assumptions[:2]:
        label = term_label(str(assumption_id))
        description = term_description(str(assumption_id))
        lines.append(f"- {label}: {description or '설명 정보 없음'}")
    _append_common_caveats(lines, context, "assumption_check")
    return "\n".join(lines)


def _render_next_experiment_answer(context: Dict[str, Any]) -> str:
    required_features = context.get("required_features", []) or []
    lines = [
        "다음 실험은 현재 상위 가설을 가장 잘 흔들거나 지지할 수 있는 변수부터 바꾸는 것이 좋습니다.",
        "우선순위는 온도 의존성 확인, sweep mode(DC/pulse) 비교, 전극 또는 절연층 두께 split입니다.",
    ]
    if required_features:
        lines.append(f"특히 {join_term_labels(required_features)} 같은 핵심 feature가 조건 변화에 따라 유지되는지 확인하는 것이 중요합니다.")
    _append_common_caveats(lines, context, "next_experiment")
    return "\n".join(lines)


def _render_generic_summary_answer(context: Dict[str, Any]) -> str:
    claim = context.get("claim_label") or "해석 후보 없음"
    final_score = context.get("final_score")
    matched = context.get("matched", []) or []
    lines = [f"현재 run 기준 최상위 해석은 {claim}이고 score는 {final_score} 입니다."]
    if matched:
        lines.append(f"현재 답변은 상위 해석과 일치하는 관측 feature인 {join_term_labels(matched)}을 기준으로 구성했습니다.")
    _append_common_caveats(lines, context, "generic_summary")
    return "\n".join(lines)


def build_direct_answer(
    user_text: str,
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
    chat_history: List[Dict[str, Any]] | None = None,
    run_dir: Path | None = None,
    prefer_llm: bool = True,
) -> str:
    text = (user_text or "").strip()
    if not text:
        return ""
    if prefer_llm:
        llm_result = answer_with_analysis_context(
            user_text=text,
            snapshot=snapshot,
            intent_profile=intent_profile,
            reranked_proposals=reranked_proposals,
            chat_history=chat_history,
            run_dir=run_dir,
        )
        if llm_result.get("used_llm") and llm_result.get("answer"):
            return str(llm_result["answer"]).strip()
    question_type = classify_direct_question(text)
    context = _build_answer_context(snapshot, intent_profile, reranked_proposals)

    if question_type == "turn_on_cause":
        return _render_turn_on_cause_answer(context)
    if question_type == "turn_on_reduction":
        return _render_turn_on_reduction_answer(context)
    if question_type == "turn_on_meaning":
        return _render_turn_on_meaning_answer(context)
    if question_type == "next_experiment":
        return _render_next_experiment_answer(context)
    if question_type == "assumption_check":
        return _render_assumption_check_answer(context)
    if question_type == "mechanism_why":
        return _render_mechanism_why_answer(context)
    if question_type == "meaning_explanation":
        return _render_meaning_explanation_answer(context)
    return _render_generic_summary_answer(context)


def assess_ontology_coverage(snapshot: Dict[str, Any], proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    proposal_count = len(proposals or [])
    top_score = 0.0
    second_score = 0.0
    if proposal_count >= 1:
        try:
            top_score = float((proposals or [{}])[0].get("score", 0.0) or 0.0)
        except Exception:
            top_score = 0.0
    if proposal_count >= 2:
        try:
            second_score = float((proposals or [{}, {}])[1].get("score", 0.0) or 0.0)
        except Exception:
            second_score = 0.0

    feature_count = len((snapshot.get("l1_state", {}) or {}).get("iv_features", []) or [])
    warning_count = len((snapshot.get("measurement_validation", {}) or {}).get("warnings", []) or [])
    status = "sufficient"
    reason = "Strong ontology-backed proposal is available."

    if proposal_count == 0:
        status = "insufficient_ontology_coverage"
        reason = "No ontology proposal matched the extracted features."
    elif top_score < 2:
        status = "low_confidence_candidates"
        reason = "Top proposal is supported by too few matched features."
    elif proposal_count >= 2 and abs(top_score - second_score) <= 0.5:
        status = "ambiguous_competing_candidates"
        reason = "Top ontology candidates are too close to treat as settled."
    elif feature_count <= 1 and warning_count > 0:
        status = "measurement_context_limited"
        reason = "Observed feature coverage is narrow and validation warnings remain."

    return {
        "status": status,
        "reason": reason,
        "proposal_count": proposal_count,
        "top_score": top_score,
        "second_score": second_score,
        "observed_feature_count": feature_count,
        "warning_count": warning_count,
    }


def build_exploratory_fallback(
    snapshot: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
    intent_profile: Dict[str, Any],
    coverage: Dict[str, Any],
) -> Dict[str, Any]:
    measurement_validation = snapshot.get("measurement_validation", {}) or {}
    l1_state = snapshot.get("l1_state", {}) or {}
    top = (reranked_proposals or [{}])[0] if reranked_proposals else {}
    llm_pattern = str(snapshot.get("llm_pattern") or "").strip()
    observed_patterns: List[str] = []
    if llm_pattern:
        observed_patterns.append(llm_pattern)
    features = l1_state.get("iv_features", []) or []
    if features:
        observed_patterns.append(f"관측 feature: {', '.join(features)}")
    warnings = measurement_validation.get("warnings", []) or []
    if warnings:
        observed_patterns.append(f"validation warning {len(warnings)}건")

    possible_hypotheses: List[Dict[str, Any]] = []
    for proposal in reranked_proposals[:3]:
        possible_hypotheses.append(
            {
                "hypothesis_id": f"existing::{proposal.get('claim_concept')}",
                "label": proposal.get("claim_concept") or "unknown_claim",
                "kind": "existing_ontology_candidate",
                "confidence": "tentative",
                "basis": proposal.get("matched_features", []) or [],
                "reason": "Existing ontology candidate retained as a tentative explanation.",
            }
        )

    if not possible_hypotheses:
        if any("field_enhanced" in item or "nonlinear" in item for item in features):
            possible_hypotheses.append(
                {
                    "hypothesis_id": "candidate::field_enhanced_transport",
                    "label": "field-enhanced transport candidate",
                    "kind": "exploratory_candidate",
                    "confidence": "exploratory",
                    "basis": features,
                    "reason": "Nonlinear/high-field signatures exist but no strong ontology mapping succeeded.",
                }
            )
        if warnings:
            possible_hypotheses.append(
                {
                    "hypothesis_id": "candidate::measurement_artifact",
                    "label": "measurement artifact candidate",
                    "kind": "exploratory_candidate",
                    "confidence": "exploratory",
                    "basis": warnings,
                    "reason": "Validation warnings suggest setup or acquisition artifacts may still explain the trace.",
                }
            )
        possible_hypotheses.append(
            {
                "hypothesis_id": "candidate::interface_or_barrier_limited_transport",
                "label": "interface/barrier-limited transport candidate",
                "kind": "exploratory_candidate",
                "confidence": "exploratory",
                "basis": features,
                "reason": "Use as a temporary bucket until temperature, electrode, and sweep metadata are confirmed.",
            }
        )

    missing_metadata: List[str] = []
    confirmed_conditions = intent_profile.get("confirmed_conditions", {}) or {}
    if "temperature" not in confirmed_conditions:
        missing_metadata.append("temperature dependence / measurement temperature")
    if not measurement_validation.get("measurement_conditions"):
        missing_metadata.append("measurement setup: DC vs pulse, compliance, sweep direction")
    if not intent_profile.get("notes"):
        missing_metadata.append("device stack / electrode / thickness context")

    experiment_ideas = build_experiment_ideas(
        possible_hypotheses=possible_hypotheses,
        confirmed_conditions=confirmed_conditions,
        top_proposal=top,
        measurement_validation=measurement_validation,
    )
    recommended_next_experiments = [item.get("title", "") for item in experiment_ideas if item.get("title")]

    summary = (
        "기존 ontology 안에서 충분히 강한 해석이 확보되지 않아, 현재 결과는 확정 결론보다 탐색형 가설 정리로 다루는 편이 적절합니다."
        if coverage.get("status") != "sufficient"
        else "현재 ontology coverage는 충분합니다."
    )
    return {
        "status": "fallback_active" if coverage.get("status") != "sufficient" else "fallback_not_needed",
        "summary": summary,
        "observed_patterns": observed_patterns,
        "possible_hypotheses": possible_hypotheses,
        "missing_metadata": missing_metadata,
        "recommended_next_experiments": _merge_unique([], recommended_next_experiments),
        "experiment_ideas": experiment_ideas,
    }


def build_experiment_ideas(
    possible_hypotheses: List[Dict[str, Any]],
    confirmed_conditions: Dict[str, Any],
    top_proposal: Dict[str, Any],
    measurement_validation: Dict[str, Any],
) -> List[Dict[str, Any]]:
    ideas: List[Dict[str, Any]] = []
    seen_titles = set()

    def add_idea(title: str, purpose: str, actions: List[str], expected: str, target_hypothesis: str) -> None:
        if not title or title in seen_titles:
            return
        seen_titles.add(title)
        ideas.append(
            {
                "title": title,
                "purpose": purpose,
                "actions": actions,
                "expected_signal": expected,
                "target_hypothesis": target_hypothesis,
            }
        )

    temperature_known = "temperature" in confirmed_conditions
    setup = confirmed_conditions.get("measurement_setup")
    reproducibility = confirmed_conditions.get("reproducibility")
    warnings = measurement_validation.get("warnings", []) or []

    if not temperature_known:
        add_idea(
            "온도 의존성 매핑",
            "transport mechanism과 artifact 가능성을 1차 분리",
            ["상온 외 2~3개 온도점에서 동일 sweep 수행", "동일 bias window에서 turn-on/기울기 변화 비교"],
            "온도 민감성이 크면 barrier/trap/thermally activated 성분 가능성이 올라감",
            "all_candidates",
        )

    if setup != "pulsed_bias":
        add_idea(
            "DC vs Pulse 비교",
            "self-heating 또는 charging artifact를 구분",
            ["동일 소자에서 DC sweep와 pulse sweep를 같은 범위로 비교", "pulse width와 duty cycle도 함께 기록"],
            "pulse에서 비선형성이 완화되면 heating/charging artifact 가능성이 올라감",
            "candidate::measurement_artifact",
        )

    for hypothesis in possible_hypotheses:
        hid = hypothesis.get("hypothesis_id", "")
        label = hypothesis.get("label", hid)
        if "field_enhanced" in hid or "fn_tunneling" in hid.lower():
            add_idea(
                f"{label} 검증용 두께/전극 스플릿",
                "field-enhanced 또는 barrier-limited 가설 검증",
                ["절연층 두께를 2수준 이상으로 나눈 샘플 비교", "전극 work function이 다른 조합 비교"],
                "두께/전극 변화에 따라 turn-on 또는 고전계 slope가 체계적으로 이동하면 지지 근거가 강해짐",
                hid,
            )
        elif "measurement_artifact" in hid:
            add_idea(
                "재현성 및 sweep 방향 체크",
                "artifact와 진짜 transport signature를 구분",
                ["forward/reverse sweep 비교", "반복 측정 3회 이상", "compliance/settling time 변경"],
                "재현성이 낮거나 sweep history 의존성이 크면 artifact 가능성이 높아짐",
                hid,
            )
        elif "barrier" in hid or "interface" in hid:
            add_idea(
                f"{label} 검증용 계면 제어 실험",
                "interface/barrier 지배 여부를 확인",
                ["계면 처리 전후 샘플 비교", "전극 치환 또는 annealing 전후 비교"],
                "계면 처리 변화에 따라 비선형성이나 turn-on 이동이 크면 계면 지배 가능성이 올라감",
                hid,
            )

    if reproducibility == "not_reproducible" or warnings:
        add_idea(
            "측정 안정성 점검 세트",
            "현재 데이터 품질 문제를 먼저 줄이기",
            ["케이블/접촉/접지 재확인", "compliance current 기록", "baseline noise와 zero-bias offset 확인"],
            "안정성 개선 후에도 패턴이 유지될 때만 메커니즘 논의를 강화하는 것이 안전함",
            "all_candidates",
        )

    if top_proposal.get("required_features"):
        required = ", ".join((top_proposal.get("required_features") or [])[:3])
        add_idea(
            "상위 가설 구분 feature 재측정",
            "현재 최상위 가설을 더 엄밀하게 검증",
            ["측정 범위와 분해능을 조정해 핵심 feature 재관측", "필요 시 low-field/high-field 구간을 분리 저장"],
            f"핵심 feature({required})가 안정적으로 재현되면 상위 가설의 신뢰도가 상승",
            str(top_proposal.get("claim_concept") or "top_proposal"),
        )

    return ideas[:6]


def write_candidate_hypotheses(
    run_dir: Path,
    coverage: Dict[str, Any],
    exploratory_fallback: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "run_id": run_dir.name,
        "generated_at_utc": utc_now_iso(),
        "coverage_status": coverage.get("status", "unknown"),
        "items": [],
    }
    for item in exploratory_fallback.get("possible_hypotheses", []) or []:
        hypothesis_id = item.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            continue
        related_ideas = [
            idea for idea in exploratory_fallback.get("experiment_ideas", []) or []
            if idea.get("target_hypothesis") in (hypothesis_id, "all_candidates")
        ]
        payload["items"].append(
            {
                "hypothesis_id": hypothesis_id,
                "label": item.get("label", hypothesis_id),
                "kind": item.get("kind", "exploratory_candidate"),
                "confidence": item.get("confidence", "exploratory"),
                "basis": item.get("basis", []),
                "reason": item.get("reason", ""),
                "experiment_ideas": related_ideas,
                "candidate_only": True,
            }
        )
    write_json(run_dir / CANDIDATE_HYPOTHESES_FILE, payload)
    return payload


def _apply_structured_answers(profile: Dict[str, Any], answers: List[StructuredAnswer]) -> None:
    approved = dict(profile.get("approved_patch_items", {}))
    assumption_states = dict(profile.get("assumption_states", {}))
    confirmed_conditions = dict(profile.get("confirmed_conditions", {}))
    uncertain_conditions = list(profile.get("uncertain_conditions", []))
    notes = list(profile.get("notes", []))

    for answer in answers:
        if answer.question_id == "analysis.priority":
            if answer.selected_ids:
                profile["analysis_priority"] = answer.selected_ids[0]
        elif answer.question_id == "conditions.temperature":
            if answer.answer_kind in ("confirm", "single_select") and answer.selected_ids:
                confirmed_conditions["temperature"] = answer.selected_ids[0]
                uncertain_conditions = [item for item in uncertain_conditions if item != "temperature"]
                approved["measurement_conditions"] = _merge_unique(
                    approved.get("measurement_conditions", []),
                    ["measurement_conditions.room_temperature"] if answer.approve_for_overlay else [],
                )
                if answer.approve_for_overlay and answer.selected_ids[0] == "room_temperature":
                    approved["assumptions"] = _merge_unique(
                        approved.get("assumptions", []),
                        ["physical_assumption.room_temperature_operation"],
                    )
            elif answer.answer_kind == "unknown":
                uncertain_conditions = _merge_unique(uncertain_conditions, ["temperature"])
        elif answer.question_id == "conditions.reproducibility":
            if answer.selected_ids:
                confirmed_conditions["reproducibility"] = answer.selected_ids[0]
        elif answer.question_id == "conditions.measurement_setup":
            if isinstance(answer.note, str) and answer.note.strip():
                confirmed_conditions["measurement_setup_details"] = answer.note.strip()
                setup_text = answer.note.strip().lower()
                if any(token in setup_text for token in ("pulse", "pulsed", "펄스")):
                    confirmed_conditions["measurement_setup"] = "pulsed_bias"
                elif any(token in setup_text for token in ("dc", "steady", "직류")):
                    confirmed_conditions["measurement_setup"] = "steady_state_dc"
        elif answer.question_id == "conditions.device_context":
            if isinstance(answer.note, str) and answer.note.strip():
                confirmed_conditions["device_context"] = answer.note.strip()
                lowered = answer.note.strip().lower()
                if any(token in lowered for token in ("thickness", "nm", "두께")):
                    confirmed_conditions["stack_or_thickness"] = answer.note.strip()
                if any(token in lowered for token in ("electrode", "au", "ag", "pt", "전극")):
                    confirmed_conditions["electrode_context"] = answer.note.strip()
        elif answer.category == "competing_proposal_disambiguation":
            if answer.answer_kind in ("single_select", "approve"):
                profile["focus_claims"] = _merge_unique(profile.get("focus_claims", []), answer.selected_ids)
                profile["exclude_claims"] = _remove_values(profile.get("exclude_claims", []), answer.selected_ids)
                if answer.approve_for_overlay:
                    approved["claims"] = _merge_unique(approved.get("claims", []), answer.selected_ids)
            elif answer.answer_kind == "deprioritize":
                profile["exclude_claims"] = _merge_unique(profile.get("exclude_claims", []), answer.selected_ids)
            elif answer.answer_kind == "multi_select":
                profile["keep_open_claims"] = _merge_unique(profile.get("keep_open_claims", []), answer.selected_ids)
        elif answer.category == "assumption_confirmation":
            for selected_id in answer.selected_ids:
                if answer.answer_kind == "confirm":
                    assumption_states[selected_id] = "confirmed"
                elif answer.answer_kind == "reject":
                    assumption_states[selected_id] = "rejected"
                elif answer.answer_kind == "approve":
                    assumption_states[selected_id] = "approved"
                    approved["assumptions"] = _merge_unique(approved.get("assumptions", []), [selected_id])
        if answer.condition_updates:
            confirmed_conditions.update(answer.condition_updates)
        if isinstance(answer.note, str) and answer.note.strip():
            notes = _merge_unique(notes, [answer.note.strip()])

    profile["approved_patch_items"] = approved
    profile["assumption_states"] = assumption_states
    profile["confirmed_conditions"] = confirmed_conditions
    profile["uncertain_conditions"] = uncertain_conditions
    profile["notes"] = notes


def build_question_catalog(snapshot: Dict[str, Any], intent_profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for question in generate_follow_up_questions(snapshot, intent_profile):
        catalog[question["question_id"]] = question

    # Keep canonical question ids valid even after they stop being suggested.
    catalog["analysis.priority"] = {
        "question_id": "analysis.priority",
        "category": "missing_condition_check",
        "expected_answer_kind": "single_select",
        "target_ids": [
            "mechanism_identification",
            "measurement_anomaly_diagnosis",
            "next_experiment_planning",
        ],
    }
    catalog["conditions.temperature"] = {
        "question_id": "conditions.temperature",
        "category": "missing_condition_check",
        "expected_answer_kind": "confirm",
        "target_ids": ["room_temperature", "temperature_uncertain"],
    }
    catalog["conditions.measurement_setup"] = {
        "question_id": "conditions.measurement_setup",
        "category": "missing_condition_check",
        "expected_answer_kind": "text",
        "allow_any_target_ids": True,
    }
    catalog["conditions.device_context"] = {
        "question_id": "conditions.device_context",
        "category": "missing_condition_check",
        "expected_answer_kind": "text",
        "allow_any_target_ids": True,
    }
    catalog["conditions.reproducibility"] = {
        "question_id": "conditions.reproducibility",
        "category": "missing_condition_check",
        "expected_answer_kind": "single_select",
        "target_ids": ["reproducible", "not_reproducible", "unknown"],
    }
    catalog["proposals.primary_focus"] = {
        "question_id": "proposals.primary_focus",
        "category": "competing_proposal_disambiguation",
        "expected_answer_kind": "single_select",
        "allow_any_target_ids": True,
    }

    catalog["proposals.manual_focus"] = {
        "question_id": "proposals.manual_focus",
        "category": "competing_proposal_disambiguation",
        "expected_answer_kind": "single_select",
        "allow_any_target_ids": True,
    }
    catalog["proposals.manual_exclude"] = {
        "question_id": "proposals.manual_exclude",
        "category": "competing_proposal_disambiguation",
        "expected_answer_kind": "deprioritize",
        "allow_any_target_ids": True,
    }
    catalog["proposals.manual_approve"] = {
        "question_id": "proposals.manual_approve",
        "category": "competing_proposal_disambiguation",
        "expected_answer_kind": "approve",
        "allow_any_target_ids": True,
    }
    catalog["assumptions.manual_confirm"] = {
        "question_id": "assumptions.manual_confirm",
        "category": "assumption_confirmation",
        "expected_answer_kind": "confirm",
        "allow_any_target_ids": True,
    }
    catalog["assumptions.manual_reject"] = {
        "question_id": "assumptions.manual_reject",
        "category": "assumption_confirmation",
        "expected_answer_kind": "reject",
        "allow_any_target_ids": True,
    }
    catalog["assumptions.manual_approve"] = {
        "question_id": "assumptions.manual_approve",
        "category": "assumption_confirmation",
        "expected_answer_kind": "approve",
        "allow_any_target_ids": True,
    }
    for index in range(1, 5):
        catalog[f"assumption.{index}"] = {
            "question_id": f"assumption.{index}",
            "category": "assumption_confirmation",
            "expected_answer_kind": "confirm",
            "allow_any_target_ids": True,
        }
    return catalog


def validate_structured_answers(run_dir: Path, structured_answers: List[StructuredAnswer]) -> List[Dict[str, Any]]:
    snapshot = load_analysis_snapshot(run_dir)
    intent_profile = load_intent_profile(run_dir)
    catalog = build_question_catalog(snapshot, intent_profile)
    errors: List[Dict[str, Any]] = []

    for answer in structured_answers:
        definition = catalog.get(answer.question_id)
        if definition is None:
            errors.append({"question_id": answer.question_id, "error": "unknown_question_id"})
            continue

        expected_kind = definition.get("expected_answer_kind")
        allowed_kinds = {expected_kind}
        if expected_kind == "confirm":
            allowed_kinds.update({"reject", "approve"})
        if expected_kind == "single_select":
            allowed_kinds.update({"approve", "deprioritize", "unknown"})
        if answer.answer_kind not in allowed_kinds:
            errors.append(
                {
                    "question_id": answer.question_id,
                    "error": "unexpected_answer_kind",
                    "expected": sorted(list(allowed_kinds)),
                    "actual": answer.answer_kind,
                }
            )

        expected_category = definition.get("category")
        if expected_category and answer.category and answer.category != expected_category:
            errors.append(
                {
                    "question_id": answer.question_id,
                    "error": "category_mismatch",
                    "expected": expected_category,
                    "actual": answer.category,
                }
            )

        allowed_ids = set(definition.get("target_ids", []))
        allow_any = bool(definition.get("allow_any_target_ids"))
        if not allow_any and allowed_ids and any(item not in allowed_ids for item in answer.selected_ids):
            errors.append(
                {
                    "question_id": answer.question_id,
                    "error": "selected_id_not_allowed",
                    "allowed_target_ids": sorted(list(allowed_ids)),
                    "actual_selected_ids": answer.selected_ids,
                }
            )

    return errors


def update_intent_profile(run_dir: Path, chat_request: ChatTurnRequest) -> Dict[str, Any]:
    profile = load_intent_profile(run_dir)
    snapshot = load_analysis_snapshot(run_dir)
    update = chat_request.intent_update.model_dump()
    inferred = infer_intent_from_text(chat_request.user_text)
    contextual = infer_contextual_intent_from_text(chat_request.user_text, snapshot)
    inferred_context = infer_structured_context_from_text(chat_request.user_text)

    analysis_priority = update.get("analysis_priority") or contextual.get("analysis_priority") or inferred.get("analysis_priority")
    if analysis_priority:
        profile["analysis_priority"] = analysis_priority

    merged_focus = list(update.get("focus_claims", [])) + list(contextual.get("focus_claims", [])) + list(inferred.get("focus_claims", []))
    merged_exclude = list(update.get("exclude_claims", [])) + list(contextual.get("exclude_claims", [])) + list(inferred.get("exclude_claims", []))

    profile["focus_claims"] = _merge_unique(profile.get("focus_claims", []), merged_focus)
    profile["focus_claims"] = _remove_values(profile["focus_claims"], merged_exclude)
    profile["exclude_claims"] = _merge_unique(profile.get("exclude_claims", []), merged_exclude)
    profile["exclude_claims"] = _remove_values(profile["exclude_claims"], merged_focus)
    profile["keep_open_claims"] = _merge_unique(profile.get("keep_open_claims", []), update.get("keep_open_claims", []))

    confirmed_conditions = dict(profile.get("confirmed_conditions", {}))
    confirmed_conditions.update(inferred.get("confirmed_conditions", {}))
    confirmed_conditions.update(contextual.get("confirmed_conditions", {}))
    confirmed_conditions.update(inferred_context)
    confirmed_conditions.update(update.get("confirmed_conditions", {}))
    profile["confirmed_conditions"] = confirmed_conditions
    profile["uncertain_conditions"] = _merge_unique(
        profile.get("uncertain_conditions", []),
        list(inferred.get("uncertain_conditions", [])) + list(contextual.get("uncertain_conditions", [])) + list(update.get("uncertain_conditions", [])),
    )

    assumption_states = dict(profile.get("assumption_states", {}))
    for assumption_id in list(contextual.get("confirmed_assumptions", [])) + list(update.get("confirmed_assumptions", [])):
        assumption_states[assumption_id] = "confirmed"
    for assumption_id in list(contextual.get("rejected_assumptions", [])) + list(update.get("rejected_assumptions", [])):
        assumption_states[assumption_id] = "rejected"
    for assumption_id in list(contextual.get("approved_assumptions", [])) + list(update.get("approved_assumptions", [])):
        assumption_states[assumption_id] = "approved"
    for answer in chat_request.structured_answers:
        for assumption_id in answer.selected_ids:
            if answer.category != "assumption_confirmation":
                continue
            if answer.answer_kind == "confirm":
                assumption_states[assumption_id] = "confirmed"
            elif answer.answer_kind == "reject":
                assumption_states[assumption_id] = "rejected"
            elif answer.answer_kind == "approve":
                assumption_states[assumption_id] = "approved"
    profile["assumption_states"] = assumption_states

    approved = dict(profile.get("approved_patch_items", {}))
    approved["claims"] = _merge_unique(approved.get("claims", []), update.get("approved_claims", []))
    approved["assumptions"] = _merge_unique(
        approved.get("assumptions", []),
        list(contextual.get("approved_assumptions", [])) + list(update.get("approved_assumptions", [])),
    )
    approved["measurement_conditions"] = _merge_unique(approved.get("measurement_conditions", []), [])
    profile["approved_patch_items"] = approved

    note = update.get("note")
    if isinstance(note, str) and note.strip():
        profile["notes"] = _merge_unique(profile.get("notes", []), [note.strip()])
    elif chat_request.user_text.strip():
        profile["notes"] = _merge_unique(profile.get("notes", []), [chat_request.user_text.strip()])

    _apply_structured_answers(profile, chat_request.structured_answers)

    profile["history"] = list(profile.get("history", []))
    profile["history"].append(
        {
            "timestamp_utc": utc_now_iso(),
            "intent_update": IntentUpdate(**chat_request.intent_update.model_dump()).model_dump(),
            "user_text": chat_request.user_text,
            "structured_answers": [answer.model_dump() for answer in chat_request.structured_answers],
        }
    )
    profile["updated_at_utc"] = utc_now_iso()

    write_json(run_dir / "intent_profile.json", profile)
    return profile


def _collect_validation_counts(field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for intent_path in RUNS_DIR.glob("*/intent_profile.json"):
        payload = load_json(intent_path)
        approved = payload.get("approved_patch_items", {})
        for item in approved.get(field, []):
            if not isinstance(item, str) or not item:
                continue
            counts[item] = counts.get(item, 0) + 1
    return counts


def _make_patch_entries(
    values: Iterable[str],
    counts: Dict[str, int],
    key_name: str,
    repeat_threshold: int,
    run_id: str,
    notes: List[str] | None = None,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for value in values:
        count = counts.get(value, 0)
        entries.append(
            {
                key_name: value,
                "approval_state": "approved",
                "promotion_reason": "repeated_validation" if count >= repeat_threshold else "user_approved",
                "validation_count": count,
                "source_run_id": run_id,
                "approved_at_utc": utc_now_iso(),
                "evidence": {
                    "validation_count": count,
                    "notes": list(notes or []),
                },
            }
        )
    return entries


def build_ontology_patch(run_dir: Path, intent_profile: Dict[str, Any], repeat_threshold: int = 2) -> Dict[str, Any]:
    claim_counts = _collect_validation_counts("claims")
    assumption_counts = _collect_validation_counts("assumptions")
    condition_counts = _collect_validation_counts("measurement_conditions")
    approved = intent_profile.get("approved_patch_items", {})
    patch = {
        "run_id": run_dir.name,
        "status": "candidate_overlay",
        "generated_at_utc": utc_now_iso(),
        "claims": _make_patch_entries(
            approved.get("claims", []),
            claim_counts,
            "claim_concept",
            repeat_threshold,
            run_dir.name,
            intent_profile.get("notes", []),
        ),
        "assumptions": _make_patch_entries(
            approved.get("assumptions", []),
            assumption_counts,
            "assumption_id",
            repeat_threshold,
            run_dir.name,
            intent_profile.get("notes", []),
        ),
        "measurement_conditions": _make_patch_entries(
            approved.get("measurement_conditions", []),
            condition_counts,
            "condition_id",
            repeat_threshold,
            run_dir.name,
            intent_profile.get("notes", []),
        ),
    }
    write_json(run_dir / "ontology_patch.json", patch)
    return patch


def rebuild_review_queue(repeat_threshold: int = 2) -> Dict[str, Any]:
    queue = default_review_queue()
    state = load_review_state()
    reviewed_index = {
        (item.get("overlay_type"), item.get("target_id")): item
        for item in state.get("items", [])
        if isinstance(item, dict)
    }
    aggregated: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for patch_path in RUNS_DIR.glob("*/ontology_patch.json"):
        patch = load_json(patch_path)
        run_id = patch.get("run_id")
        for overlay_type, field_name, id_key in (
            ("claim", "claims", "claim_concept"),
            ("assumption", "assumptions", "assumption_id"),
            ("measurement_condition", "measurement_conditions", "condition_id"),
        ):
            for item in patch.get(field_name, []):
                target_id = item.get(id_key)
                if not isinstance(target_id, str) or not target_id:
                    continue
                key = (overlay_type, target_id)
                entry = aggregated.setdefault(
                    key,
                    {
                        "overlay_type": overlay_type,
                        "target_id": target_id,
                        "support_count": 0,
                        "source_runs": [],
                        "last_promotion_reason": item.get("promotion_reason"),
                    },
                )
                entry["support_count"] += 1
                if run_id not in entry["source_runs"]:
                    entry["source_runs"].append(run_id)

    queue_items: List[Dict[str, Any]] = []
    for key, entry in aggregated.items():
        reviewed = reviewed_index.get(key, {})
        queue_items.append(
            {
                **entry,
                "status": reviewed.get("status", "pending_review"),
                "review_note": reviewed.get("review_note"),
                "eligible_for_review": entry["support_count"] >= repeat_threshold,
            }
        )

    queue["generated_at_utc"] = utc_now_iso()
    queue["items"] = sorted(queue_items, key=lambda item: (item["status"], -item["support_count"], item["target_id"]))
    write_json(REVIEW_QUEUE_PATH, queue)
    return queue


def apply_review_decision(overlay_type: str, target_id: str, decision: str, note: str | None = None) -> Dict[str, Any]:
    queue = rebuild_review_queue()
    matching = next(
        (item for item in queue.get("items", []) if item.get("overlay_type") == overlay_type and item.get("target_id") == target_id),
        None,
    )
    if matching is None:
        raise KeyError(f"overlay review target not found: {overlay_type}:{target_id}")

    state = load_review_state()
    items = [item for item in state.get("items", []) if not (item.get("overlay_type") == overlay_type and item.get("target_id") == target_id)]
    items.append(
        {
            "overlay_type": overlay_type,
            "target_id": target_id,
            "status": decision,
            "review_note": note or "",
            "updated_at_utc": utc_now_iso(),
        }
    )
    state["items"] = items
    state["updated_at_utc"] = utc_now_iso()
    write_json(REVIEW_STATE_PATH, state)
    rebuild_review_queue()
    return state


def rebuild_curated_overlay(repeat_threshold: int = 2) -> Dict[str, Any]:
    queue = rebuild_review_queue(repeat_threshold=repeat_threshold)
    reviewed_index = {
        (item.get("overlay_type"), item.get("target_id")): item
        for item in load_review_state().get("items", [])
        if isinstance(item, dict) and item.get("status") == "approved"
    }

    overlay = default_curated_overlay()
    overlay["generated_at_utc"] = utc_now_iso()
    for item in queue.get("items", []):
        key = (item.get("overlay_type"), item.get("target_id"))
        reviewed = reviewed_index.get(key)
        if reviewed is None:
            continue
        support_count = int(item.get("support_count", 0) or 0)
        if item.get("overlay_type") == "claim":
            overlay["claims"].append(
                {
                    "claim_concept": item.get("target_id"),
                    "support_count": support_count,
                    "source_runs": item.get("source_runs", []),
                    "review_note": reviewed.get("review_note", ""),
                    "score_delta": min(2.0, 0.5 * support_count),
                }
            )
        elif item.get("overlay_type") == "assumption":
            overlay["assumptions"].append(
                {
                    "assumption_id": item.get("target_id"),
                    "support_count": support_count,
                    "source_runs": item.get("source_runs", []),
                    "review_note": reviewed.get("review_note", ""),
                    "score_delta": min(1.5, 0.25 * support_count),
                }
            )
        elif item.get("overlay_type") == "measurement_condition":
            overlay["measurement_conditions"].append(
                {
                    "condition_id": item.get("target_id"),
                    "support_count": support_count,
                    "source_runs": item.get("source_runs", []),
                    "review_note": reviewed.get("review_note", ""),
                }
            )
    write_json(CURATED_OVERLAY_PATH, overlay)
    return overlay


def rerank_proposals_with_intent(
    proposals: List[Dict[str, Any]],
    intent_profile: Dict[str, Any],
    curated_overlay: Dict[str, Any] | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    curated_overlay = curated_overlay or default_curated_overlay()
    focus_claims = set(intent_profile.get("focus_claims", []))
    exclude_claims = set(intent_profile.get("exclude_claims", []))
    keep_open_claims = set(intent_profile.get("keep_open_claims", []))
    confirmed_conditions = intent_profile.get("confirmed_conditions", {}) or {}
    assumption_states = intent_profile.get("assumption_states", {}) or {}
    overlay_claims = {item.get("claim_concept"): item for item in curated_overlay.get("claims", []) if isinstance(item, dict)}
    overlay_assumptions = {item.get("assumption_id"): item for item in curated_overlay.get("assumptions", []) if isinstance(item, dict)}
    analysis_priority = intent_profile.get("analysis_priority")

    reranked: List[Dict[str, Any]] = []
    adjustments_summary: List[Dict[str, Any]] = []
    for proposal in proposals or []:
        claim = proposal.get("claim_concept")
        base_score = float(proposal.get("score", 0.0) or 0.0)
        score = base_score
        adjustments: List[Dict[str, Any]] = []

        overlay_claim = overlay_claims.get(claim)
        if overlay_claim:
            delta = float(overlay_claim.get("score_delta", 0.0) or 0.0)
            score += delta
            adjustments.append(
                {
                    "type": "curated_overlay_claim",
                    "delta": delta,
                    "reason": f"검토된 overlay에서 같은 해석을 지지한 run이 {overlay_claim.get('support_count')}개 있습니다.",
                }
            )

        if claim in focus_claims:
            score += 3.0
            adjustments.append({"type": "focus_claim", "delta": 3.0, "reason": "사용자가 이 해석을 우선해서 보길 원했습니다."})
        if claim in keep_open_claims:
            score += 1.0
            adjustments.append({"type": "keep_open", "delta": 1.0, "reason": "사용자가 이 후보를 계속 열어 두길 원했습니다."})
        if claim in exclude_claims:
            score -= 5.0
            adjustments.append({"type": "exclude_claim", "delta": -5.0, "reason": "사용자가 이 해석의 우선순위를 낮추길 원했습니다."})

        if analysis_priority == "measurement_anomaly_diagnosis":
            validation_penalty = len(proposal.get("matched_features", []) or []) * -0.1
            if validation_penalty:
                score += validation_penalty
                adjustments.append(
                    {
                        "type": "analysis_priority",
                        "delta": validation_penalty,
                        "reason": "측정 이상 진단을 우선하므로 메커니즘 중심 랭킹을 조금 낮췄습니다.",
                    }
                )
        elif analysis_priority == "next_experiment_planning":
            planning_bonus = min(1.5, 0.5 * len(proposal.get("required_features", []) or []))
            if planning_bonus:
                score += planning_bonus
                adjustments.append(
                    {
                        "type": "analysis_priority",
                        "delta": planning_bonus,
                        "reason": "다음 실험 설계 목적이므로 구분 실험을 제안하기 쉬운 가설에 가점을 주었습니다.",
                    }
                )

        if confirmed_conditions.get("temperature") == "room_temperature":
            if "physical_assumption.room_temperature_operation" in set(proposal.get("sj_assumptions", []) or []):
                score += 1.0
                adjustments.append(
                    {"type": "confirmed_condition", "delta": 1.0, "reason": "사용자가 상온 측정 조건을 확인했습니다."}
                )

        for assumption_id in proposal.get("sj_assumptions", []) or []:
            overlay_assumption = overlay_assumptions.get(assumption_id)
            if overlay_assumption:
                delta = float(overlay_assumption.get("score_delta", 0.0) or 0.0)
                score += delta
                adjustments.append(
                    {
                        "type": "curated_overlay_assumption",
                        "delta": delta,
                        "reason": f"검토된 overlay에서 같은 가정을 지지한 run이 {overlay_assumption.get('support_count')}개 있습니다.",
                    }
                )

            state = assumption_states.get(assumption_id)
            if state == "confirmed":
                score += 0.75
                adjustments.append({"type": "confirmed_assumption", "delta": 0.75, "reason": f"사용자가 {term_label(assumption_id)}을(를) 확인했습니다."})
            elif state == "approved":
                score += 1.5
                adjustments.append({"type": "approved_assumption", "delta": 1.5, "reason": f"사용자가 {term_label(assumption_id)}을(를) overlay 후보로 승인했습니다."})
            elif state == "rejected":
                score -= 2.0
                adjustments.append({"type": "rejected_assumption", "delta": -2.0, "reason": f"사용자가 {term_label(assumption_id)}을(를) 배제했습니다."})

        reranked_item = dict(proposal)
        reranked_item["base_score"] = base_score
        reranked_item["intent_score_delta"] = round(score - base_score, 3)
        reranked_item["final_score"] = round(score, 3)
        reranked_item["score"] = round(score, 3)
        reranked_item["rerank_reasons"] = [item.get("reason", "") for item in adjustments]
        reranked_item["intent_adjustments"] = adjustments
        reranked.append(reranked_item)
        if adjustments:
            adjustments_summary.append(
                {
                    "claim_concept": claim,
                    "adjustments": adjustments,
                    "base_score": base_score,
                    "intent_score_delta": round(score - base_score, 3),
                    "final_score": round(score, 3),
                }
            )

    reranked.sort(key=lambda item: item.get("score", 0), reverse=True)
    return reranked, adjustments_summary


def generate_follow_up_questions(snapshot: Dict[str, Any], intent_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    questions: List[DomainChatQuestion] = []
    measurement_validation = snapshot.get("measurement_validation", {}) or {}
    proposals = snapshot.get("sj_proposals", []) or []
    coverage = assess_ontology_coverage(snapshot, proposals)
    confirmed_conditions = intent_profile.get("confirmed_conditions", {}) or {}
    assumption_states = intent_profile.get("assumption_states", {}) or {}
    asked_ids = {
        entry.get("question_id")
        for entry in intent_profile.get("history", [])
        for answer in entry.get("structured_answers", [])
        if isinstance(answer, dict) and isinstance(answer.get("question_id"), str)
    }

    if not intent_profile.get("analysis_priority") and "analysis.priority" not in asked_ids:
        questions.append(
            DomainChatQuestion(
                question_id="analysis.priority",
                category="missing_condition_check",
                prompt="이번 분석에서 가장 중요한 목표는 무엇인가요?",
                reason="사용자의 목표가 메커니즘 식별인지, 이상 진단인지, 다음 실험 설계인지에 따라 제안 순위를 조정해야 합니다.",
                target_ids=[
                    "mechanism_identification",
                    "measurement_anomaly_diagnosis",
                    "next_experiment_planning",
                ],
                expected_answer_kind="single_select",
                options=[
                    {"id": "mechanism_identification", "label": "메커니즘 식별"},
                    {"id": "measurement_anomaly_diagnosis", "label": "측정 이상 진단"},
                    {"id": "next_experiment_planning", "label": "다음 실험 설계"},
                ],
            )
        )

    if "temperature" not in confirmed_conditions and "conditions.temperature" not in asked_ids:
        questions.append(
            DomainChatQuestion(
                question_id="conditions.temperature",
                category="missing_condition_check",
                prompt="상온 측정이 확인되었나요, 아니면 온도 조건이 아직 불확실한가요?",
                reason="현재 해석 중 일부는 온도 의존 가정에 민감하지만, 이번 run에는 확정된 온도 메타데이터가 없습니다.",
                target_ids=["room_temperature", "temperature_uncertain"],
                expected_answer_kind="single_select",
                options=[
                    {"id": "room_temperature", "label": "상온 측정 확인"},
                    {"id": "temperature_uncertain", "label": "온도 조건 불확실"},
                ],
            )
        )

    if not measurement_validation.get("measurement_conditions") and "conditions.measurement_setup" not in asked_ids:
        questions.append(
            DomainChatQuestion(
                question_id="conditions.measurement_setup",
                category="missing_condition_check",
                prompt="steady-state DC, pulsed bias, 전극 조건 같은 측정 설정을 확인해 주실 수 있나요?",
                reason="이번 run에는 측정 조건 메타데이터가 부족해서 해석 신뢰도가 떨어집니다.",
                target_ids=["measurement_conditions.sweep_iv", "measurement_conditions.steady_state_dc_iv"],
                expected_answer_kind="text",
            )
        )

    if coverage.get("status") != "sufficient":
        if "conditions.device_context" not in asked_ids:
            questions.append(
                DomainChatQuestion(
                    question_id="conditions.device_context",
                    category="missing_condition_check",
                    prompt="전극 재료, 절연층 두께, sweep direction, compliance 같은 디바이스/측정 맥락을 더 알려주실 수 있나요?",
                    reason="지금은 ontology coverage가 약해서, 해석보다 메타데이터 보강이 우선입니다.",
                    target_ids=["device_context"],
                    expected_answer_kind="text",
                )
            )
        if "conditions.reproducibility" not in asked_ids:
            questions.append(
                DomainChatQuestion(
                    question_id="conditions.reproducibility",
                    category="missing_condition_check",
                    prompt="이 패턴이 반복 측정에서도 재현되는지, sweep 방향을 바꿔도 유지되는지 확인되었나요?",
                    reason="재현성 정보가 있어야 artifact와 transport hypothesis를 구분하기 쉽습니다.",
                    target_ids=["reproducible", "not_reproducible", "unknown"],
                    expected_answer_kind="single_select",
                    options=[
                        {"id": "reproducible", "label": "반복 측정에서도 재현됨"},
                        {"id": "not_reproducible", "label": "재현되지 않음"},
                        {"id": "unknown", "label": "아직 모름"},
                    ],
                )
            )

    if len(proposals) >= 2 and "proposals.primary_focus" not in asked_ids:
        first = proposals[0]
        second = proposals[1]
        try:
            score_gap = abs(float(first.get("score", 0)) - float(second.get("score", 0)))
        except Exception:
            score_gap = 999.0
        if score_gap <= 1.0:
            first_label = term_label(str(first.get("claim_concept") or ""))
            second_label = term_label(str(second.get("claim_concept") or ""))
            questions.append(
                DomainChatQuestion(
                    question_id="proposals.primary_focus",
                    category="competing_proposal_disambiguation",
                    prompt=f"{first_label}와 {second_label} 중 어느 해석을 더 집중해서 보고 싶으신가요?",
                    reason="상위 제안들의 점수 차이가 작아서, 여기서는 사용자 선호를 반영해도 안전합니다.",
                    target_ids=[str(first.get("claim_concept") or ""), str(second.get("claim_concept") or "")],
                    expected_answer_kind="single_select",
                    options=[
                        {"id": str(first.get("claim_concept") or ""), "label": first_label},
                        {"id": str(second.get("claim_concept") or ""), "label": second_label},
                    ],
                )
            )

    top = proposals[0] if proposals else {}
    for index, assumption_id in enumerate((top.get("sj_assumptions", []) or [])[:2]):
        if assumption_id not in assumption_states:
            assumption_label = term_label(str(assumption_id))
            assumption_desc = term_description(str(assumption_id))
            prompt = f"{assumption_label}을(를) 확인할지, 배제할지, overlay 후보로 승인할지 알려주세요."
            if assumption_desc:
                prompt += f" {assumption_desc}"
            questions.append(
                DomainChatQuestion(
                    question_id=f"assumption.{index + 1}",
                    category="assumption_confirmation",
                    prompt=prompt,
                    reason="현재 최상위 해석은 아직 사용자 확인이 없는 가정에 의존하고 있습니다.",
                    target_ids=[assumption_id],
                    expected_answer_kind="confirm",
                    options=[
                        {"id": assumption_id, "label": f"{assumption_label} 확인 또는 승인"},
                    ],
                )
            )

    return [question.model_dump() for question in questions[:4]]


def build_chat_response(run_dir: Path) -> Dict[str, Any]:
    from backend.domains.iv.renderer import render_system_narrative_ko

    snapshot = load_analysis_snapshot(run_dir)
    intent_profile = load_intent_profile(run_dir)
    build_ontology_patch(run_dir, intent_profile)
    curated_overlay = rebuild_curated_overlay()
    review_queue = rebuild_review_queue()
    review_state = load_review_state()
    reranked_proposals, adjustments = rerank_proposals_with_intent(
        snapshot.get("sj_proposals", []),
        intent_profile,
        curated_overlay=curated_overlay,
    )
    coverage = assess_ontology_coverage(snapshot, reranked_proposals)
    exploratory_fallback = build_exploratory_fallback(snapshot, reranked_proposals, intent_profile, coverage)
    candidate_hypotheses = write_candidate_hypotheses(run_dir, coverage, exploratory_fallback)
    derived = snapshot.get("assumptions", {}) or {}
    narrative = render_system_narrative_ko(
        measurement_validation=snapshot.get("measurement_validation", {}),
        llm_pattern=str(snapshot.get("llm_pattern", "")),
        l1_state=snapshot.get("l1_state", {}),
        sj_proposals=reranked_proposals,
        derived=derived,
        intent_profile=intent_profile,
        proposal_adjustments=adjustments,
        curated_overlay=curated_overlay,
    )
    questions = generate_follow_up_questions({**snapshot, "sj_proposals": reranked_proposals}, intent_profile)
    sync_suggested_questions(run_dir, questions)
    patch = load_json(run_dir / "ontology_patch.json", fallback=default_patch_payload(run_dir.name))
    return {
        "run_id": run_dir.name,
        "intent_profile": intent_profile,
        "ontology_patch": patch,
        "curated_overlay": curated_overlay,
        "overlay_review_queue": review_queue,
        "overlay_review_state": review_state,
        "coverage_assessment": coverage,
        "exploratory_fallback": exploratory_fallback,
        "candidate_hypotheses": candidate_hypotheses,
        "reranked_sj_proposals": reranked_proposals,
        "proposal_adjustments": adjustments,
        "system_narrative": narrative["system_narrative"],
        "L1 좌표 요약": narrative["L1 좌표 요약"],
        "과학적 정당화 제안": narrative["과학적 정당화 제안"],
        "suggested_questions": questions,
        "chat_history": load_chat_history(run_dir),
        "chat_mode": "intent_update",
        "assistant_reply": "",
    }
