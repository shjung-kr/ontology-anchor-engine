Development has become more complex than originally anticipated. As the project progressed, both the underlying concepts and the implementation approach expanded, incorporating a wider range of ideas and techniques. Below is a summary of these technical extensions and expansions.

## Quick Start

```bash
cd /home/shjung/projects/ontology-engine/ontology-anchor-engine
./.venv/bin/uvicorn backend.server:app --reload
```

If `OPENAI_API_KEY` is not set, the backend still runs in numeric-fallback mode.

Ontology consistency can be checked with:

```bash
./.venv/bin/python scripts/validate_ontology.py
```

# Reproducibility and Auditability

This document defines how the project guarantees **repeatable** (as deterministic as possible) runs and provides **audit trails** when results differ.

The key idea is to separate the pipeline into stable stages and store their outputs as artifacts:

1. **Parse & Normalize**: `raw_data` → `canonical`
2. **Derive**: `canonical` → `derived`
3. **Infer**: `derived (+metadata/text)` → `measurement_conditions`, `iv_features`, `sj_proposal`
4. **Store**: write all artifacts + a run `manifest.json`

---

## 1) Determinism policy (LLM + rules)

### 1.1 Rule-first
Whenever feasible, **numeric rules** decide:
- regime split
- slopes / decades span
- iv feature candidates

LLM is used primarily for:
- selecting among *predefined* ontology IDs when numeric signals are ambiguous
- producing human-readable traces/explanations

### 1.2 LLM parameters (recommended defaults)
- `temperature = 0`
- `top_p = 1` (or fixed)
- fixed model name/version (recorded in manifest)
- fixed system prompt + user template (recorded in manifest)

### 1.3 Allowed IDs only (no ontology invention)
The LLM must **never** create IDs.
It may only select from `allowed_ids` lists provided at runtime.
If nothing fits, it must output `unknown` for that field.

---

## 2) Prompt governance (System Prompt is part of the spec)

### 2.1 Why we version the system prompt
LLM output depends heavily on the **system prompt**.
To ensure reproducibility:
- system prompt is stored as a **file** in the repo (not inline in code)
- changes go through PR review
- every run stores the **prompt hash** in `manifest.json`

### 2.2 Prompt files layout (recommended)
```
prompts/
  system_prompt_v1.md
  user_template_v1.md
  system_prompt_v1_ko.md        (optional)
  user_template_v1_ko.md        (optional)
```

### 2.3 What the system prompt must enforce (non-negotiable)
1) **No ontology ID creation**
2) **JSON-only output**
3) **Use only `allowed_ids`**
4) **Evidence-first selection** (refer to derived fields / rules)
5) **Deterministic behavior** mindset (no creative writing)

---

## 3) Minimal system prompt template (v1)

Use the file: `prompts/system_prompt_v1.md`

### 3.1 Core rules (summary)
- You are inside a scientific inference system.
- You must not invent ontology IDs.
- You may only choose from provided `allowed_ids`.
- Output must be **valid JSON only**, matching the requested schema.
- If none apply, emit `"unknown"` and explain in trace.

---

## 4) User template (runtime message) requirements

Use the file: `prompts/user_template_v1.md`

The user template should include:
- the input `derived` JSON (or a compact summary)
- optional user-provided metadata/text
- `allowed_ids` grouped by field (conditions, features, mechanisms, etc.)
- the exact output schema to follow

---

## 5) Manifest (run metadata) specification

Every run must write a `manifest.json` capturing:

### 5.1 Minimum required fields
```json
{
  "run_id": "2026-02-11T10-22-31Z__<dataset_id>",
  "dataset_id": "sha256:<...>",
  "created_at_utc": "2026-02-11T10:22:31Z",
  "code_commit": "git:<...>",
  "ontology_commit": "git:<...>",
  "lexicon_commit": "git:<...>",
  "model": { "name": "<...>", "temperature": 0, "top_p": 1 },
  "prompts": {
    "system_prompt_path": "prompts/system_prompt_v1.md",
    "system_prompt_hash": "sha256:<...>",
    "user_template_path": "prompts/user_template_v1.md",
    "user_template_hash": "sha256:<...>"
  },
  "artifacts": {
    "raw_input": "raw_input.txt",
    "canonical": "canonical.parquet",
    "derived": "derived.json",
    "inference": "inference.json",
    "sj_proposal": "sj_proposal.json",
    "llm_trace": "llm_trace.json"
  }
}
```

