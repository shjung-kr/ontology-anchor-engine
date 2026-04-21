# Ontology Anchor Engine Improvement Roadmap

This roadmap breaks the current improvement themes into executable work items.

## Priority Order

1. Repository hygiene and ignore rules
2. Runtime environment alignment
3. Tests and CI baseline
4. Security baseline
5. Evaluation and scientific validation docs
6. README rewrite

## Immediate Sprint Scope

The first implementation sprint should cover only the items below:

- Add a repository-wide `.gitignore`
- Remove tracked virtualenv, cache, run artifacts, and user data from version control
- Decide and align a single supported Python version
- Clean dependency metadata and move setup notes out of `requirements.txt`
- Add a minimal `pytest` test suite
- Add GitHub Actions CI for install, test, and API smoke test
- Raise the authentication baseline and add `SECURITY.md`

## Workstreams

### 1. Repository Hygiene

See [01-repository-hygiene.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/01-repository-hygiene.md).

### 2. Runtime and Packaging

See [02-runtime-alignment.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/02-runtime-alignment.md).

### 3. Test Coverage

See [03-test-plan.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/03-test-plan.md).

### 4. Continuous Integration

See [04-ci-plan.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/04-ci-plan.md).

### 5. Security Hardening

See [05-security-baseline.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/05-security-baseline.md).

### 6. Evaluation Documentation

See [06-evaluation-plan.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/06-evaluation-plan.md).

### 7. README Rewrite

See [07-readme-plan.md](/home/shjung/projects/ontology-anchor-engine/docs/roadmap/07-readme-plan.md).

## Definition of Done

The repository is considered baseline-ready when all conditions below are true:

- No local-only files or user-generated data are tracked in Git
- Python version requirements are identical across code and docs
- CI runs automatically on pull requests
- Core engine paths have repeatable tests
- Authentication and session handling meet a minimum public-demo security bar
- Evaluation methodology is documented with measurable criteria
- README supports setup, execution, and basic verification without tribal knowledge
