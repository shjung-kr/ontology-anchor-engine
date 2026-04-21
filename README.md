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

Example response shape:

```json
{
  "domain": "iv",
  "llm_pattern": "데이터 전체에서 |I| 변화폭은 약 6.59 decades 입니다. |V|≈1.5 부근에서 전류 거동이 바뀌는 구간 분리가 관측됩니다. 저전압 구간의 log-log 기울기는 0.48로, 선형보다 더 가파른 초선형 스케일링을 보입니다.",
  "l1_state": {
    "iv_features": [
      "iv_features.field_enhanced_current",
      "iv_features.nonlinear_iv_regime"
    ]
  },
  "sj_proposals": [
    {
      "claim_concept": "iv_interpretation.fn_tunneling_asserted",
      "score": 2.0
    }
  ]
}
```

## Sample Input

Bundled sample files live under [`data/`](/home/shjung/projects/ontology-anchor-engine/data:1), including:

- `data/fn_tunneling_iv_300K.txt`
- `data/led_iv_curve_-10V_to_5V_step_0.02V.csv`
- `data/thermionic_emission_iv_300K.txt`

Representative golden benchmark expectations:

- `fn_tunneling_iv_300K.txt` -> top claim `iv_interpretation.fn_tunneling_asserted`
- `thermionic_emission_iv_300K.txt` -> top claim `iv_interpretation.ohmic_transport`

Golden case definitions are stored in [`data/evals/golden_iv_cases.json`](/home/shjung/projects/ontology-anchor-engine/data/evals/golden_iv_cases.json:1).

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

Example `manifest.json` excerpt:

```json
{
  "run_id": "readme-sample-1",
  "domain": "iv",
  "prompts": {
    "system_prompt_path": "prompts/system_prompt_v1.md",
    "user_template_path": "prompts/user_template_v1.md"
  },
  "artifacts": {
    "raw_input": "raw_input.txt",
    "derived": "derived.json",
    "inference": "inference.json",
    "sj_proposal": "sj_proposal.json",
    "llm_trace": "llm_trace.json"
  }
}
```

Example `derived.json` excerpt:

```json
{
  "llm_pattern": "데이터 전체에서 |I| 변화폭은 약 6.59 decades 입니다. |V|≈1.5 부근에서 전류 거동이 바뀌는 구간 분리가 관측됩니다. 저전압 구간의 log-log 기울기는 0.48로, 선형보다 더 가파른 초선형 스케일링을 보입니다.",
  "metrics": {
    "absI_decades_span": 6.59,
    "v_knee": 1.5
  }
}
```

## Tests

Run the baseline test suite with:

```bash
pytest
```

The current automated baseline covers:

- parser behavior
- I-V feature extraction
- ontology proposal matching
- golden sample regression checks
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

Start with:

- [`docs/evaluation/engine-evaluation-protocol.md`](/home/shjung/projects/ontology-anchor-engine/docs/evaluation/engine-evaluation-protocol.md:1)
- [`docs/evaluation/chat-eval-rubric.md`](/home/shjung/projects/ontology-anchor-engine/docs/evaluation/chat-eval-rubric.md:1)

The engine evaluation protocol defines:

- golden benchmark cases
- top-1/top-k and feature-match metrics
- failure taxonomy
- benchmark update rules

Current non-goals:

- replacing expert scientific judgment
- claiming validated performance across all mechanism families
- serving as a hardened public multi-tenant platform
