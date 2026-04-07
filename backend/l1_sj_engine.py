# backend/l1_sj_engine.py
import os
import json
import math
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from backend.llm_adapter import llm_analyze_numeric
from backend.measurement_validations.infer import infer_measurement_conditions
from backend.measurement_validations.parser import parse_vi, build_stats
from backend.measurement_validations.runner import run_rules

# -----------------------------
# Paths (프로젝트 폴더 구조에 맞게 필요시만 수정)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
ONTO_BASE = os.path.join(BASE_DIR, "ontology")         # backend/ontology
RUNS_DIR = Path(BASE_DIR) / "runs"
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
    reg = {"iv_regimes": {}, "iv_features": {}, "assumptions": {}}

    def _ingest_dir(dir_path: str, key: str):
        if not os.path.isdir(dir_path):
            return
        for path, obj in _load_json_files(dir_path):
            oid = obj.get("id") or obj.get("ontology_id")
            if isinstance(oid, str) and oid.strip():
                reg[key][oid.strip()] = True

    def _ingest_assumptions_dir(dir_path: str):
        """
        assumptions 레지스트리는 '정의'를 담아야 하므로 True가 아니라 dict를 저장.
        지원 패턴:
          1) 파일 자체가 assumption 정의: {"assumption_id": "...", "statement": "...", ...}
          2) id가 "assumption.A_MAG_NOISE" 형태: {"id":"assumption.A_MAG_NOISE", ...}
          3) assumptions/items 리스트 포함:
             - {"assumptions":[ {...}, {...} ]}
             - {"items":[ {...}, {...} ]} (id 기반 lexicon 스타일)
        """
        if not os.path.isdir(dir_path):
            return

        def _register_one(a: Dict[str, Any], source_file: str):
            if not isinstance(a, dict):
                return

            # assumption_id 결정
            aid = a.get("assumption_id")
            if not (isinstance(aid, str) and aid.strip()):
                _id = a.get("id") or a.get("ontology_id")
                if isinstance(_id, str) and _id.strip():
                    # (A) "assumption.A_X" -> "A_X"
                    if _id.strip().lower().startswith("assumption."):
                        aid = _id.split(".", 1)[1]
                    # (B) "measurement_assumption.xxx" / "fn_assumption.xxx" 등은 그대로 id로 써도 됨
                    else:
                        aid = _id.strip()

            if not (isinstance(aid, str) and aid.strip()):
                return
            aid = aid.strip()
            card = _coerce_assumption_definition(aid, a, source_file)
            if card:
                reg["assumptions"][aid] = card

        for path, obj in _load_json_files(dir_path):
            if isinstance(obj, dict):
                # dict-mapping lexicon 스타일:
                # { "physical_assumption.xxx": {...}, ... }
                for k, v in obj.items():
                    if isinstance(k, str) and isinstance(v, dict):
                        card = _coerce_assumption_definition(k, v, path)
                        if card:
                            reg["assumptions"][k] = card

            # (A) 단일 assumption일 수 있음
            looks_like_single = False
            if isinstance(obj, dict):
                if isinstance(obj.get("assumption_id"), str) and obj["assumption_id"].strip():
                    looks_like_single = True
                else:
                    _id = obj.get("id") or obj.get("ontology_id")
                    if isinstance(_id, str) and _id.strip():
                        looks_like_single = True

            if looks_like_single:
                _register_one(obj, path)

            # (B) 컨테이너일 수 있음
            if isinstance(obj, dict) and isinstance(obj.get("assumptions"), list):
                for item in obj["assumptions"]:
                    _register_one(item, path)

            # (C) lexicon style: {"category": "...", "items":[...]}
            if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                for item in obj["items"]:
                    _register_one(item, path)

    _ingest_dir(IV_REGIMES_DIR, "iv_regimes")
    _ingest_dir(IV_FEATURES_DIR, "iv_features")

    for d in ASSUMPTIONS_DIRS:
        _ingest_assumptions_dir(d)

    return reg