### 5.2 Notes
- `code_commit/ontology_commit/lexicon_commit` should be git commit hashes when available.
- `prompt_hash` must be computed on the **exact file content** used for the run.
- If any of these fields are missing, the run is considered **non-auditable**.

---

## 6) LLM caching policy

To reduce variance and ensure identical inputs yield identical outputs, cache LLM results.

### 6.1 Cache key (recommended)
```
cache_key = sha256(
  model_name +
  system_prompt_hash +
  user_template_hash +
  input_hash(derived + metadata/text) +
  allowed_ids_hash
)
```

### 6.2 Cache value (recommended)
- raw LLM response text
- parsed JSON output
- timestamp

If the same `cache_key` is seen again, **reuse** the cached response (no new LLM call).

---

## 7) Trace logging (llm_trace.json)

Store enough information to explain outcomes without leaking secrets:
- the **selected IDs**
- the evidence fields used (derived keys, rule names)
- any `unknown` reasons
- prompt hashes + cache key

This enables:
- comparing two runs
- pinpointing whether a change came from data, rules, ontology, or prompt/model changes


In Korean(한글)

# 재현성 및 감사 가능성(Reproducibility & Auditability)

이 문서는 프로젝트가 실행 결과를 **최대한 재현 가능**하게 만들고(결정성 강화), 결과가 달라졌을 때 **원인을 추적(감사)**할 수 있도록 하는 운영 규칙을 정의합니다.

핵심 아이디어는 파이프라인을 안정적인 단계로 분리하고, 각 단계의 출력물을 아티팩트로 저장하는 것입니다.

1. **파싱/정규화**: `raw_data` → `canonical`
2. **파생지표 생성**: `canonical` → `derived`
3. **추론**: `derived (+metadata/text)` → `measurement_conditions`, `iv_features`, `sj_proposal`
4. **저장**: 모든 아티팩트 + 실행 `manifest.json` 기록

---

## 1) 결정성(Determinism) 정책: 룰 우선 + LLM 보조

### 1.1 룰 우선(rule-first)
가능한 범위에서는 **수치 기반 룰**이 다음을 결정합니다.
- regime 분할
- slope / decades span 등 핵심 지표
- iv_features 후보 판정

LLM은 주로 다음 용도로 제한합니다.
- 수치 신호가 애매할 때 *미리 정의된* 온톨로지 ID 중 선택 보조
- 사람용 설명(trace) 생성(선택 사항)

### 1.2 LLM 파라미터(권장 기본값)
- `temperature = 0`
- `top_p = 1` (또는 고정값)
- 모델 이름/버전 고정(실행 시 manifest에 기록)
- system prompt + user template 고정(실행 시 manifest에 기록)

### 1.3 허용 ID만 사용(온톨로지 ID 생성 금지)
LLM은 온톨로지 ID를 **절대 생성**하지 않습니다.  
런타임에 제공되는 `allowed_ids` 목록에서만 선택할 수 있습니다.  
아무 것도 해당하지 않으면 해당 필드에 `"unknown"`을 출력합니다(스키마가 허용할 때).

---

## 2) 프롬프트 거버넌스: System Prompt는 스펙의 일부

### 2.1 왜 system prompt를 버전 관리해야 하나
LLM 출력은 **system prompt**에 크게 의존합니다. 재현성 확보를 위해:
- system prompt를 코드에 박지 않고 **레포 파일로 분리**
- 변경은 PR로 리뷰
- 매 실행마다 **프롬프트 해시(prompt_hash)**를 `manifest.json`에 저장

