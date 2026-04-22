from __future__ import annotations

from backend.measurement_validations.parser import build_stats, parse_vi
from backend.domains.cv_eis.parser import parse_measurement_table


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


def test_parse_measurement_table_detects_cv():
    parsed = parse_measurement_table("bias capacitance\n-1 12e-9\n0 10e-9\n1 8e-9\n")
    assert parsed["measurement_kind"] == "cv"
    assert parsed["columns"] == ["bias", "capacitance"]
    assert parsed["stats"]["n_rows"] == 3


def test_parse_measurement_table_detects_eis():
    parsed = parse_measurement_table("frequency,z_real,z_imag\n1,10,-1\n10,8,-4\n100,5,-1\n")
    assert parsed["measurement_kind"] == "eis"
    assert parsed["columns"] == ["frequency", "z_real", "z_imag"]
    assert parsed["stats"]["finite_rows"] == 3
