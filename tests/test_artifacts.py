from __future__ import annotations

import json

from backend.domains.iv.runner import normalize_requested_run_id, write_run_artifacts


def test_normalize_requested_run_id_rejects_invalid_values():
    assert normalize_requested_run_id(" demo run ") == "demo_run"


def test_write_run_artifacts_creates_manifest(tmp_path, monkeypatch):
    import backend.domains.iv.runner as runner_module

    monkeypatch.setattr(runner_module, "get_runs_dir", lambda: tmp_path)

    artifact_dir = write_run_artifacts(
        raw_data="V,I\n0,1e-9\n1,2e-9\n",
        measurement_validation={"valid": True, "warnings": [], "errors": []},
        llm_pattern="test pattern",
        llm_keywords=[{"keyword": "demo", "evidence": "demo"}],
        llm_trace={"used_llm": False},
        prompt_bundle={"model": "none", "temperature": 0.0, "top_p": 1.0},
        metadata={"requested_run_id": "artifact-demo"},
        assumptions={"assumption_ids": [], "assumptions": [], "assumptions_meta": {}},
        l1_state={"iv_features": [], "iv_regimes": [], "evidence": [], "rejected_ids": []},
        sj_proposals=[],
        metrics={"absI_decades_span": 1.0},
        regimes=[],
    )

    manifest = json.loads((tmp_path / "artifact-demo" / "manifest.json").read_text(encoding="utf-8"))
    assert artifact_dir.endswith("artifact-demo")
    assert manifest["run_id"] == "artifact-demo"
    assert manifest["artifacts"]["inference"] == "inference.json"
