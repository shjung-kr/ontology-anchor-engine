from __future__ import annotations
from typing import Any, Dict, List
from .checks import get_check

def rule_applies(rule: Dict[str, Any], measurement_conditions: List[str]) -> bool:
    applies_to = rule.get("applies_to", ["*"])
    if "*" in applies_to:
        return True
    return any(c in measurement_conditions for c in applies_to)

def run_rules(
    rules: List[Dict[str, Any]],
    stats: Dict[str, Any],
    measurement_conditions: List[str]
) -> Dict[str, Any]:
    applied: List[str] = []
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    info: List[Dict[str, Any]] = []
    emitted_assumptions: List[str] = []

    for rule in rules:
        rid = rule.get("validation_id") or rule.get("id") or "validation.unknown"
        if not rule_applies(rule, measurement_conditions):
            continue

        applied.append(rid)

        level = rule.get("level", "warn")
        checks = rule.get("checks", [])

        failed = []
        for chk in checks:
            fn_name = chk.get("fn")
            fn = get_check(fn_name) if fn_name else None
            if fn is None:
                # 체크 이름이 잘못된 경우: 일단 warn으로 기록
                failed.append(f"unknown_check_fn={fn_name}")
                continue

            ok, detail = fn(stats, chk)
            if not ok:
                failed.append(f"{fn_name}: {detail}")

        if failed:
            payload = {
                "validation_id": rid,
                "level": level,
                "failures": failed,
                "reason": (rule.get("on_fail", {}) or {}).get("reason", "")
            }
            if level == "error":
                errors.append(payload)
            elif level == "info":
                info.append(payload)
            else:
                warnings.append(payload)
        else:
            # pass면 emit 같은 것만 info로 남김(옵션)
            emit = (rule.get("on_pass", {}) or {}).get("emit")
            if emit:
                info.append({"validation_id": rid, "level": "info", "pass": True, "emit": emit})
            for assumption_id in rule.get("emitted_assumptions", []) or []:
                if isinstance(assumption_id, str) and assumption_id.strip():
                    emitted_assumptions.append(assumption_id.strip())

    return {
        "applied_rules": applied,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "valid": len(errors) == 0,
        "emitted_assumptions": emitted_assumptions,
    }
