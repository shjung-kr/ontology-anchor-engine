# Frontend Workbench Plan

## Goal

현재 단일 분석 화면을 다음 3가지 워크벤치 기능으로 확장한다.

1. Session History List
2. Run Compare View
3. Experiment Planner View

핵심 목적은 "보기 좋은 데모 화면"이 아니라, 개발과 반복 실험에 실제로 편한 분석 워크벤치를 만드는 것이다.


## Why

현재 인터페이스는 단일 run 중심이다.

- 이전 run을 다시 찾기 어렵다.
- 두 run의 해석 차이를 한 화면에서 비교하기 어렵다.
- 실험 아이디어가 conversation 결과 안에 섞여 있어서 planning 도구처럼 쓰기 어렵다.

그래서 다음 3개 화면을 분리해야 한다.


## Scope

### 1. Session History List

목표:

- 최근 run 목록 확인
- run의 핵심 상태를 빠르게 스캔
- 원하는 run을 다시 열기
- 후속 비교/계획 작업의 시작점 제공

보여줄 항목:

- `run_id`
- 생성 시각
- domain
- coverage status
- 최상위 claim 또는 fallback status
- validation warning 존재 여부
- approved patch item 수

행동:

- `Open`
- `Compare`
- `Plan`


### 2. Run Compare View

목표:

- 두 run의 해석 차이와 조건 차이를 한눈에 본다.
- 동일 데이터의 다른 intent 결과나 다른 데이터의 유사/상반 패턴을 비교한다.

비교 축:

- measurement validation 요약
- confirmed conditions
- top proposal
- fallback status
- candidate hypotheses
- experiment ideas
- approved patch items

비교 원칙:

- 정량 raw dump보다 차이 중심으로 보여준다.
- "같음 / 다름 / 추가됨 / 제거됨"이 먼저 보여야 한다.


### 3. Experiment Planner View

목표:

- conversation 결과에서 실험 아이디어만 따로 모아 planning 도구처럼 사용
- 가설별 실험 목적, 기대 관찰, 우선순위를 관리

보여줄 항목:

- hypothesis label
- experiment title
- purpose
- actions
- expected signal
- source run
- target hypothesis
- planner status

planner status 예시:

- `suggested`
- `selected`
- `scheduled`
- `completed`
- `rejected`

추가 행동:

- 특정 아이디어를 planner에 pin
- 메모 추가
- 우선순위 부여


## Information Architecture

### Primary Navigation

상단 탭을 4개로 분리한다.

1. `Analyze`
2. `History`
3. `Compare`
4. `Planner`

현재 화면은 `Analyze` 탭으로 유지한다.


### Analyze

기존 단일 run 분석 화면.

역할:

- 새 run 생성
- conversation 수행
- planner로 아이디어 보내기


### History

왼쪽:

- run 목록

오른쪽:

- 선택한 run 요약

빠른 액션:

- `Open in Analyze`
- `Add to Compare`
- `Send Ideas to Planner`


### Compare

상단:

- 비교 대상 run A / run B 선택

본문:

- Difference summary
- Shared interpretation
- Diverging claims
- Condition differences
- Experiment idea differences


### Planner

목록 중심 화면.

필터:

- by run
- by hypothesis
- by status

카드 정보:

- title
- target hypothesis
- source run
- purpose
- expected signal
- status


## Backend Requirements

현재 API만으로는 목록/비교/플래너를 충분히 만들기 어렵다.

필요 API:

### 1. `GET /runs`

목적:

- 최근 run 목록 로딩

응답 최소 필드:

- `run_id`
- `created_at_utc`
- `domain`
- `coverage_status`
- `top_claim`
- `fallback_status`
- `warning_count`
- `candidate_count`


### 2. `GET /runs/{run_id}/summary`

목적:

- history에서 선택한 run의 lightweight 상세 보기

응답:

- 현재 `conversation_state`의 핵심 요약
- full artifact dump는 제외 가능


### 3. `POST /runs/compare`

입력:

- `left_run_id`
- `right_run_id`

응답:

- `shared_items`
- `changed_items`
- `left_only`
- `right_only`
- `experiment_idea_diff`


### 4. `GET /planner`

목적:

- planner에 저장된 아이디어 목록


### 5. `POST /planner/items`

목적:

- run의 experiment idea를 planner에 저장

입력:

