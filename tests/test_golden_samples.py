from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from backend.core.domain_models import DomainExecutionRequest
from backend.core.engine import run_domain_engine
from backend.user_storage import user_scope
import backend.llm_adapter as llm_adapter
import backend.domains.iv.runner as iv_runner


ROOT_DIR = Path(__file__).resolve().parents[1]
GOLDEN_CASES_PATH = ROOT_DIR / "data" / "evals" / "golden_iv_cases.json"


def test_golden_iv_cases(tmp_path):
    cases = json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))

    with patch.object(llm_adapter, "_get_openai_client", return_value=None):
        with patch.object(iv_runner, "get_runs_dir", return_value=tmp_path):
            for case in cases:
                raw_data = (ROOT_DIR / case["input_path"]).read_text(encoding="utf-8")
                requested_run_id = f"golden-{case['case_id']}"
                with user_scope("golden-test-user"):
                    result = run_domain_engine(
                        DomainExecutionRequest(
                            domain=case["domain"],
                            raw_data=raw_data,
                            requested_run_id=requested_run_id,
                        )
                    )

                assert result["domain"] == case["domain"]
                assert result["llm_pattern"]
                assert result["sj_proposals"], f"no proposals for {case['case_id']}"
                assert result["sj_proposals"][0]["claim_concept"] == case["expected_top_claim"]
                assert len(result["measurement_validation"]["warnings"]) <= case["max_warning_count"]

                observed_features = set(result["l1_state"]["iv_features"])
                for expected_feature in case["expected_features"]:
                    assert expected_feature in observed_features

                artifact_dir = tmp_path / requested_run_id
                for filename in ("manifest.json", "derived.json", "inference.json", "sj_proposal.json", "llm_trace.json"):
                    assert (artifact_dir / filename).is_file(), f"missing {filename} for {case['case_id']}"
