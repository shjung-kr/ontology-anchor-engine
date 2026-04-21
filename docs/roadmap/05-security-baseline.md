# 05. Security Baseline

## Objective

Raise the repository from local-prototype security to a minimum public-demo baseline.

## Current Findings

- Password minimum length is `4`.
- Sessions are stored in `backend/user_data/_system/sessions.json`.
- Session tokens appear to be stored directly.
- No session expiry was identified.
- CORS is configured in server code and should be environment-aware before public deployment.
- Public registration exists and needs deployment controls.

## Action Items

1. Raise password minimum length and error messaging.
2. Add session expiry and invalidation rules.
3. Add login rate limiting.
4. Avoid storing bearer tokens in plain retrievable form.
5. Split CORS settings by environment.
6. Add a flag to disable open registration in public deployments.
7. Add `SECURITY.md`.

## Concrete Tasks

- Change password minimum length from `4` to at least `8` or `12`.
- Store session metadata with issued-at and expires-at timestamps.
- Reject expired sessions in auth dependency checks.
- Add per-IP or per-user login throttling.
- Move allowed origins into environment configuration.
- Add a deployment guard for `/auth/register`.
- Create a public vulnerability reporting policy.

## Acceptance Criteria

- The application can no longer be deployed publicly with default-weak auth rules.
- Session handling has explicit lifecycle rules.
- Security expectations are documented for maintainers and users.
