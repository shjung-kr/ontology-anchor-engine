# Domain Expansion Plan

## 1. 확장 가능한 폴더 구조 초안

```text
ontology-anchor-engine/
├─ backend/
│  ├─ core/
│  │  ├─ domain_models.py
│  │  ├─ domain_registry.py
│  │  └─ engine.py
│  ├─ domains/
│  │  ├─ iv/
│  │  │  └─ runner.py
│  │  └─ <new_domain>/
│  │     ├─ runner.py
│  │     ├─ parser.py
│  │     ├─ features.py
│  │     └─ renderer.py
│  ├─ ontology/
│  │  └─ <current_or_legacy_iv_files>
│  ├─ domain_registry.json
│  └─ server.py
├─ docs/
│  └─ architecture/
│     └─ domain-expansion-plan.md
└─ prompts/
   ├─ iv/
   └─ <new_domain>/
```

이 구조의 목적은 공통 엔진과 도메인별 규칙을 분리하는 것입니다. 새 주제를 추가할 때는 `backend/domains/<new_domain>/` 와 대응하는 ontology/prompt 묶음을 추가하고, `backend/domain_registry.json` 에 등록하는 방식으로 확장합니다.

## 2. domain registry 설계안

레지스트리는 다음을 한 곳에서 정의합니다.

- 도메인 식별자
- 입력 형식
- 실행기 함수 경로
- ontology/prompt 디렉터리
- 파이프라인 단계별 구현체 경로

현재 실제 예시는 [backend/domain_registry.json](/home/shjung/projects/ontology-anchor-engine/backend/domain_registry.json) 에 추가되어 있습니다.

핵심 원칙은 다음과 같습니다.

- 서버는 도메인 내부 구현을 직접 import 하지 않고 registry를 통해 실행합니다.
- 새 도메인 추가 시 서버 코드를 수정하지 않는 것을 목표로 합니다.
- 공통 artifact 포맷은 유지하고, 도메인 특화 정보는 `domain_config` 아래에 넣습니다.

## 3. 리팩터링 순서

1. 현재 `v14` I-V 엔진을 유지한 채 공통 실행 레이어를 추가합니다.
2. 서버에 generic endpoint를 추가하고, registry 기반 실행을 병행 도입합니다.
3. I-V 전용 로직을 `backend/domains/iv/` 아래 wrapper로 먼저 이동시킵니다.
4. 이후 parser, feature extractor, renderer를 단계적으로 `domains/iv` 하위로 재배치합니다.
5. ontology 디렉터리도 장기적으로 `backend/ontology/iv/` 같은 네임스페이스 구조로 옮깁니다.
6. 두 번째 도메인을 작게 추가해 실제 확장 경로를 검증합니다.

## 4. JSON 스키마 초안

이번 작업에서 아래 두 개의 스키마 초안을 추가했습니다.

- [domain_registry.schema.json](/home/shjung/projects/ontology-anchor-engine/backend/schema/domain_registry.schema.json)
- [domain_pack.schema.json](/home/shjung/projects/ontology-anchor-engine/backend/schema/domain_pack.schema.json)

용도는 다음과 같습니다.

- `domain_registry.schema.json`
  registry 파일 전체 형식을 검증합니다.
- `domain_pack.schema.json`
  각 도메인 팩이 최소한 어떤 메타데이터를 가져야 하는지 정의합니다.

이 스키마를 기반으로 향후에는 신규 도메인 추가 시 CI에서 형식 검증을 자동화하는 것이 좋습니다.
