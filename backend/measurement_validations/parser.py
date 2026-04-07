from __future__ import annotations
from typing import List, Tuple, Dict, Any
import math
import re

def _to_float(x: str) -> float:
    try:
        s = x.strip()
        if s == "" or s.lower() in ("nan", "none", "null"):
            return float("nan")
        return float(s)
    except Exception:
        return float("nan")

def _is_finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))

def parse_vi(raw_data: str) -> Tuple[List[float], List[float]]:
    """
    Parse CSV-like / whitespace-separated text into V, I arrays.
    Supports headerless data and skips obvious header lines.
    """
    lines = [ln.strip() for ln in raw_data.splitlines() if ln.strip()]
    if not lines:
        return [], []

    def split_parts(line: str) -> List[str]:
        return [p.strip() for p in re.split(r"[,\s\t]+", line) if p.strip()]

    header = [h.strip().lower() for h in split_parts(lines[0])]

    def find_col(cands: List[str]):
        for c in cands:
            if c in header:
                return header.index(c)
        return None

    v_idx = find_col(["v", "voltage", "bias", "vbias", "v_app", "vapp", "volts"])
    i_idx = find_col(["i", "current", "id", "is", "i_meas", "imeas", "amps", "a"])

    if v_idx is None or i_idx is None:
        # fallback: first two columns
        v_idx, i_idx = 0, 1

    V: List[float] = []
    I: List[float] = []

    start_idx = 1 if header else 0
    for idx, ln in enumerate(lines):
        if idx < start_idx:
            continue
        ll = ln.lower()
        if ("voltage" in ll) or ("current" in ll):
            continue
        parts = split_parts(ln)
        if len(parts) <= max(v_idx, i_idx):
            continue
        V.append(_to_float(parts[v_idx]))
        I.append(_to_float(parts[i_idx]))

    # 길이 정리(혹시라도 다르면)
    n = min(len(V), len(I))
    return V[:n], I[:n]

def build_stats(V: List[float], I: List[float], metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Minimal stats for validation checks.
    """
    metadata = metadata or {}

    def nan_ratio(arr: List[float]) -> float:
        if not arr:
            return 1.0
        n_nan = sum(1 for x in arr if not _is_finite(x))
        return n_nan / max(len(arr), 1)

    def finite_ratio(arr: List[float]) -> float:
        if not arr:
            return 0.0
        n_fin = sum(1 for x in arr if _is_finite(x))
        return n_fin / max(len(arr), 1)

    def unique_count(arr: List[float], digits: int = 12) -> int:
        vals = [x for x in arr if _is_finite(x)]
        vals = [round(x, digits) for x in vals]
        return len(set(vals))

    stats: Dict[str, Any] = {
        "n_points": min(len(V), len(I)),
        "V_nan_ratio": nan_ratio(V),
        "I_nan_ratio": nan_ratio(I),
        "V_finite_ratio": finite_ratio(V),
        "I_finite_ratio": finite_ratio(I),
        "V_unique": unique_count(V),
        "I_unique": unique_count(I),
        "V_series": V,
        "I_series": I,
        "metadata": metadata,
    }
    return stats
