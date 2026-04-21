# Engine Evaluation Protocol

이 문서는 `ontology-anchor-engine`의 I-V 분석 엔진을 외부 연구자도 이해 가능한 방식으로 검증하기 위한 기준 문서다.

## 목적

- 엔진이 어떤 I-V 패턴에서 어떤 해석 후보를 안정적으로 제시하는지 기록한다.
- 전문가 기대와 얼마나 일치하는지 정량 지표로 관리한다.
- 잘 맞는 조건뿐 아니라 실패 조건과 비적용 범위를 명시한다.

## 평가 범위

현재 프로토콜은 `iv` 도메인에 우선 적용한다.

평가 대상은 아래 단계다.

- 원시 입력 파싱
- 측정 유효성 검증
- 수치 기반 관측 패턴 요약
- feature 추출
- ontology 기반 proposal ranking
- run artifact 생성

## 평가 단위

하나의 평가 case는 아래 요소를 가진다.

- `case_id`
- 입력 파일 경로
- 도메인
- 기대 top claim
- 기대 feature 집합
- 허용/비허용 warning
- 메모

기본 case 정의 파일은 [`data/evals/golden_iv_cases.json`](/home/shjung/projects/ontology-anchor-engine/data/evals/golden_iv_cases.json:1)을 사용한다.

## 데이터셋 정책

### 1. Golden Benchmark Set

회귀 검출을 위한 소형 신뢰 셋이다.

요건:

- 저장소에 포함된 공개 가능 샘플만 사용
- 기대 해석과 핵심 feature를 명시
- 변경이 필요한 경우 PR에서 근거를 남김

현재 포함된 대표 케이스:

- `fn_tunneling_iv_300K.txt`
- `thermionic_emission_iv_300K.txt`

### 2. Exploratory Set

정식 score 집계에는 바로 넣지 않고 실패 분석과 coverage 확장에만 사용한다.

후보:

- synthetic I-V
- toy CSV
- noisy real raw data

## 핵심 지표

### 1. Top-1 Claim Accuracy

정의:

- 최상위 `claim_concept`가 기대 top claim과 일치하는 비율

목적:

- 대표 메커니즘 식별 안정성 추적

### 2. Top-k Candidate Recall

정의:

- 기대 claim이 상위 `k` proposal 안에 포함되는 비율

권장 `k`:

- `k=3`

목적:

- 순위는 다르더라도 유효 후보를 놓치지 않는지 확인

### 3. Feature Match Accuracy

정의:

- 기대 feature가 추출 결과에 포함되는지 확인

목적:

- proposal 성능 저하가 feature 단계에서 시작되는지 분리

### 4. Validation Cleanliness

정의:

- 정상이 기대되는 샘플에서 `error=0`
- warning 개수와 warning 유형 추적

목적:

- 파서/validator 회귀 조기 탐지

### 5. Artifact Completeness

정의:

- 필수 artifact 파일 생성 여부

필수 항목:

- `manifest.json`
- `derived.json`
- `inference.json`
- `sj_proposal.json`
- `llm_trace.json`

## 전문가 라벨 일치

정식 benchmark가 커지면 아래 형식으로 expert agreement를 기록한다.

- `expert_label.primary_claim`
- `expert_label.acceptable_claims`
- `expert_label.key_features`
- `expert_label.disallowed_claims`

지표:

- exact top-1 match
- acceptable set hit
- feature overlap

## 실패 분석 규칙

실패 case는 아래 taxonomy로 분류한다.

- `parse_failure`
- `validation_false_alarm`
- `feature_miss`
- `feature_overfire`
- `ranking_misorder`
- `ontology_gap`
- `artifact_generation_failure`
- `unsupported_pattern`

각 실패 case에는 아래를 기록한다.

- 입력 샘플
- 실제 top claim
- 기대 top claim
- 누락 feature / 과잉 feature
- 재현 절차
- 다음 수정 후보

## 비적용 범위

현재 엔진은 아래를 보장하지 않는다.

- 모든 transport mechanism family에 대한 일반적 성능
- 모든 재료계와 온도 조건에 대한 강건성
- 전문가 판단을 대체하는 자동 결론

## 운영 방식

1. golden sample 테스트는 모든 PR에서 실행한다.
2. 평가 문서 변경 시 benchmark 기대값 변경 이유를 함께 남긴다.
3. 기대값이 바뀌면 코드 회귀인지, ontology 업데이트인지, benchmark 수정인지 구분한다.
4. README에는 대표 성공 케이스와 현재 한계를 함께 노출한다.

## 산출물

최소 산출물은 아래 두 가지다.

- 자동화 테스트 결과
- 평가 문서 및 benchmark 정의 파일

후속 단계에서는 `scripts/` 아래 평가 스크립트와 연결해 JSON/Markdown 리포트를 자동 생성한다.
