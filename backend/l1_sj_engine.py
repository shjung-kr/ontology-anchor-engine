# backend/l1_sj_engine.py
import os
import json
import math
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from backend.domains.iv.features import (
    build_l1_state as iv_build_l1_state,
    infer_iv_features_from_numeric as iv_infer_iv_features_from_numeric,
)
from backend.domains.iv.proposals import (
    build_derived_assumptions as iv_build_derived_assumptions,
    evaluate_scientific_justification as iv_evaluate_scientific_justification,
)
from backend.domains.iv.registry import load_registry_from_folders as iv_load_registry_from_folders
from backend.domains.iv.renderer import render_system_narrative_ko as iv_render_system_narrative_ko
from backend.domains.iv.runner import run_iv_domain
from backend.domains.iv.validation import validate_measurement as iv_validate_measurement
from backend.llm_adapter import llm_analyze_numeric
from backend.measurement_validations.infer import infer_measurement_conditions
from backend.measurement_validations.parser import parse_vi, build_stats
from backend.measurement_validations.runner import run_rules
from backend.user_storage import get_user_runs_dir

# -----------------------------
# Paths (프로젝트 폴더 구조에 맞게 필요시만 수정)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
ONTO_BASE = os.path.join(BASE_DIR, "ontology")         # backend/ontology
PROMPTS_DIR = Path(BASE_DIR).parent / "prompts"

IV_REGIMES_DIR = os.path.join(ONTO_BASE, "01_iv_regimes")
IV_FEATURES_DIR = os.path.join(ONTO_BASE, "02_iv_features")
ONTOLOGY_DIR = os.path.join(ONTO_BASE, "04_scientific_justification")

# ✅ assumptions / validation rules 폴더
ASSUMPTIONS_DIRS = [
    os.path.join(ONTO_BASE, "00_lexicon"),
    os.path.join(ONTO_BASE, "03_assumptions"),
    os.path.join(ONTO_BASE, "02_measurement_validations"),
]
MEASUREMENT_RULE_DIR = os.path.join(ONTO_BASE, "02_measurement_validations")

