# Chat Evaluation Rubric

이 문서는 `ontology-anchor-engine`의 대화 품질 개선을 재현 가능하게 측정하기 위한 기준표다.

## 목적

- 규칙 기반 답변과 LLM 자유대화 답변을 동일한 질문셋으로 비교한다.
- 개선 여부를 “느낌”이 아니라 수치로 기록한다.
- 질문 유형별 약점을 분리해서 추적한다.

## 평가 단위

평가는 `run_id + user question` 한 쌍을 하나의 case로 본다.

각 case는 아래 정보를 가진다.

- `run_id`
- `category`
- `question`
- `expected_elements.must`
- `expected_elements.should`
- `avoid_patterns`

## 평가 축

모든 축은 1~5점으로 채점한다.

### 1. Question Fit

- 질문에 직접 답했는가
- 사용자가 묻지 않은 run 요약을 과도하게 반복하지 않았는가

기준:
- `1`: 질문과 거의 무관한 답변
- `3`: 관련은 있지만 초점이 흐림
- `5`: 질문의 초점에 바로 답함

### 2. Evidence Use

- run 결과 JSON에서 형성된 근거를 실제로 활용했는가
- feature, assumption, warning, condition, candidate hypothesis 등을 적절히 연결했는가

기준:
- `1`: 근거 없이 일반론만 말함
- `3`: 일부 근거를 언급함
- `5`: 질문과 관련된 근거를 선택적으로 잘 사용함

### 3. Depth

- 단순 요약 반복이 아니라 원인, 의미, 조건, 해석 차이를 풀어 설명했는가

기준:
- `1`: 표면적 요약
- `3`: 부분 설명
- `5`: 원인/조건/한계를 포함한 설명

### 4. Accuracy & Guardedness

- 현재 run 결과와 모순되지 않는가
- 불확실성을 과장하지 않고 적절히 드러내는가

기준:
- `1`: 결과와 모순되거나 과도하게 단정
- `3`: 대체로 맞지만 경계가 흐림
- `5`: 근거 기반이며 불확실성 표현도 적절

### 5. Naturalness

- 사람이 읽기에 자연스러운가
- ontology ID 남용, 기계적 템플릿 반복, 딱딱한 구조가 적은가

기준:
- `1`: 기계적이고 부자연스러움
- `3`: 무난하지만 반복적
- `5`: 자연스럽고 읽기 쉬움

### 6. Actionability

- 질문이 실험 제안/개선 방안을 요구하는 경우, 다음 행동이 구체적인가
- 관련 없는 질문에서는 중립 점수(기본 3점)로 본다

기준:
- `1`: 행동으로 이어지지 않음
- `3`: 대략적 방향만 제시
- `5`: 변수/조건/비교 방식이 구체적임

## 질문 카테고리

- `mechanism_why`: 왜 이런 메커니즘 해석이 나왔는지 설명
- `meaning_explanation`: feature, slope, pattern의 의미 설명
- `turn_on_cause`: 턴온 전압/턴온 거동의 원인 설명
- `turn_on_reduction`: 턴온 전압을 낮추는 방법/실험
- `next_experiment`: 다음 실험 제안
- `assumption_check`: 가정의 역할과 필요성 설명
- `artifact_check`: measurement artifact 가능성 점검

## 권장 운영

1. 같은 benchmark JSON을 기준으로 `rule_based`와 `llm_context`를 모두 평가한다.
2. 가능하면 `heuristic + llm_judge`를 함께 기록한다.
3. 전체 평균뿐 아니라 카테고리별 평균도 비교한다.
4. 개선률은 아래처럼 계산한다.

```text
improvement % = (new_score - baseline_score) / baseline_score * 100
```

## 산출물

평가 스크립트는 아래 정보를 JSON 리포트에 저장한다.

- 전략별 평균 점수
- 카테고리별 평균 점수
- case별 질문/답변/세부 점수
- 반복 응답 비율
- ontology leakage 비율
- baseline 대비 delta
