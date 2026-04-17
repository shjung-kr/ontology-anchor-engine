"""
추세 분석 도메인 실행기.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.conversation.memory import ensure_memory_files
from backend.domains.trend.features import extract_signal_features, validate_input
from backend.domains.trend.parser import parse_xy
from backend.domains.trend.registry import list_interpretations, load_registry
from backend.domains.trend.renderer import render_narrative
from backend.user_storage import get_user_runs_dir


def evaluate_proposals(feature_ids: List[str]) -> List[Dict[str, Any]]:
    """
    추출된 feature와 interpretation 정의를 비교해 후보를 계산한다.
    """

    observed = set(feature_ids)
    proposals: List[Dict[str, Any]] = []

    for interpretation in list_interpretations():
        required = set(interpretation.get("required_features", []))
        matched = sorted(list(required.intersection(observed)))
        score = len(matched)
        if score <= 0:
            continue
        proposals.append(
            {
                "ontology_file": interpretation.get("_filename"),
                "claim_concept": interpretation.get("claim_concept"),
                "score": score,
                "matched_features": matched,
                "required_features": sorted(list(required)),
                "notes": interpretation.get("notes", {}),
            }
        )

    proposals.sort(key=lambda item: item["score"], reverse=True)
    return proposals


def write_artifacts(payload: Dict[str, Any], raw_data: str) -> str:
    """
    trend 도메인 실행 결과를 runs 디렉터리에 저장한다.
    """

    runs_dir = get_user_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}__trend__{hashlib.sha256(raw_data.encode('utf-8')).hexdigest()[:8]}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "raw_input.txt").write_text(raw_data, encoding="utf-8")
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ensure_memory_files(run_dir)
    return str(run_dir)


def run_trend_domain(raw_data: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    trend 도메인 분석 파이프라인을 실행한다.
    """

    _ = metadata
    x_values, y_values = parse_xy(raw_data)
    validation = validate_input(x_values, y_values)
    extracted = extract_signal_features(x_values, y_values) if validation.get("valid") else {"features": [], "evidence": [], "metrics": {}}
    proposals = evaluate_proposals(extracted.get("features", []))
    registry = load_registry()

    result: Dict[str, Any] = {
        "measurement_validation": validation,
        "metrics": extracted.get("metrics", {}),
        "l1_state": {
            "signal_features": [feature_id for feature_id in extracted.get("features", []) if feature_id in registry.get("signal_features", {})],
            "evidence": extracted.get("evidence", []),
        },
        "assumptions": [],
        "assumption_ids": [],
        "assumptions_meta": {},
        "sj_proposals": proposals,
        "system_narrative": render_narrative(validation, extracted, proposals),
        "domain_config": {
            "parser": "backend.domains.trend.parser:parse_xy",
            "feature_extractor": "backend.domains.trend.features:extract_signal_features",
            "renderer": "backend.domains.trend.renderer:render_narrative",
        },
    }
    result["artifact_dir"] = write_artifacts(result, raw_data)
    result["run_id"] = Path(result["artifact_dir"]).name
    return result
