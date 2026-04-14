"""
I-V 도메인 전용 실행 파이프라인.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.conversation.memory import build_chat_response, ensure_memory_files
from backend.domains.iv.common import PROMPTS_DIR, RUNS_DIR
from backend.domains.iv.features import build_l1_state
from backend.domains.iv.proposals import build_derived_assumptions, evaluate_scientific_justification
from backend.domains.iv.registry import load_registry_from_folders
from backend.domains.iv.renderer import render_system_narrative_ko
from backend.domains.iv.validation import validate_measurement
from backend.llm_adapter import llm_analyze_numeric


def run_iv_domain(raw_data: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    I-V 도메인 전체 분석 파이프라인을 실행한다.
    """

    metadata = dict(metadata or {})
    measurement_validation = validate_measurement(raw_data, metadata=metadata)

    llm_result = llm_analyze_numeric(raw_data)
    llm_pattern = str(llm_result.get("pattern") or "")
    llm_keywords = llm_result.get("keywords", []) or []
    metrics = llm_result.get("metrics", {}) or {}
    regimes = llm_result.get("regimes", []) or []
    llm_trace = llm_result.get("llm_trace", {}) or {}
    prompt_bundle = llm_result.get("prompt_bundle", {}) or {}
    llm_assumptions = llm_result.get("assumptions", []) or []

    registry = load_registry_from_folders()
    l1_state = build_l1_state(
        llm_keywords=llm_keywords,
        metrics=metrics,
        regimes=regimes,
        registry=registry,
    )

    sj_proposals = evaluate_scientific_justification(l1_state)
    sj_top = sj_proposals[0] if sj_proposals else None
    derived = build_derived_assumptions(measurement_validation, sj_top, registry)
    narrative_pack = render_system_narrative_ko(
        measurement_validation=measurement_validation,
        llm_pattern=llm_pattern,
        l1_state=l1_state,
        sj_proposals=sj_proposals,
        derived=derived,
    )
    artifact_dir = write_run_artifacts(
        raw_data=raw_data,
        measurement_validation=measurement_validation,
        llm_pattern=llm_pattern,
        llm_keywords=llm_keywords,
        llm_trace=llm_trace,
        prompt_bundle=prompt_bundle,
        assumptions=derived,
        l1_state=l1_state,
        sj_proposals=sj_proposals,
        metrics=metrics,
        regimes=regimes,
    )
    run_id = Path(artifact_dir).name
    chat_state = build_chat_response(Path(artifact_dir))

    reranked_sj_proposals = chat_state.get("reranked_sj_proposals") or sj_proposals
    reranked_narrative = str(chat_state.get("system_narrative") or narrative_pack["system_narrative"])
    reranked_summary = str(chat_state.get("과학적 정당화 제안") or narrative_pack["과학적 정당화 제안"])

    return {
        "measurement_validation": measurement_validation,
        "llm_pattern": llm_pattern,
        "llm_keywords": llm_keywords,
        "llm_trace": llm_trace,
        "llm_assumptions": llm_assumptions,
        "assumptions": derived.get("assumptions", []),
        "assumption_ids": derived.get("assumption_ids", []),
        "assumptions_meta": derived.get("assumptions_meta", {}),
        "l1_state": l1_state,
        "sj_proposals_base": sj_proposals,
        "sj_proposals": reranked_sj_proposals,
        "system_narrative": reranked_narrative,
        "L1 좌표 요약": narrative_pack["L1 좌표 요약"],
        "과학적 정당화 제안": reranked_summary,
        "metrics": metrics,
        "regimes": regimes,
        "run_id": run_id,
        "artifact_dir": artifact_dir,
        "conversation_state": chat_state,
        "domain_config": {
            "parser": "backend.measurement_validations.parser:parse_vi",
            "feature_extractor": "backend.domains.iv.features:infer_iv_features_from_numeric",
            "renderer": "backend.domains.iv.renderer:render_system_narrative_ko",
            "metadata_used": bool(metadata),
        },
    }


