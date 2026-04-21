# Ontology Anchor Engine

Ontology-backed experimental analysis service focused on I-V pattern interpretation, proposal generation, and reproducible run artifacts.

## Status

This repository is an actively evolving research prototype. It is suitable for local development and controlled demos, not an internet-exposed production deployment without additional hardening.

## Quick Start

### Requirements

- Python 3.10 or newer
- `pip`

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
uvicorn backend.server:app --reload
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/frontend/studio.html`

## API Example

Register a local user:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo-user","password":"strongpass123","display_name":"Demo"}'
```

Run an I-V analysis:

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "iv",
    "raw_data": "V,I\n0,1e-9\n1,2e-9\n2,8e-9\n3,4e-8\n4,2e-7"
  }'
```

## Sample Input

Bundled sample files live under [`data/`](/home/shjung/projects/ontology-anchor-engine/data:1), including:

- `data/fn_tunneling_iv_300K.txt`
- `data/led_iv_curve_-10V_to_5V_step_0.02V.csv`
- `data/thermionic_emission_iv_300K.txt`

## Outputs and Artifacts

Run artifacts and local user state are generated at runtime under:

- `backend/runs/`
- `backend/user_data/`

These directories are intentionally ignored by Git and must not be committed.

Typical run artifacts include:

- `manifest.json`
- `derived.json`
- `inference.json`
- `sj_proposal.json`
- `llm_trace.json`

## Tests

Run the baseline test suite with:

```bash
pytest
```

The current automated baseline covers:

- parser behavior
- I-V feature extraction
- ontology proposal matching
- run artifact generation
- auth and API smoke flow

## Repository Layout

- [`backend/`](/home/shjung/projects/ontology-anchor-engine/backend:1): FastAPI app, domain engines, auth, storage
- [`frontend/`](/home/shjung/projects/ontology-anchor-engine/frontend:1): static HTML pages
- [`data/`](/home/shjung/projects/ontology-anchor-engine/data:1): sample datasets and evaluation inputs
- [`docs/`](/home/shjung/projects/ontology-anchor-engine/docs:1): architecture, evaluation, roadmap
- [`prompts/`](/home/shjung/projects/ontology-anchor-engine/prompts:1): prompt templates
- [`scripts/`](/home/shjung/projects/ontology-anchor-engine/scripts:1): utility and validation scripts

## Security Notes

- Open registration is intended for local development by default.
- For public or shared deployments, disable registration and configure explicit CORS allowlists.
- Session tokens now expire and are stored server-side as hashes.
- See [`SECURITY.md`](/home/shjung/projects/ontology-anchor-engine/SECURITY.md:1).

## Evaluation and Limits

Evaluation planning documents live under [`docs/evaluation/`](/home/shjung/projects/ontology-anchor-engine/docs/evaluation:1) and [`docs/roadmap/`](/home/shjung/projects/ontology-anchor-engine/docs/roadmap:1).

Current non-goals:

- replacing expert scientific judgment
- claiming validated performance across all mechanism families
- serving as a hardened public multi-tenant platform
