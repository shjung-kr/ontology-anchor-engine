"""
Run-scoped conversational memory, strict Q/A handling, and curated overlay helpers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from backend.conversation.models import ChatTurnRequest, DomainChatQuestion, IntentUpdate, StructuredAnswer


RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"
OVERLAY_DIR = Path(__file__).resolve().parents[1] / "ontology_overlays"
CURATED_OVERLAY_PATH = OVERLAY_DIR / "iv_user_overlay.json"
REVIEW_QUEUE_PATH = OVERLAY_DIR / "iv_review_queue.json"
REVIEW_STATE_PATH = OVERLAY_DIR / "iv_review_state.json"


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

    if not chat_path.exists():
        chat_path.write_text("", encoding="utf-8")
    if not intent_path.exists():
        write_json(intent_path, default_intent_profile(run_id))
    if not patch_path.exists():
        write_json(patch_path, default_patch_payload(run_id))


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


def build_direct_answer(
    user_text: str,
    snapshot: Dict[str, Any],
    intent_profile: Dict[str, Any],
    reranked_proposals: List[Dict[str, Any]],
) -> str:
    text = (user_text or "").strip()
    if not text:
        return ""

    top = reranked_proposals[0] if reranked_proposals else {}
    claim = top.get("claim_concept") or "해석 후보 없음"
    final_score = top.get("final_score", top.get("score"))
    confirmed_conditions = intent_profile.get("confirmed_conditions", {}) or {}
    assumptions = top.get("sj_assumptions", []) or []
    required_features = top.get("required_features", []) or []
    warnings = snapshot.get("measurement_validation", {}).get("warnings", []) or []

    answer_lines: List[str] = []
    answer_lines.append(f"현재 run 기준 최상위 해석은 `{claim}` 이고 score는 {final_score} 입니다.")

    priority = intent_profile.get("analysis_priority")
    if priority == "next_experiment_planning":
        answer_lines.append("질문이 다음 실험 설계에 가깝기 때문에, 현재는 메커니즘 확정보다 구분 실험 제안 중심으로 답하는 것이 적절합니다.")
    elif priority == "measurement_anomaly_diagnosis":
        answer_lines.append("질문이 이상 진단 맥락으로 해석되므로, 메커니즘 결론보다 측정 검증 포인트를 먼저 보는 것이 맞습니다.")

    if confirmed_conditions:
        answer_lines.append(f"현재 확인된 조건은 {confirmed_conditions} 입니다.")
    if warnings:
        answer_lines.append(f"다만 validation warning이 {len(warnings)}건 있어 해석 전에 함께 점검하는 편이 좋습니다.")

    if "turn-on voltage" in text.lower() or "턴온" in text or "turn on" in text.lower():
        answer_lines.append("턴온 전압을 낮추는 방향을 보려면 장벽 높이/두께, 계면 상태, 전극 일함수 차이, 트랩 분포를 먼저 의심하는 것이 일반적입니다.")
        answer_lines.append("현재 상위 해석이 FN 계열이라면, 다음으로는 전극 변경, 절연층 두께 변화, 온도 의존성 비교 실험이 우선순위가 높습니다.")
    elif any(token in text.lower() for token in ("next experiment", "다음 실험", "후속 실험", "추천")):
        answer_lines.append("다음 실험은 상위 가설을 구분할 수 있는 변수부터 바꾸는 것이 좋습니다.")
        if required_features:
            answer_lines.append(f"현재 상위 해석이 기대하는 핵심 feature는 {', '.join(required_features)} 입니다.")
        answer_lines.append("권장 순서는 온도 의존성, sweep mode(DC/pulse), 전극 또는 두께 변경 비교입니다.")
    elif any(token in text.lower() for token in ("why", "왜", "이유", "근거")):
        matched = top.get("matched_features", []) or []
        answer_lines.append(f"현재 해석이 올라온 직접 근거는 {', '.join(matched) if matched else 'matched feature 없음'} 입니다.")
        if assumptions:
            answer_lines.append(f"다만 이 해석은 {', '.join(assumptions[:3])} 같은 가정에 의존합니다.")
    else:
        matched = top.get("matched_features", []) or []
        answer_lines.append(f"현재 답변은 상위 해석과 일치하는 관측 feature인 {', '.join(matched) if matched else '없음'}을 기준으로 구성했습니다.")
        if assumptions:
            answer_lines.append(f"확인 또는 배제가 필요한 대표 가정은 {', '.join(assumptions[:2])} 입니다.")

    return "\n".join(answer_lines)


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
                    "reason": f"Curated overlay support_count={overlay_claim.get('support_count')}.",
                }
            )

        if claim in focus_claims:
            score += 3.0
            adjustments.append({"type": "focus_claim", "delta": 3.0, "reason": "User asked to prioritize this interpretation."})
        if claim in keep_open_claims:
            score += 1.0
            adjustments.append({"type": "keep_open", "delta": 1.0, "reason": "User wants to keep this candidate active."})
        if claim in exclude_claims:
            score -= 5.0
            adjustments.append({"type": "exclude_claim", "delta": -5.0, "reason": "User asked to de-prioritize this interpretation."})

        if analysis_priority == "measurement_anomaly_diagnosis":
            validation_penalty = len(proposal.get("matched_features", []) or []) * -0.1
            if validation_penalty:
                score += validation_penalty
                adjustments.append(
                    {
                        "type": "analysis_priority",
                        "delta": validation_penalty,
                        "reason": "Anomaly diagnosis mode reduces confidence in mechanism-first ranking.",
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
                        "reason": "Next-experiment planning favors hypotheses with clear follow-up discriminators.",
                    }
                )

        if confirmed_conditions.get("temperature") == "room_temperature":
            if "physical_assumption.room_temperature_operation" in set(proposal.get("sj_assumptions", []) or []):
                score += 1.0
                adjustments.append(
                    {"type": "confirmed_condition", "delta": 1.0, "reason": "User confirmed room-temperature operation."}
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
                        "reason": f"Curated overlay assumption support_count={overlay_assumption.get('support_count')}.",
                    }
                )

            state = assumption_states.get(assumption_id)
            if state == "confirmed":
                score += 0.75
                adjustments.append({"type": "confirmed_assumption", "delta": 0.75, "reason": f"User confirmed assumption {assumption_id}."})
            elif state == "approved":
                score += 1.5
                adjustments.append({"type": "approved_assumption", "delta": 1.5, "reason": f"User approved assumption {assumption_id} for overlay consideration."})
            elif state == "rejected":
                score -= 2.0
                adjustments.append({"type": "rejected_assumption", "delta": -2.0, "reason": f"User rejected assumption {assumption_id}."})

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

    if len(proposals) >= 2 and "proposals.primary_focus" not in asked_ids:
        first = proposals[0]
        second = proposals[1]
        try:
            score_gap = abs(float(first.get("score", 0)) - float(second.get("score", 0)))
        except Exception:
            score_gap = 999.0
        if score_gap <= 1.0:
            questions.append(
                DomainChatQuestion(
                    question_id="proposals.primary_focus",
                    category="competing_proposal_disambiguation",
                    prompt=f"{first.get('claim_concept')}와 {second.get('claim_concept')} 중 어느 해석을 더 집중해서 보고 싶으신가요?",
                    reason="상위 제안들의 점수 차이가 작아서, 여기서는 사용자 선호를 반영해도 안전합니다.",
                    target_ids=[str(first.get("claim_concept") or ""), str(second.get("claim_concept") or "")],
                    expected_answer_kind="single_select",
                    options=[
                        {"id": str(first.get("claim_concept") or ""), "label": str(first.get("claim_concept") or "")},
                        {"id": str(second.get("claim_concept") or ""), "label": str(second.get("claim_concept") or "")},
                    ],
                )
            )

    top = proposals[0] if proposals else {}
    for index, assumption_id in enumerate((top.get("sj_assumptions", []) or [])[:2]):
        if assumption_id not in assumption_states:
            questions.append(
                DomainChatQuestion(
                    question_id=f"assumption.{index + 1}",
                    category="assumption_confirmation",
                    prompt=f"`{assumption_id}` 가정을 확인할지, 배제할지, overlay 후보로 승인할지 알려주세요.",
                    reason="현재 최상위 해석은 아직 사용자 확인이 없는 가정에 의존하고 있습니다.",
                    target_ids=[assumption_id],
                    expected_answer_kind="confirm",
                    options=[
                        {"id": assumption_id, "label": "이 가정 확인 또는 승인"},
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
        "reranked_sj_proposals": reranked_proposals,
        "proposal_adjustments": adjustments,
        "system_narrative": narrative["system_narrative"],
        "L1 좌표 요약": narrative["L1 좌표 요약"],
        "과학적 정당화 제안": narrative["과학적 정당화 제안"],
        "suggested_questions": questions,
        "chat_mode": "intent_update",
        "assistant_reply": "",
    }