# =========================================================
# 1) Measurement validation (✅ assumptions는 여기서만 "불러다 씀")
# =========================================================
def validate_measurement(raw_data: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    V, I = parse_vi(raw_data)
    stats = build_stats(V, I, metadata)
    measurement_conditions = infer_measurement_conditions(stats, metadata)

    all_rules: List[Dict[str, Any]] = []
    applied_rule_files: List[str] = []
    for path, obj in _load_json_files(MEASUREMENT_RULE_DIR):
        if isinstance(obj, dict) and isinstance(obj.get("rules"), list):
            all_rules.extend([r for r in obj["rules"] if isinstance(r, dict)])
            applied_rule_files.append(os.path.basename(path))
        elif isinstance(obj, dict):
            all_rules.append(obj)
            applied_rule_files.append(os.path.basename(path))

    rule_result = run_rules(all_rules, stats, measurement_conditions)
    return {
        "valid": bool(rule_result.get("valid", False)),
        "applied_rules": rule_result.get("applied_rules", []),
        "errors": rule_result.get("errors", []),
        "warnings": rule_result.get("warnings", []),
        "info": rule_result.get("info", []),
        "stats": stats,
        "measurement_conditions": measurement_conditions,
        "emitted_assumptions": _unique_preserve_order(rule_result.get("emitted_assumptions", [])),
        "applied_rule_files": _unique_preserve_order(applied_rule_files),
    }


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
    feats: List[str] = []
    if not regimes:
        return []

    low = next((r for r in regimes if r.get("name") == "low_|V|"), None)
    high = next((r for r in regimes if r.get("name") == "high_|V|"), None)

    slope_ref: Optional[float] = None
    if low and low.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(low.get("mean_slope_log_absI_per_logV"))
    elif high and high.get("mean_slope_log_absI_per_logV") is not None:
        slope_ref = float(high.get("mean_slope_log_absI_per_logV"))

    if slope_ref is not None:
        if 0.85 <= slope_ref <= 1.15:
            feats += ["iv_features.linear_iv_regime", "iv_features.constant_conductance_behavior"]
        elif slope_ref >= 1.20:
            feats.append("iv_features.nonlinear_iv_regime")

    if high:
        ddec = float(high.get("delta_decades_robust", 0.0) or 0.0)
        ms = float(high.get("mean_slope_log_absI_per_logV", 0.0) or 0.0)
        if ddec >= 2.0 and ms >= 2.0:
            feats.append("iv_features.field_enhanced_current")
            feats.append("iv_features.nonlinear_iv_regime")

    return _unique_preserve_order(feats)


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
    proposals: List[Dict[str, Any]] = []
    if not os.path.isdir(ONTOLOGY_DIR):
        return proposals

    for fname in os.listdir(ONTOLOGY_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(ONTOLOGY_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                sj = json.load(f).get("scientific_justification", {})
        except Exception:
            continue

        claim = sj.get("claim_concept")
        required_features = set(sj.get("required_features", []))
        matched = required_features.intersection(set(l1_state.get("iv_features", [])))
        score = len(matched)

        if score > 0:
            proposals.append({
                "ontology_file": fname,
                "claim_concept": claim,
                "mechanism_id": claim,
                "score": score,
                "required_features": sorted(list(required_features)),
                "observed_features": sj.get("observed_features", []) or [],
                "matched_features": sorted(list(matched)),
                "explanation_notes": sj.get("explanation_notes", {}),
                # ✅ SJ가 이미 가지고 있는 assumption id 리스트를 그대로 유지
                "sj_assumptions": sj.get("assumptions", []) or [],
                "mechanism_by_regime": sj.get("mechanism_by_regime", []) or [],
            })

    proposals.sort(key=lambda x: x["score"], reverse=True)
    return proposals


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
    regimes = l1_state.get("iv_regimes", [])
    feats = l1_state.get("iv_features", [])

    l1_summary = "【L1 관측 좌표 요약】\n"
    l1_summary += f"- iv_regimes: {', '.join(regimes) if regimes else '(none)'}\n"
    l1_summary += f"- iv_features: {', '.join(feats) if feats else '(none)'}\n"

    if sj_proposals:
        top = sj_proposals[0]
        sj_text = f"최상위 제안: {top.get('ontology_file')} (score={top.get('score')})"
    else:
        sj_text = "제안 가능한 과학적 정당화가 발견되지 않았습니다."

    assumps = derived.get("assumptions", []) or []
    assump_ids = [a.get("assumption_id", "") for a in assumps if isinstance(a, dict)]
    a_text = f"- assumptions: {', '.join(assump_ids) if assump_ids else '(none)'}"

    narrative = (
        f"{l1_summary}\n"
        f"【LLM 관측 패턴】\n{llm_pattern or '(none)'}\n\n"
        f"【과학적 정당화 제안】\n{sj_text}\n\n"
        f"【가정(assumptions)】\n{a_text}\n"
    )

    return {
        "L1 좌표 요약": l1_summary.strip(),
        "과학적 정당화 제안": sj_text,
        "system_narrative": narrative.strip(),
    }


# =========================================================
# ✅ Entrypoint expected by backend/server.py
# =========================================================
def run_l1_engine(raw_data: str) -> Dict[str, Any]:
    # 1) measurement validation
    measurement_validation = validate_measurement(raw_data)

    # 2) llm adapter (pattern/keywords/metrics/regimes)
    llm_result = llm_analyze_numeric(raw_data)
    llm_pattern = str(llm_result.get("pattern") or "")
    llm_keywords = llm_result.get("keywords", []) or []
    metrics = llm_result.get("metrics", {}) or {}
    regimes = llm_result.get("regimes", []) or []
    llm_trace = llm_result.get("llm_trace", {}) or {}
    prompt_bundle = llm_result.get("prompt_bundle", {}) or {}

    # ✅ 더 이상 llm_result["assumptions"]를 신뢰하지 않음(필요하면 참고용으로만 유지)
    llm_assumptions = llm_result.get("assumptions", []) or []

    # 3) registry
    registry = load_registry_from_folders()

    # 4) l1_state
    l1_state = build_l1_state(
        llm_keywords=llm_keywords,
        metrics=metrics,
        regimes=regimes,
        registry=registry,
    )

    # 5) SJ proposals
    sj_proposals = evaluate_scientific_justification(l1_state)
    sj_top = sj_proposals[0] if sj_proposals else None

    # 6) ✅ derived assumptions = validation + sj
    derived = build_derived_assumptions(measurement_validation, sj_top, registry)

    # 7) narrative
    narrative_pack = render_system_narrative_ko(
        measurement_validation=measurement_validation,
        llm_pattern=llm_pattern,
        l1_state=l1_state,
        sj_proposals=sj_proposals,
        derived=derived,
    )

    return {
        "measurement_validation": measurement_validation,
        "llm_pattern": llm_pattern,
        "llm_keywords": llm_keywords,
        "llm_trace": llm_trace,
        # ✅ 프론트가 기대한다면 유지(참고용)
        "llm_assumptions": llm_assumptions,
        # ✅ 이제 이게 "공식" assumptions 출력
        "assumptions": derived.get("assumptions", []),
        "assumption_ids": derived.get("assumption_ids", []),
        "assumptions_meta": derived.get("assumptions_meta", {}),
        "l1_state": l1_state,
        "sj_proposals": sj_proposals,
        "system_narrative": narrative_pack["system_narrative"],
        "L1 좌표 요약": narrative_pack["L1 좌표 요약"],
        "과학적 정당화 제안": narrative_pack["과학적 정당화 제안"],
        "metrics": metrics,
        "regimes": regimes,
        "artifact_dir": _write_run_artifacts(
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
        ),
    }


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
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}__{hashlib.sha256(raw_data.encode('utf-8')).hexdigest()[:10]}"
    run_dir = RUNS_DIR / run_id
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
