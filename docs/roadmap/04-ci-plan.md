# 04. CI Plan

## Objective

Run install, tests, and a minimal API verification on every pull request.

## Current Findings

- No `.github/workflows/` workflow files were found.

## Minimum Workflow

1. Checkout repository
2. Set up Python
3. Install dependencies
4. Run tests
5. Run a lightweight API smoke test

## Suggested Workflow Scope

- Trigger on pull request
- Trigger on push to main branches
- Keep runtime under a few minutes

## Concrete Tasks

- Add `.github/workflows/ci.yml`.
- Use the same Python version declared by runtime policy.
- Install dependencies using the documented project flow.
- Run `pytest`.
- Run a simple import check for `backend.server:app`.
- Optionally start `uvicorn` in CI and hit one endpoint.

## Nice-to-Have Follow-ups

- Add linting once the baseline stabilizes.
- Add matrix builds if multiple Python versions are officially supported.
- Cache dependency downloads.

## Acceptance Criteria

- Every PR gets an automated pass/fail signal.
- CI failure clearly identifies whether setup, tests, or app boot failed.