### 2.2 프롬프트 파일 권장 레이아웃
```
prompts/
  system_prompt_v1.md
  user_template_v1.md
  system_prompt_v1_ko.md
  user_template_v1_ko.md
```

### 2.3 system prompt가 강제해야 하는 것(필수)
1) **온톨로지 ID 생성 금지**
2) **JSON-only 출력**
3) **allowed_ids 범위 내 선택**
4) **증거 기반 선택(derived/rule 근거)**
5) **결정성 우선(불필요한 변형 금지)**

---

## 3) 최소 system prompt 템플릿(v1)

파일: `prompts/system_prompt_v1_ko.md`

요약:
- 너는 과학 추론 시스템 내부의 어시스턴트다.
- 온톨로지 ID는 만들면 안 된다.
- allowed_ids에서만 고른다.
- 출력은 JSON만 반환한다.
- 불확실하면 unknown을 반환하고(trace가 있을 때) 짧은 이유를 남긴다.

---

## 4) user 템플릿(런타임 메시지) 요구사항

파일: `prompts/user_template_v1_ko.md`

user 템플릿에는 다음이 포함되어야 합니다.
- `derived` JSON(또는 축약 요약)
- 사용자 제공 메타/노트(옵션)
- `allowed_ids` (conditions/features/mechanisms 등 카테고리별)
- 출력 스키마(또는 정확한 JSON 스켈레톤)

---

## 5) Manifest(실행 메타) 스펙

모든 실행은 아래 정보를 포함한 `manifest.json`을 생성합니다.

### 5.1 최소 필수 필드
```json
{
  "run_id": "2026-02-11T10-22-31Z__<dataset_id>",
  "dataset_id": "sha256:<...>",
  "created_at_utc": "2026-02-11T10:22:31Z",
  "code_commit": "git:<...>",
  "ontology_commit": "git:<...>",
  "lexicon_commit": "git:<...>",
  "model": { "name": "<...>", "temperature": 0, "top_p": 1 },
  "prompts": {
    "system_prompt_path": "prompts/system_prompt_v1_ko.md",
    "system_prompt_hash": "sha256:<...>",
    "user_template_path": "prompts/user_template_v1_ko.md",
    "user_template_hash": "sha256:<...>"
  },
  "artifacts": {
    "raw_input": "raw_input.txt",
    "canonical": "canonical.parquet",
    "derived": "derived.json",
    "inference": "inference.json",
    "sj_proposal": "sj_proposal.json",
    "llm_trace": "llm_trace.json"
  }
}
```

### 5.2 메모
- `code_commit/ontology_commit/lexicon_commit`은 가능하면 git commit hash를 저장합니다.
- `prompt_hash`는 **실제로 사용한 파일의 전체 내용**으로 sha256을 계산합니다.
- 위 정보가 누락되면 해당 실행은 **감사 불가(non-auditable)**로 간주합니다.

---

## 6) LLM 캐싱 정책(강추)

동일 입력이 동일 출력으로 재사용되도록 LLM 결과를 캐시합니다.

### 6.1 캐시 키(권장)
```
cache_key = sha256(
  model_name +
  system_prompt_hash +
  user_template_hash +
  input_hash(derived + metadata/text) +
  allowed_ids_hash
)
```

### 6.2 캐시 값(권장)
- LLM 원문 응답
- 파싱된 JSON 결과
- timestamp

동일 `cache_key`가 있으면 **새로 LLM을 호출하지 않고** 캐시를 재사용합니다.

---

## 7) trace 로그(llm_trace.json)

비밀(예: 내부 온톨로지 전체) 노출 없이도 원인을 추적할 수 있도록 다음을 저장합니다.
- 선택된 ID 목록
- 사용한 근거(derived 키, 적용된 룰 이름)
- unknown 사유(해당 시)
- prompt hash + cache key

이를 통해:
- 두 실행(run) 비교
- 변경 원인이 데이터/룰/온톨로지/프롬프트/모델 중 무엇인지 식별