# =========================================================
# 0) Helpers
# =========================================================
def _unique_preserve_order(xs: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in xs:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _load_json_files(dir_path: str) -> List[Tuple[str, Dict[str, Any]]]:
    out: List[Tuple[str, Dict[str, Any]]] = []
    if not os.path.isdir(dir_path):
        return out
    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(dir_path, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                out.append((path, json.load(f)))
        except Exception:
            continue
    return out


def _extract_statement_from_definition(obj: Dict[str, Any]) -> Optional[str]:
    statement = obj.get("statement")
    if isinstance(statement, str) and statement.strip():
        return statement.strip()

    definition = obj.get("definition")
    if isinstance(definition, dict):
        for lang in ("ko", "en"):
            val = definition.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()
    elif isinstance(definition, str) and definition.strip():
        return definition.strip()

    labels = obj.get("labels")
    if isinstance(labels, dict):
        for lang in ("ko", "en"):
            val = labels.get(lang)
            if isinstance(val, str) and val.strip():
                return val.strip()

    for key in ("description", "label", "summary"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return None


def _coerce_assumption_definition(
    assumption_id: str,
    obj: Dict[str, Any],
    source_file: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(assumption_id, str) or not assumption_id.strip() or not isinstance(obj, dict):
        return None

    statement = _extract_statement_from_definition(obj)
    if not statement:
        return None

    impact_axis = obj.get("impact_axis")
    if not isinstance(impact_axis, list):
        impact_axis = []

    card = {
        "assumption_id": assumption_id.strip(),
        "statement": statement,
        "impact_axis": impact_axis,
        "_source_file": source_file,
    }

    labels = obj.get("labels")
    if isinstance(labels, dict):
        card["labels"] = labels

    for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
        if extra_key in obj:
            card[extra_key] = obj[extra_key]

    return card


# =========================================================
# 0) Registry loader (안정적으로 id만 모음)
# =========================================================
def load_registry_from_folders() -> Dict[str, Any]:
    return iv_load_registry_from_folders()


# =========================================================
# 1) Measurement validation (✅ assumptions는 여기서만 "불러다 씀")
# =========================================================
def validate_measurement(raw_data: str) -> Dict[str, Any]:
    return iv_validate_measurement(raw_data, metadata={})


def _parse_vi_pairs(raw_data: str) -> List[Tuple[float, float]]:
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
    return pairs


# =========================================================
# 2) B 방식: regimes/metrics -> iv_features
# =========================================================
def infer_iv_features_from_numeric(metrics: Dict[str, Any], regimes: List[Dict[str, Any]]) -> List[str]:
    return iv_infer_iv_features_from_numeric(metrics, regimes)


# =========================================================
# 3) L1 state builder (B 방식)
# =========================================================
def build_l1_state(
    llm_keywords: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    regimes: List[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    state = {
        "iv_regimes": set(),
        "iv_features": set(),
        "evidence": [],
        "rejected_ids": [],
        "metrics": metrics or {},
        "regimes": regimes or [],
    }

    name_to_regime_id = {
        "low_|V|": "iv_regimes.low_field_regime",
        "high_|V|": "iv_regimes.high_field_regime",
    }
    for r in regimes or []:
        rid = name_to_regime_id.get(r.get("name", ""))
        if not rid:
            continue
        if rid in registry.get("iv_regimes", {}):
            state["iv_regimes"].add(rid)
        else:
            state["rejected_ids"].append(rid)

    numeric_feats = infer_iv_features_from_numeric(metrics or {}, regimes or [])
    for f in numeric_feats:
        if f in registry.get("iv_features", {}):
            state["iv_features"].add(f)
        else:
            state["rejected_ids"].append(f)

    for entry in llm_keywords or []:
        ev = entry.get("evidence")
        if ev:
            state["evidence"].append(ev)

    return {
        "iv_regimes": sorted(list(state["iv_regimes"])),
        "iv_features": sorted(list(state["iv_features"])),
        "evidence": state["evidence"],
        "rejected_ids": state["rejected_ids"],
        "metrics": state["metrics"],
        "regimes": state["regimes"],
    }


def _normalize_assumption_card(assumption_id: str, registry: Dict[str, Any]) -> Dict[str, Any]:
    ref = registry.get("assumptions", {}).get(assumption_id)
    if isinstance(ref, dict):
        card = {
            "assumption_id": assumption_id,
            "statement": ref.get("statement", assumption_id),
            "impact_axis": ref.get("impact_axis", []),
        }
        if isinstance(ref.get("labels"), dict):
            card["labels"] = ref["labels"]
        for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
            if extra_key in ref:
                card[extra_key] = ref[extra_key]
        return card

    return {
        "assumption_id": assumption_id,
        "statement": assumption_id,
        "impact_axis": [],
    }


# =========================================================
# 4) SJ ontology evaluation (✅ assumptions도 SJ에서 불러다 씀)
# =========================================================
def evaluate_scientific_justification(l1_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return iv_evaluate_scientific_justification(l1_state)


# =========================================================
# 5) Derived assumptions (✅ validation + SJ assumptions merge)
# =========================================================
def build_derived_assumptions(
    measurement_validation: Dict[str, Any],
    sj_top: Optional[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    v_assumptions = measurement_validation.get("emitted_assumptions", []) or []
    sj_assumptions = (sj_top or {}).get("sj_assumptions", []) or []
    merged = _unique_preserve_order(list(v_assumptions) + list(sj_assumptions))
    cards = [_normalize_assumption_card(aid, registry) for aid in merged]

    return {
        "assumptions": cards,
        "assumption_ids": merged,
        "assumptions_meta": {
            "from_validation": list(v_assumptions),
            "from_sj": list(sj_assumptions),
        },
    }


# =========================================================
# 6) Simple narrative renderer (프론트 출력용)
# =========================================================
def render_system_narrative_ko(
    measurement_validation: Dict[str, Any],
    llm_pattern: str,
    l1_state: Dict[str, Any],
    sj_proposals: List[Dict[str, Any]],
    derived: Dict[str, Any],
) -> Dict[str, str]:
    return iv_render_system_narrative_ko(
        measurement_validation=measurement_validation,
        llm_pattern=llm_pattern,
        l1_state=l1_state,
        sj_proposals=sj_proposals,
        derived=derived,
    )


# =========================================================
# ✅ Entrypoint expected by backend/server.py
# =========================================================
def run_l1_engine(raw_data: str) -> Dict[str, Any]:
    return run_iv_domain(raw_data=raw_data, metadata={})


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _git_commit_or_unknown() -> str:
    head_path = Path(BASE_DIR).parent / ".git" / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_path = Path(BASE_DIR).parent / ".git" / head.split(" ", 1)[1]
            if ref_path.is_file():
                return f"git:{ref_path.read_text(encoding='utf-8').strip()}"
        return f"git:{head}"
    except Exception:
        return "git:unknown"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_prompt_text(name: str, fallback: str) -> str:
    path = PROMPTS_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return fallback


def _write_run_artifacts(
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
    runs_dir = get_user_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}__{hashlib.sha256(raw_data.encode('utf-8')).hexdigest()[:10]}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = prompt_bundle.get("system_prompt") or _load_prompt_text("system_prompt_v1.md", "")
    user_prompt = prompt_bundle.get("user_prompt") or _load_prompt_text("user_template_v1.md", "")

    _write_json(run_dir / "derived.json", {
        "metrics": metrics,
        "regimes": regimes,
        "llm_pattern": llm_pattern,
        "llm_keywords": llm_keywords,
    })
    _write_json(run_dir / "inference.json", {
        "measurement_validation": measurement_validation,
        "l1_state": l1_state,
        "assumptions": assumptions,
        "sj_proposals": sj_proposals,
    })
    _write_json(run_dir / "sj_proposal.json", {
        "top": sj_proposals[0] if sj_proposals else None,
        "all": sj_proposals,
    })
    _write_json(run_dir / "llm_trace.json", {
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
            "system_prompt_hash": _sha256_text(system_prompt),
            "user_template_hash": _sha256_text(user_prompt),
        },
    })

    (run_dir / "raw_input.txt").write_text(raw_data, encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "dataset_id": _sha256_text(raw_data),
        "created_at_utc": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "code_commit": _git_commit_or_unknown(),
        "ontology_commit": _git_commit_or_unknown(),
        "lexicon_commit": _git_commit_or_unknown(),
        "model": {
            "name": prompt_bundle.get("model", "none"),
            "temperature": prompt_bundle.get("temperature", 0.0),
            "top_p": prompt_bundle.get("top_p", 1.0),
        },
        "prompts": {
            "system_prompt_path": "prompts/system_prompt_v1.md",
            "system_prompt_hash": _sha256_text(system_prompt),
            "user_template_path": "prompts/user_template_v1.md",
            "user_template_hash": _sha256_text(user_prompt),
        },
        "artifacts": {
            "raw_input": "raw_input.txt",
            "derived": "derived.json",
            "inference": "inference.json",
            "sj_proposal": "sj_proposal.json",
            "llm_trace": "llm_trace.json",
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    return str(run_dir)
