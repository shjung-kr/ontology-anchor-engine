"""
C-V / EIS 도메인 실행기.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from backend.domains.cv_eis.common import get_runs_dir
from backend.domains.cv_eis.features import build_l1_state, extract_electrical_features
from backend.domains.cv_eis.parser import parse_measurement_table
from backend.domains.cv_eis.proposals import build_derived_assumptions, evaluate_interpretations
from backend.domains.cv_eis.registry import load_registry
from backend.domains.cv_eis.renderer import render_narrative
from backend.domains.cv_eis.validation import validate_measurement

try:
    from backend.conversation.memory import ensure_memory_files
except Exception:
    ensure_memory_files = None


def write_artifacts(payload: Dict[str, Any], raw_data: str) -> str:
    runs_dir = get_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}__cv_eis__{hashlib.sha256(raw_data.encode('utf-8')).hexdigest()[:8]}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "raw_input.txt").write_text(raw_data, encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if callable(ensure_memory_files):
        ensure_memory_files(run_dir)
    return str(run_dir)


def run_cv_eis_domain(raw_data: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    parsed = parse_measurement_table(raw_data)
    validation = validate_measurement(parsed, metadata=metadata)
    extracted = extract_electrical_features(parsed, metadata=metadata) if validation.get("valid") else {"features": [], "evidence": [], "metrics": {}}
    registry = load_registry()
    l1_state = build_l1_state(extracted, registry, validation)
    proposals = evaluate_interpretations(l1_state)
    derived = build_derived_assumptions(validation, proposals[0] if proposals else None, registry)

    result: Dict[str, Any] = {
        "measurement_validation": validation,
        "parsed_measurement": {
            "measurement_kind": parsed.get("measurement_kind"),
            "columns": parsed.get("columns", []),
            "stats": parsed.get("stats", {}),
        },
        "metrics": extracted.get("metrics", {}),
        "l1_state": l1_state,
        "assumptions": derived.get("assumptions", []),
        "assumption_ids": derived.get("assumption_ids", []),
        "assumptions_meta": derived.get("assumptions_meta", {}),
        "sj_proposals": proposals,
        "system_narrative": render_narrative(validation, extracted, proposals),
        "domain_config": {
            "parser": "backend.domains.cv_eis.parser:parse_measurement_table",
            "feature_extractor": "backend.domains.cv_eis.features:extract_electrical_features",
            "renderer": "backend.domains.cv_eis.renderer:render_narrative",
        },
    }
    result["artifact_dir"] = write_artifacts(result, raw_data)
    result["run_id"] = Path(result["artifact_dir"]).name
    return result
