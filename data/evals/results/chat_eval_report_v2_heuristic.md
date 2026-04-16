# Chat Eval Summary

- generated_at_utc: `2026-04-16T08:16:54Z`
- benchmark_file: `/home/shjung/projects/ontology-anchor-engine/data/evals/chat_eval_questions.json`
- judge_mode: `heuristic`

## Overall Scores

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| rule_based | 3.5 | 2.094 | 3.5 | 4.969 | 4.469 | 3 |
| llm_context | 4.25 | 2.562 | 4.312 | 4.969 | 5 | 3.281 |

## Improvement vs Rule-Based

| axis | delta | improvement_percent |
| --- | --- | --- |
| question_fit | 0.75 | 21.43 |
| evidence_use | 0.468 | 22.35 |
| depth | 0.812 | 23.2 |
| accuracy_guardedness | 0.0 | 0.0 |
| naturalness | 0.531 | 11.88 |
| actionability | 0.281 | 9.37 |

## rule_based

- case_count: `32`
- ontology_leak_rate: `0.0`
- repeated_opening_rate: `0.531`

### By Category

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| artifact_check | 2 | 1 | 2.333 | 5 | 4 | 3 |
| assumption_check | 4.5 | 2.5 | 4 | 5 | 5 | 3 |
| meaning_explanation | 3.2 | 2 | 3.1 | 5 | 4.5 | 3 |
| mechanism_why | 3.4 | 2 | 3.6 | 5 | 4 | 3 |
| next_experiment | 3 | 1.75 | 3.5 | 4.75 | 4.25 | 2.5 |
| turn_on_cause | 4.667 | 3 | 5 | 5 | 5 | 3 |
| turn_on_reduction | 4.333 | 2.667 | 3.667 | 5 | 4.667 | 3.667 |

### Lowest-Scoring Cases

| case_id | category | total_score | question |
| --- | --- | --- | --- |
| next_experiment_03 | next_experiment | 16 | measurement anomaly와 mechanism을 동시에 가를 수 있는 실험을 제안해줘. |
| next_experiment_04 | next_experiment | 16 | 연구 미팅 전에 바로 해볼 만한 최소 실험 세트를 정리해줘. |
| artifact_check_01 | artifact_check | 17 | 이 데이터에서 measurement artifact 가능성도 있는지 봐줘. |
| artifact_check_02 | artifact_check | 17 | 이 패턴이 진짜 transport signature인지, 아니면 측정 문제인지 어떻게 구분해? |
| turn_on_reduce_03 | turn_on_reduction | 18 | 전압을 덜 올려도 전류가 켜지게 만들려면 무엇을 바꾸는 게 유리해? |

## llm_context

- case_count: `32`
- ontology_leak_rate: `0.0`
- repeated_opening_rate: `0.0`

### By Category

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| artifact_check | 3.333 | 2 | 4.333 | 5 | 5 | 3 |
| assumption_check | 5 | 3 | 4.75 | 5 | 5 | 3 |
| meaning_explanation | 4.5 | 2.8 | 4.5 | 5 | 5 | 3 |
| mechanism_why | 3.8 | 2.4 | 4.2 | 5 | 5 | 3 |
| next_experiment | 4 | 2.25 | 4 | 4.75 | 5 | 4.75 |
| turn_on_cause | 4.667 | 3 | 4.333 | 5 | 5 | 3 |
| turn_on_reduction | 4 | 2 | 3.667 | 5 | 5 | 3.667 |

### Lowest-Scoring Cases

| case_id | category | total_score | question |
| --- | --- | --- | --- |
| fn_why_02 | mechanism_why | 22 | 현재 해석이 FN 쪽으로 올라간 직접 이유를 짧게 설명해줘. |
| turn_on_reduce_01 | turn_on_reduction | 22 | 턴온 전압을 낮추려면 어떤 실험 변수를 먼저 바꾸는 게 좋을까? |
| turn_on_reduce_03 | turn_on_reduction | 22 | 전압을 덜 올려도 전류가 켜지게 만들려면 무엇을 바꾸는 게 유리해? |
| artifact_check_02 | artifact_check | 22 | 이 패턴이 진짜 transport signature인지, 아니면 측정 문제인지 어떻게 구분해? |
| artifact_check_03 | artifact_check | 22 | 노이즈나 설정 문제 때문에 이렇게 보였을 가능성도 있어? |
