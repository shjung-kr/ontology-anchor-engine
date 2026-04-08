"""
추세 분석 도메인 ontology 로더.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


DOMAIN_ROOT = Path(__file__).resolve().parents[2] / "ontology" / "trend"


def load_registry() -> Dict[str, Any]:
    """
    trend 도메인 feature registry를 로드한다.
    """

    features: Dict[str, bool] = {}
    assumptions: Dict[str, Dict[str, Any]] = {}

    feature_dir = DOMAIN_ROOT / "02_signal_features"
    for path in sorted(feature_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        feature_id = payload.get("id") or payload.get("feature_id")
        if isinstance(feature_id, str) and feature_id.strip():
            features[feature_id.strip()] = True

    assumption_dir = DOMAIN_ROOT / "00_lexicon"
    for path in sorted(assumption_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.startswith("trend_assumption."):
                assumptions[item_id] = item

    return {"signal_features": features, "assumptions": assumptions}


def list_interpretations() -> List[Dict[str, Any]]:
    """
    trend 도메인 interpretation 파일 목록을 반환한다.
    """

    interpretations: List[Dict[str, Any]] = []
    interp_dir = DOMAIN_ROOT / "04_interpretations"
    for path in sorted(interp_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        interpretation = payload.get("interpretation")
        if isinstance(interpretation, dict):
            interpretation["_filename"] = path.name
            interpretations.append(interpretation)
    return interpretations
