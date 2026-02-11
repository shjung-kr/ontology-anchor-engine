# backend/l1_sj_engine.py
import os
import json
import math
import re
from typing import Dict, Any, List, Tuple, Optional

from backend.llm_adapter import llm_analyze_numeric

# -----------------------------
# Paths (프로젝트 폴더 구조에 맞게 필요시만 수정)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
ONTO_BASE = os.path.join(BASE_DIR, "ontology")         # backend/ontology

IV_REGIMES_DIR = os.path.join(ONTO_BASE, "01_iv_regimes")
IV_FEATURES_DIR = os.path.join(ONTO_BASE, "02_iv_features")
ONTOLOGY_DIR = os.path.join(ONTO_BASE, "04_scientific_justification")

# ✅ assumptions / validation rules 폴더 (프로젝트에 맞게 조정)
ASSUMPTIONS_DIRS = [
    os.path.join(ONTO_BASE, "03_assumptions"),                 # 권장
    os.path.join(ONTO_BASE, "02_measurement_validations"),      # rule+assumption 같이 둘 수도 있으면
]
MEASUREMENT_RULE_DIR = os.path.join(ONTO_BASE, "02_measurement_validation")

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

            # statement/definition 결정
            statement = a.get("statement")
            if not (isinstance(statement, str) and statement.strip()):
                # lexicon 스타일이면 definition.ko/en 또는 labels.ko/en에서 뽑기
                if isinstance(a.get("definition"), dict):
                    ko = a["definition"].get("ko")
                    en = a["definition"].get("en")
                    if isinstance(ko, str) and ko.strip():
                        statement = ko
                    elif isinstance(en, str) and en.strip():
                        statement = en
                if not (isinstance(statement, str) and statement.strip()):
                    if isinstance(a.get("labels"), dict):
                        ko = a["labels"].get("ko")
                        en = a["labels"].get("en")
                        if isinstance(ko, str) and ko.strip():
                            statement = ko
                        elif isinstance(en, str) and en.strip():
                            statement = en

            if not (isinstance(statement, str) and statement.strip()):
                # fallback 후보
                for k in ("description", "label", "summary"):
                    v = a.get(k)
                    if isinstance(v, str) and v.strip():
                        statement = v
                        break

            # impact_axis
            impact_axis = a.get("impact_axis")
            if not isinstance(impact_axis, list):
                impact_axis = []

            if not (isinstance(statement, str) and statement.strip()):
                return

            card = {
                "assumption_id": aid,
                "statement": statement.strip(),
                "impact_axis": impact_axis,
                "_source_file": source_file,
            }

            for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
                if extra_key in a:
                    card[extra_key] = a[extra_key]

            reg["assumptions"][aid] = card

        for path, obj in _load_json_files(dir_path):
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
    """
    기존처럼 stats/conditions를 채우고,
    추가로 measurement_validation rule ontology에서 emitted_assumptions를 "불러다" 적용한다.
    """
    pairs = _parse_vi_pairs(raw_data)

    n = len(pairs)
    v_vals = [v for v, i in pairs if math.isfinite(v)]
    i_vals = [i for v, i in pairs if math.isfinite(i)]

    def _nan_ratio(arr: List[float]) -> float:
        if not arr:
            return 1.0
        nan = sum(1 for x in arr if not math.isfinite(x))
        return nan / max(1, len(arr))

    stats = {
        "n_points": n,
        "V_nan_ratio": float(_nan_ratio(v_vals)),
        "I_nan_ratio": float(_nan_ratio(i_vals)),
        "V_finite_ratio": float(sum(1 for x in v_vals if math.isfinite(x)) / max(1, len(v_vals))) if v_vals else 0.0,
        "I_finite_ratio": float(sum(1 for x in i_vals if math.isfinite(x)) / max(1, len(i_vals))) if i_vals else 0.0,
        "V_unique": len(set(v_vals)) if v_vals else 0,
        "I_unique": len(set(i_vals)) if i_vals else 0,
        "metadata": {},
    }

    valid = True
    errors: List[str] = []
    warnings: List[str] = []
    applied_rules: List[str] = []

    if n < 10:
        valid = False
        errors.append("too_few_points")
        applied_rules.append("validation.too_few_points")

    if stats["V_finite_ratio"] < 0.95 or stats["I_finite_ratio"] < 0.95:
        valid = False
        errors.append("non_finite_values_present")
        applied_rules.append("validation.non_finite")

    if valid:
        applied_rules.append("validation.unknown")  # 기존 UI 기대값 유지용

    measurement_conditions: List[str] = ["measurement_conditions.sweep_iv"] if n >= 10 else []

    # ✅ rule ontology에서 emitted_assumptions를 "불러다" 적용
    emitted_assumptions: List[str] = []
    applied_rule_files: List[str] = []
    if os.path.isdir(MEASUREMENT_RULE_DIR):
        for path, obj in _load_json_files(MEASUREMENT_RULE_DIR):
            # rule 스키마 다양성 대비: {"id":..., "emitted_assumptions":[...]} 또는 컨테이너
            rules: List[Dict[str, Any]] = []
            if isinstance(obj, dict) and obj.get("id") and ("criteria" in obj or "emitted_assumptions" in obj):
                rules = [obj]
            elif isinstance(obj, dict) and isinstance(obj.get("rules"), list):
                rules = [r for r in obj["rules"] if isinstance(r, dict)]
            else:
                rules = []

            # 최소 구현: criteria 없이 emitted_assumptions만 있으면 "항상 적용"하지 않음.
            # 필요하면 여기서 criteria를 stats 기반으로 평가하도록 확장 가능.
            for r in rules:
                ea = r.get("emitted_assumptions")
                if not isinstance(ea, list) or not ea:
                    continue
                # 여기서는 간단히 "validation.valid일 때만" 적용 예시
                # (원하면 rule.criteria 평가 로직을 붙이면 됨)
                if valid:
                    emitted_assumptions.extend([str(x) for x in ea if isinstance(x, str)])
                    applied_rule_files.append(os.path.basename(path))

    return {
        "valid": bool(valid),
        "applied_rules": applied_rules,
        "errors": errors,
        "warnings": warnings,
        "info": [],
        "stats": stats,
        "measurement_conditions": measurement_conditions,
        # ✅ 추가: validation이 내보낸 assumptions
        "emitted_assumptions": _unique_preserve_order(emitted_assumptions),
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
                "score": score,
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
) -> Dict[str, Any]:
    v_assumptions = measurement_validation.get("emitted_assumptions", []) or []
    sj_assumptions = (sj_top or {}).get("sj_assumptions", []) or []
    merged = _unique_preserve_order(list(v_assumptions) + list(sj_assumptions))

    return {
        "assumptions": merged,
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
    a_text = f"- assumptions: {', '.join(assumps) if assumps else '(none)'}"

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
    derived = build_derived_assumptions(measurement_validation, sj_top)

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
        # ✅ 프론트가 기대한다면 유지(참고용)
        "llm_assumptions": llm_assumptions,
        # ✅ 이제 이게 "공식" assumptions 출력
        "assumptions": derived.get("assumptions", []),
        "assumptions_meta": derived.get("assumptions_meta", {}),
        "l1_state": l1_state,
        "sj_proposals": sj_proposals,
        "system_narrative": narrative_pack["system_narrative"],
        "L1 좌표 요약": narrative_pack["L1 좌표 요약"],
        "과학적 정당화 제안": narrative_pack["과학적 정당화 제안"],
        "metrics": metrics,
        "regimes": regimes,
    }
