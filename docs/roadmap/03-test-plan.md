# 03. Test Plan

## Objective

Add a minimal but credible automated test baseline for the core engine and API.

## Current Findings

- No `tests/` directory is present.
- No `pytest` test files were found.

## Minimum Coverage Targets

1. Parser behavior
2. Feature extraction
3. Ontology matching
4. Proposal ranking
5. Run artifact generation
6. FastAPI smoke test

## Test Layers

### Unit Tests

- Parser returns normalized internal structures for valid input.
- Parser rejects malformed or incomplete input.
- Feature extraction produces expected derived features on known samples.
- Ontology matching returns expected candidates for stable golden inputs.
- Proposal ranking preserves deterministic ordering for a fixed sample.

### Golden Sample Tests

- Curate representative I-V samples from `data/`.
- Freeze expected outputs for a small trusted subset.
- Add one failure-mode sample per mechanism family when possible.

### API Tests

- App import test
- Health or root endpoint smoke test
- One representative analysis request with fixture data

## Concrete Tasks

- Add `pytest` and `httpx` or `fastapi[test]` test dependencies.
- Create `tests/conftest.py` if shared fixtures are needed.
- Add `tests/test_parser.py`.
- Add `tests/test_features.py`.
- Add `tests/test_matching.py`.
- Add `tests/test_ranking.py`.
- Add `tests/test_artifacts.py`.
- Add `tests/test_api_smoke.py`.

## Acceptance Criteria

- `pytest` runs successfully in CI.
- Critical engine paths are covered by stable, non-flaky tests.
- At least one golden sample guards against regression in mechanism proposals.
