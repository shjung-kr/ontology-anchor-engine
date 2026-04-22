# C-V / EIS Ontology Prep

## 목적

`ontology-anchor-engine`의 기존 `I-V` 구조를 최대한 재사용하면서, `C-V`와 `impedance/EIS`를 하나의 전기적 측정 계열 도메인으로 확장하기 위한 준비 상태를 만든다.

이번 단계의 산출물은 다음에 집중한다.

- `backend/ontology/cv_eis/` 도메인 팩 스켈레톤 추가
- `parser / feature / proposal` 구조에 맞는 feature 축 정의
- 이후 구현 시 바로 사용할 수 있는 interpretation 카드 초안 정리

아직 하지 않은 일은 다음과 같다.

- `backend/domain_registry.json` 등록
- `backend/domains/cv_eis/` 실행 코드 구현
- schema 기반 enum 검증 파이프라인 연결

## 왜 C-V / EIS를 한 도메인으로 묶는가

- 둘 다 `bias`, `frequency`, `small-signal AC`, `complex response` 축을 공유한다.
- C-V에서의 `slope`, `hysteresis`, `frequency dispersion`, `peak`는 EIS의 `semicircle`, `arc depression`, `tail`, `peak frequency`와 feature 추출 관점에서 자연스럽게 이어진다.
- 디바이스 해석 워크플로우에서 `I-V -> C-V -> EIS` 순으로 측정 증거를 조합하기 쉽다.

## 제안한 ontology 축

### measurement_conditions

- `measurement_conditions.capacitance_voltage_sweep`
- `measurement_conditions.impedance_spectroscopy_frequency_sweep`
- `measurement_conditions.small_signal_ac_linearization`
- `measurement_conditions.bias_dependent_impedance`

### electrical_features

- `electrical_features.bias_dependent_capacitance_slope`
- `electrical_features.hysteresis_loop_present`
- `electrical_features.loss_peak_present`
- `electrical_features.semicircle_present`
- `electrical_features.frequency_dispersion_present`
- `electrical_features.warburg_tail_present`

### claim_concepts

- `cv_interpretation.depletion_dominated_capacitance`
- `cv_interpretation.interface_trap_response`
- `eis_interpretation.single_rc_relaxation`
- `eis_interpretation.nonideal_interfacial_capacitance`
- `eis_interpretation.diffusion_limited_response`

## 구현 순서

1. `parser`
   `numeric_pairs`만 가정하는 현재 `parse_vi`와 달리, `cv_eis`는 최소한 다음 입력 형태를 받아야 한다.
   - `bias, capacitance`
   - `frequency, z_real, z_imag`
   - `bias, frequency, capacitance`
   - `bias, frequency, z_real, z_imag`

2. `validator`
   아래 검증이 먼저 필요하다.
   - 열 존재성: `bias`, `frequency`, `capacitance`, `z_real`, `z_imag`
   - 최소 포인트 수
   - 단위/축 혼동 탐지
   - small-signal metadata 존재 여부
   - frequency ordering / branch completeness

3. `feature extractor`
   아래 계산을 최소 feature 세트로 둔다.
   - C-V slope
   - forward/reverse loop area
   - peak prominence / peak frequency
   - semicircle apex / arc count
   - low-frequency tail angle
   - fixed-bias frequency dispersion

4. `proposal evaluator`
   현재 IV의 `required_features ∩ observed_features` 매칭 방식을 그대로 재사용하고, 나중에 `score weighting`만 확장한다.

## 권장 후속 작업

- `backend/domains/cv_eis/`에 최소 실행 스텁 추가
- `backend/ontology/cv_eis/schema/` 도입 또는 공통 schema 일반화
- `scripts/validate_ontology.py`를 도메인-네임스페이스 기반 검증기로 리팩터링
- 샘플 데이터셋 추가
  - 단일 주파수 C-V
  - multi-frequency C-V
  - single semicircle EIS
  - Warburg tail 포함 EIS
