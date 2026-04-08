"""
추세 분석 도메인 입력 파서.
"""

from typing import List, Tuple


def parse_xy(raw_data: str) -> Tuple[List[float], List[float]]:
    """
    2열 숫자 데이터를 x, y 배열로 파싱한다.
    """

    x_values: List[float] = []
    y_values: List[float] = []

    for line in raw_data.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        parts = [part for part in stripped.replace("\t", ",").replace(" ", ",").split(",") if part]
        if len(parts) < 2:
            continue

        try:
            x_val = float(parts[0])
            y_val = float(parts[1])
        except Exception:
            continue

        x_values.append(x_val)
        y_values.append(y_val)

    return x_values, y_values