- `source_run_id`
- `experiment_title`
- `target_hypothesis`
- `purpose`
- `actions`
- `expected_signal`


### 6. `PATCH /planner/items/{item_id}`

목적:

- status / note / priority 수정


## Frontend State Model

### Global State

- `activeTab`
- `currentRunId`
- `selectedHistoryRunId`
- `compareLeftRunId`
- `compareRightRunId`
- `plannerItems`


### Analyze State

- 현재 유지
- 여기에 `sendToPlanner(experimentIdea)` 추가


### History State

- `historyRuns`
- `historyFilter`
- `historySelection`


### Compare State

- `compareResult`
- `compareLoading`


### Planner State

- `plannerFilter`
- `plannerSelection`
- `plannerEditingItemId`


## UI Components

### Session History List

필수 컴포넌트:

- `RunListToolbar`
- `RunListTable`
- `RunSummaryCard`

행 단위 표시:

- run id
- created time
- domain
- coverage badge
- top interpretation
- actions


### Compare View

필수 컴포넌트:

- `CompareSelector`
- `CompareSummary`
- `CompareDiffSection`
- `CompareIdeasSection`

표현 방식:

- 좌/우 2열
- 차이 항목은 강조 색상


### Planner View

필수 컴포넌트:

- `PlannerToolbar`
- `PlannerBoard` 또는 `PlannerList`
- `PlannerItemCard`
- `PlannerDetailDrawer`

초기 버전은 board보다 list가 구현이 쉽고 개발 효율이 높다.


## Data Persistence

planner는 run artifact와 분리된 저장소가 필요하다.

권장 파일:

- `backend/planner/planner_items.json`

이유:

- run은 불변 기록
- planner는 사용자가 상태를 계속 수정하는 작업 영역


## Suggested Execution Order

### Phase 1

가장 빠르게 가치가 나는 단계.

1. `GET /runs`
2. `History` 탭
3. `Open / Compare / Plan` 액션


### Phase 2

비교 작업 강화.

1. `POST /runs/compare`
2. `Compare` 탭
3. 차이 요약 컴포넌트


### Phase 3

실험 planning 분리.

1. planner 저장소 추가
2. planner CRUD API 추가
3. `Planner` 탭
4. run에서 planner로 아이디어 보내기


## Suggested File Changes

### Backend

- `backend/server.py`
  - run list / compare / planner endpoints 추가
- `backend/conversation/memory.py`
  - run summary helper 추가
  - compare helper 추가
- `backend/planner/__init__.py`
- `backend/planner/store.py`
- `backend/planner/models.py`


### Frontend

- 현재 `frontend/index.html` 안에서 먼저 구현 가능
- 다만 작업량이 커지므로 다음 단계부터는 분리 권장

권장 분리안:

- `frontend/app.js`
- `frontend/styles.css`
- `frontend/views/analyze.js`
- `frontend/views/history.js`
- `frontend/views/compare.js`
- `frontend/views/planner.js`


## UX Notes

### History

- 기본 정렬은 최신순
- coverage badge를 강하게 보여준다
- run id 전체를 다 보여주되 줄바꿈 허용


### Compare

- raw JSON 금지
- "무엇이 달라졌는지" 먼저
- 숫자보다는 상태 라벨과 짧은 문장 중심


### Planner

- 실험 아이디어는 카드보다 목록이 빠르다
- status 변경은 드롭다운 1회로 끝나야 한다
- source run으로 바로 돌아가는 링크 필요


## Risks

1. 단일 HTML 파일에 계속 누적하면 유지보수가 급격히 나빠진다.
2. history/compare/planner를 넣는 시점부터는 JS 분리가 사실상 필요하다.
3. planner 상태 저장은 run artifact와 섞으면 안 된다.


## Recommendation

다음 실제 구현은 아래 순서로 간다.

1. `GET /runs` + `History` 탭
2. `POST /runs/compare` + `Compare` 탭
3. planner 저장소 + `Planner` 탭
4. 필요 시 프런트 파일 분리


## Definition of Done

다음 조건을 만족하면 1차 완료로 본다.

- 최근 run 목록이 화면에 표시된다.
- history에서 run을 다시 열 수 있다.
- 두 run을 선택해 비교할 수 있다.
- fallback 또는 proposal에서 나온 experiment idea를 planner로 보낼 수 있다.
- planner에서 status와 note를 수정할 수 있다.
