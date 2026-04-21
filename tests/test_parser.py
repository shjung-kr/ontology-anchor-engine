from __future__ import annotations

from backend.measurement_validations.parser import build_stats, parse_vi


def test_parse_vi_with_header():
    voltage, current = parse_vi("V,I\n0,1e-9\n1,2e-9\n")
    assert voltage == [0.0, 1.0]
    assert current == [1e-09, 2e-09]


def test_parse_vi_with_whitespace_rows():
    voltage, current = parse_vi("0 1e-9\n1 2e-9\n2 4e-9\n")
    stats = build_stats(voltage, current)
    assert stats["n_points"] == 3
    assert stats["V_unique"] == 3
    assert stats["I_finite_ratio"] == 1.0
