# 06. Evaluation Plan

## Objective

Document how the engine is validated scientifically and where it is expected to fail.

## Current Problem

The project communicates a strong research vision, but not yet a reproducible evaluation standard.

## Questions the Evaluation Must Answer

1. Which I-V patterns are handled reliably?
2. Which mechanisms are often confused?
3. How well do outputs match expert labels?
4. Under what measurement conditions does performance degrade?
5. What should external researchers treat as unsupported?

## Action Items

1. Define an evaluation dataset policy.
2. Define core metrics.
3. Publish representative success and failure cases.
4. Separate benchmark data from exploratory examples.
5. Add a reproducible report-generation path.

## Suggested Metrics

- Top-1 mechanism accuracy
- Top-k candidate recall
- Expert label agreement
- Explanation relevance score
- Failure case taxonomy

## Concrete Tasks

- Create `docs/evaluation/engine-evaluation-protocol.md`.
- Document inclusion and exclusion criteria for benchmark samples.
- Link each benchmark family to expected mechanisms.
- Summarize known blind spots.
- Connect scripts under `scripts/` to a repeatable evaluation report.

## Acceptance Criteria

- A third party can understand how claims about engine quality are measured.
- Success and failure conditions are both explicitly documented.
