from __future__ import annotations
from typing import Any, Dict, Tuple, Callable
import math

CheckResult = Tuple[bool, str]  # (ok, detail)
CheckFn = Callable[[Dict[str, Any], Dict[str, Any]], CheckResult]

def _is_finite(x: float) -> bool:
    return isinstance(x, float) and not (math.isnan(x) or math.isinf(x))

# ----------------------------
# Check functions
# ----------------------------
def min_points(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    min_n = int(check.get("min", 0))
    n = int(stats.get("n_points", 0))
    ok = n >= min_n
    return ok, f"n_points={n} (min {min_n})"

def max_nan_ratio(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    fields = check.get("fields", [])
    max_ratio = float(check.get("max", 0.0))
    details = []
    ok_all = True
    for f in fields:
        r = float(stats.get(f"{f}_nan_ratio", 1.0))
        ok = r <= max_ratio
        ok_all = ok_all and ok
        details.append(f"{f}_nan_ratio={r:.3f} (max {max_ratio})")
    return ok_all, ", ".join(details)

def min_unique(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    field = check.get("field")
    min_u = int(check.get("min", 0))
    u = int(stats.get(f"{field}_unique", 0))
    ok = u >= min_u
    return ok, f"{field}_unique={u} (min {min_u})"

def not_all_equal(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    field = check.get("field")
    u = int(stats.get(f"{field}_unique", 0))
    ok = u > 1
    return ok, f"{field}_unique={u} (>1 required)"

def finite_ratio(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    # optional: 너가 필요하면 stats에 미리 finite_ratio를 넣어두고 쓰면 됨
    fields = check.get("fields", [])
    min_ratio = float(check.get("min", 1.0))
    details = []
    ok_all = True
    for f in fields:
        r = float(stats.get(f"{f}_finite_ratio", 0.0))
        ok = r >= min_ratio
        ok_all = ok_all and ok
        details.append(f"{f}_finite_ratio={r:.3f} (min {min_ratio})")
    return ok_all, ", ".join(details)

def metadata_any_present(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    """
    stats["metadata"] = {...} 가 있다고 가정.
    """
    keys = check.get("keys", [])
    md = stats.get("metadata", {}) or {}
    found = [k for k in keys if k in md and md[k] not in (None, "")]
    ok = len(found) > 0
    return ok, f"found_keys={found}"

def classify_sweep_monotonicity(stats: Dict[str, Any], check: Dict[str, Any]) -> CheckResult:
    values = stats.get("V_series", []) or []
    finite = [float(x) for x in values if isinstance(x, (int, float)) and _is_finite(float(x))]
    if len(finite) < 3:
        return True, "insufficient_points_for_monotonicity"

    diffs = []
    for idx in range(1, len(finite)):
        delta = finite[idx] - finite[idx - 1]
        if abs(delta) > 1e-12:
            diffs.append(delta)

    if not diffs:
        return True, "constant_voltage_series"

    pos = sum(1 for x in diffs if x > 0)
    neg = sum(1 for x in diffs if x < 0)
    segments = 1
    last_sign = 1 if diffs[0] > 0 else -1
    for delta in diffs[1:]:
        sign = 1 if delta > 0 else -1
        if sign != last_sign:
            segments += 1
            last_sign = sign

    profile = "monotonic" if pos == 0 or neg == 0 else "segmented"
    return True, f"profile={profile}, sign_changes={max(0, segments - 1)}"


# ----------------------------
# Registry
# ----------------------------
CHECKS: Dict[str, CheckFn] = {
    "min_points": min_points,
    "max_nan_ratio": max_nan_ratio,
    "min_unique": min_unique,
    "not_all_equal": not_all_equal,
    "finite_ratio": finite_ratio,
    "metadata_any_present": metadata_any_present,
    "classify_sweep_monotonicity": classify_sweep_monotonicity,
}

def get_check(fn_name: str) -> CheckFn | None:
    return CHECKS.get(fn_name)
