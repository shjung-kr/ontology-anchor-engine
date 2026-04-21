# Security Policy

## Supported Deployment Model

The repository is maintained primarily for local development and controlled internal demos.

If you deploy it publicly, you are responsible for:

- setting explicit CORS origins
- disabling open registration unless required
- protecting secrets and API keys
- monitoring and rotating credentials

## Minimum Security Expectations

- Use passwords with at least 8 characters.
- Do not commit `backend/user_data/` or `backend/runs/`.
- Treat bearer tokens as secrets.
- Run behind TLS when exposed over a network.

## Vulnerability Reporting

Please report vulnerabilities privately to the maintainers before public disclosure.

Include:

- affected version or commit
- reproduction steps
- impact summary
- proposed mitigation if available
