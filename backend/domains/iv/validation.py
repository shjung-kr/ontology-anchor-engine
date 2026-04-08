"""
I-V 도메인 측정 유효성 검사 모듈.
"""

from typing import Any, Dict, List

from backend.domains.iv.common import get_ontology_root, load_json_files, unique_preserve_order
from backend.measurement_validations.infer import infer_measurement_conditions
from backend.measurement_validations.parser import build_stats, parse_vi
from backend.measurement_validations.runner import run_rules


def validate_measurement(raw_data: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    원시 I-V 데이터를 규칙 기반으로 검증한다.
    """

    metadata = dict(metadata or {})
    voltage_values, current_values = parse_vi(raw_data)
    stats = build_stats(voltage_values, current_values, metadata)
    measurement_conditions = infer_measurement_conditions(stats, metadata)

    ontology_root = get_ontology_root()
    rule_dir = ontology_root / "02_measurement_validations"
    all_rules: List[Dict[str, Any]] = []
    applied_rule_files: List[str] = []

    for path, obj in load_json_files(rule_dir):
        if isinstance(obj, dict) and isinstance(obj.get("rules"), list):
            all_rules.extend([rule for rule in obj["rules"] if isinstance(rule, dict)])
            applied_rule_files.append(path.name)
        elif isinstance(obj, dict):
            all_rules.append(obj)
            applied_rule_files.append(path.name)

    rule_result = run_rules(all_rules, stats, measurement_conditions)
    return {
        "valid": bool(rule_result.get("valid", False)),
        "applied_rules": rule_result.get("applied_rules", []),
        "errors": rule_result.get("errors", []),
        "warnings": rule_result.get("warnings", []),
        "info": rule_result.get("info", []),
        "stats": stats,
        "measurement_conditions": measurement_conditions,
        "emitted_assumptions": unique_preserve_order(rule_result.get("emitted_assumptions", [])),
        "applied_rule_files": unique_preserve_order(applied_rule_files),
    }
