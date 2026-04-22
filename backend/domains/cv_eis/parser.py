"""
C-V / EIS 도메인 입력 파서.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List


def _split_parts(line: str) -> List[str]:
    return [part.strip() for part in re.split(r"[,\t; ]+", line.strip()) if part.strip()]


def _to_float(value: str) -> float:
    try:
        return float(value.strip())
    except Exception:
        return float("nan")


def _is_finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


def _normalize_header(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", token.strip().lower())


ALIASES = {
    "bias": {
        "v",
        "voltage",
        "bias",
        "vbias",
        "dcbias",
        "dcoffset",
        "potential",
    },
    "capacitance": {
        "c",
        "cap",
        "capacitance",
        "capacitancef",
        "cp",
        "cm",
    },
    "frequency": {
        "f",
        "freq",
        "frequency",
        "hz",
    },
    "z_real": {
        "zreal",
        "rez",
        "realz",
        "zre",
        "zr",
    },
    "z_imag": {
        "zimag",
        "imz",
        "imagz",
        "zim",
        "zi",
        "zimaginary",
    },
    "loss": {
        "loss",
        "conductance",
        "g",
        "dissipation",
        "tandelta",
    },
    "branch": {
        "branch",
        "direction",
        "sweepdirection",
        "scan",
    },
}


def _canonicalize_header(token: str) -> str:
    normalized = _normalize_header(token)
    for canonical, names in ALIASES.items():
        if normalized in names:
            return canonical
    return normalized or "unknown"


def parse_measurement_table(raw_data: str) -> Dict[str, Any]:
    """
    표 형태의 원시 텍스트를 읽어 C-V / EIS 분석용 구조로 변환한다.
    """

    lines = [line.strip() for line in raw_data.splitlines() if line.strip()]
    if not lines:
        return {
            "measurement_kind": "unknown",
            "columns": [],
            "rows": [],
            "series": {},
            "stats": {"n_rows": 0, "finite_rows": 0},
        }

    first_parts = _split_parts(lines[0])
    header_detected = any(not _is_finite(_to_float(part)) for part in first_parts)

    if header_detected:
        columns = [_canonicalize_header(part) for part in first_parts]
        data_lines = lines[1:]
    else:
        columns = [f"col_{index}" for index in range(len(first_parts))]
        data_lines = lines

    rows: List[Dict[str, Any]] = []
    series: Dict[str, List[float]] = {column: [] for column in columns}

    for line in data_lines:
        parts = _split_parts(line)
        if len(parts) < len(columns):
            continue

        row: Dict[str, Any] = {}
        finite_row = True
        for index, column in enumerate(columns):
            value = _to_float(parts[index])
            row[column] = value
            series.setdefault(column, []).append(value)
            finite_row = finite_row and _is_finite(value)
        row["_finite"] = finite_row
        rows.append(row)

    measurement_kind = "unknown"
    has_bias = "bias" in series
    has_capacitance = "capacitance" in series
    has_frequency = "frequency" in series
    has_z_real = "z_real" in series
    has_z_imag = "z_imag" in series

    if has_z_real and has_z_imag and has_frequency:
        measurement_kind = "eis"
    elif has_bias and has_capacitance:
        measurement_kind = "cv"
    elif has_capacitance and has_frequency:
        measurement_kind = "cv_frequency"

    finite_rows = sum(1 for row in rows if row.get("_finite"))
    return {
        "measurement_kind": measurement_kind,
        "columns": columns,
        "rows": rows,
        "series": series,
        "stats": {
            "n_rows": len(rows),
            "finite_rows": finite_rows,
        },
    }