def sha256_text(text: str) -> str:
    """
    텍스트의 SHA-256 해시 문자열을 반환한다.
    """

    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def git_commit_or_unknown() -> str:
    """
    현재 작업 트리의 git 커밋 정보를 읽는다.
    """

    head_path = Path(__file__).resolve().parents[3] / ".git" / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_path = Path(__file__).resolve().parents[3] / ".git" / head.split(" ", 1)[1]
            if ref_path.is_file():
                return f"git:{ref_path.read_text(encoding='utf-8').strip()}"
        return f"git:{head}"
    except Exception:
        return "git:unknown"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    """
    JSON 파일을 UTF-8로 저장한다.
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_prompt_text(name: str, fallback: str) -> str:
    """
    프롬프트 파일을 읽고 없으면 fallback을 반환한다.
    """

    path = PROMPTS_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return fallback


def write_run_artifacts(
    raw_data: str,
    measurement_validation: Dict[str, Any],
    llm_pattern: str,
    llm_keywords: List[Dict[str, Any]],
    llm_trace: Dict[str, Any],
    prompt_bundle: Dict[str, Any],
    assumptions: Dict[str, Any],
    l1_state: Dict[str, Any],
    sj_proposals: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    regimes: List[Dict[str, Any]],
) -> str:
    """
    재현성 확보를 위해 실행 산출물을 runs 디렉터리에 저장한다.
    """

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}__{hashlib.sha256(raw_data.encode('utf-8')).hexdigest()[:10]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = prompt_bundle.get("system_prompt") or load_prompt_text("system_prompt_v1.md", "")
    user_prompt = prompt_bundle.get("user_prompt") or load_prompt_text("user_template_v1.md", "")

    write_json(run_dir / "derived.json", {
        "metrics": metrics,
        "regimes": regimes,
        "llm_pattern": llm_pattern,
        "llm_keywords": llm_keywords,
    })
    write_json(run_dir / "inference.json", {
        "measurement_validation": measurement_validation,
        "l1_state": l1_state,
        "assumptions": assumptions,
        "sj_proposals": sj_proposals,
    })
    write_json(run_dir / "sj_proposal.json", {"top": sj_proposals[0] if sj_proposals else None, "all": sj_proposals})
    write_json(run_dir / "llm_trace.json", {
        **llm_trace,
        "selected_ids": {
            "iv_regimes": l1_state.get("iv_regimes", []),
            "iv_features": l1_state.get("iv_features", []),
            "assumption_ids": assumptions.get("assumption_ids", []),
            "sj_claims": [item.get("claim_concept") for item in sj_proposals],
        },
        "evidence_fields": {
            "llm_keywords": llm_keywords,
            "metrics": metrics,
            "regimes": regimes,
        },
        "prompt_hashes": {
            "system_prompt_hash": sha256_text(system_prompt),
            "user_template_hash": sha256_text(user_prompt),
        },
    })

    (run_dir / "raw_input.txt").write_text(raw_data, encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "dataset_id": sha256_text(raw_data),
        "created_at_utc": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "code_commit": git_commit_or_unknown(),
        "ontology_commit": git_commit_or_unknown(),
        "lexicon_commit": git_commit_or_unknown(),
        "model": {
            "name": prompt_bundle.get("model", "none"),
            "temperature": prompt_bundle.get("temperature", 0.0),
            "top_p": prompt_bundle.get("top_p", 1.0),
        },
        "prompts": {
            "system_prompt_path": "prompts/system_prompt_v1.md",
            "system_prompt_hash": sha256_text(system_prompt),
            "user_template_path": "prompts/user_template_v1.md",
            "user_template_hash": sha256_text(user_prompt),
        },
        "artifacts": {
            "raw_input": "raw_input.txt",
            "derived": "derived.json",
            "inference": "inference.json",
            "sj_proposal": "sj_proposal.json",
            "llm_trace": "llm_trace.json",
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    ensure_memory_files(run_dir)
    return str(run_dir)
