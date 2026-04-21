# 01. Repository Hygiene

## Objective

Remove local-only files, execution artifacts, and user data from version control, then prevent them from returning.

## Current Findings

- `.gitignore` is missing.
- `.venv/` exists in the repository.
- `backend/__pycache__/` and `scripts/__pycache__/` exist in the repository.
- `backend/runs/` exists and appears to contain execution artifacts.
- `backend/user_data/` exists and contains user account and session data.

## Action Items

1. Create a root `.gitignore`.
2. Ignore Python cache and tooling artifacts.
3. Ignore local runtime data and generated outputs.
4. Remove already tracked local-only files from Git index.
5. Replace any required examples with sanitized fixtures.
6. Document which directories are runtime-only and must stay untracked.

## Proposed Ignore Targets

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
backend/runs/
backend/user_data/
*.log
```

## Concrete Tasks

- Add `.gitignore` at repository root.
- Run a tracked-file review for `.venv`, cache directories, generated JSON, logs, and run outputs.
- Remove tracked runtime directories from the index without deleting local working copies.
- Add `backend/user_data_example/` only if the application needs reference structures.
- Add a short note to README describing local runtime directories.

## Acceptance Criteria

- `git status` no longer shows runtime-generated files after a local run.
- No sensitive or user-derived data remains tracked.
- New contributors can run the project without accidentally committing local state.
