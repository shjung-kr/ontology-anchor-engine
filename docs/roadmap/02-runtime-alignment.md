# 02. Runtime Alignment

## Objective

Pick one supported Python version policy and make the repository state it consistently.

## Current Findings

- `pyproject.toml` requires `>=3.12`.
- `AGENT.md` says `Python 3.10+`.
- `requirements.txt` mixes dependencies with setup notes and Git command notes.

## Decision Required

Choose one of the following:

1. Standardize on `Python 3.12+`
2. Standardize on `Python 3.10+`

## Recommendation

If there is no hard dependency on Python 3.12-only features, `3.10+` is the safer public baseline.

## Action Items

1. Decide the supported Python version policy.
2. Update `pyproject.toml` to match the policy.
3. Update `AGENT.md` to match the policy.
4. Rewrite the environment section of `README.md`.
5. Clean `requirements.txt` so it contains dependencies only.
6. Decide whether `pyproject.toml` or `requirements.txt` is the canonical dependency source.

## Concrete Tasks

- Audit the codebase for 3.12-only syntax or standard library usage.
- Align `requires-python`, local setup commands, and CI version matrix.
- Move shell notes and Git notes from `requirements.txt` into README or a developer setup guide.
- Document one recommended install path.
  - Example: `python -m venv .venv`
  - Example: `pip install -r requirements.txt`
  - Example: `uvicorn backend.server:app --reload`

## Acceptance Criteria

- Version declarations are identical across docs and config.
- A new contributor can reproduce the runtime environment with one documented flow.
- Dependency files do not contain unrelated notes.
