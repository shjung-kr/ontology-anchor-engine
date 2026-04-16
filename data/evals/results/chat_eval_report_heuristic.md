# Chat Eval Summary

- generated_at_utc: `2026-04-16T07:30:52Z`
- benchmark_file: `/home/shjung/projects/ontology-anchor-engine/data/evals/chat_eval_questions.json`
- judge_mode: `heuristic`

## Overall Scores

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| rule_based | 3.9 | 2.3 | 3.3 | 5 | 4.6 | 3.4 |
| llm_context | 4.5 | 2.7 | 4.3 | 5 | 5 | 3.3 |

## Improvement vs Rule-Based

| axis | delta | improvement_percent |
| --- | --- | --- |
| question_fit | 0.6 | 15.38 |
| evidence_use | 0.4 | 17.39 |
| depth | 1.0 | 30.3 |
| accuracy_guardedness | 0 | 0.0 |
| naturalness | 0.4 | 8.7 |
| actionability | -0.1 | -2.94 |

## rule_based

- case_count: `10`
- ontology_leak_rate: `0.0`
- repeated_opening_rate: `0.4`

### By Category

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| artifact_check | 2 | 1 | 2 | 5 | 4 | 3 |
| assumption_check | 5 | 3 | 4 | 5 | 5 | 3 |
| meaning_explanation | 3.333 | 2 | 2.667 | 5 | 4.667 | 3 |
| mechanism_why | 3.5 | 2 | 3.5 | 5 | 4 | 3 |
| next_experiment | 5 | 3 | 3 | 5 | 5 | 5 |
| turn_on_cause | 5 | 3 | 5 | 5 | 5 | 3 |
| turn_on_reduction | 5 | 3 | 4 | 5 | 5 | 5 |

### Lowest-Scoring Cases

| case_id | category | total_score | question |
| --- | --- | --- | --- |
| artifact_check_01 | artifact_check | 17 | 이 데이터에서 measurement artifact 가능성도 있는지 봐줘. |
| alt_hypothesis_01 | mechanism_why | 18 | 현재 상위 해석 말고 다른 가능성도 남아 있어? |
| meaning_feature_01 | meaning_explanation | 20 | 전계 강화 전류라는 말이 정확히 무슨 뜻이야? |
| meaning_slope_01 | meaning_explanation | 20 | log-log 기울기가 크다는 건 무슨 의미야? |
| condition_effect_01 | meaning_explanation | 22 | 상온이라는 조건이 왜 이 해석에 영향을 주는 거야? |

## llm_context

- case_count: `10`
- ontology_leak_rate: `0.0`
- repeated_opening_rate: `0.0`

### By Category

| strategy | question_fit | evidence_use | depth | accuracy_guardedness | naturalness | actionability |
| --- | --- | --- | --- | --- | --- | --- |
| artifact_check | 5 | 3 | 4 | 5 | 5 | 3 |
| assumption_check | 5 | 3 | 4 | 5 | 5 | 3 |
| meaning_explanation | 5 | 3 | 5 | 5 | 5 | 3 |
| mechanism_why | 4 | 2.5 | 4.5 | 5 | 5 | 3 |
| next_experiment | 4 | 2 | 2 | 5 | 5 | 5 |
| turn_on_cause | 4 | 3 | 5 | 5 | 5 | 3 |
| turn_on_reduction | 4 | 2 | 4 | 5 | 5 | 4 |

### Lowest-Scoring Cases

| case_id | category | total_score | question |
| --- | --- | --- | --- |
| alt_hypothesis_01 | mechanism_why | 22 | 현재 상위 해석 말고 다른 가능성도 남아 있어? |
| next_experiment_01 | next_experiment | 23 | 이 해석을 검증하려면 다음 실험을 무엇부터 해야 할까? |
| turn_on_reduce_01 | turn_on_reduction | 24 | 턴온 전압을 낮추려면 어떤 실험 변수를 먼저 바꾸는 게 좋을까? |
| turn_on_cause_01 | turn_on_cause | 25 | 턴온 전압이 왜 높게 보일 수 있는지 설명해줘. |
| assumption_barrier_01 | assumption_check | 25 | 유효 퍼텐셜 장벽 존재 가정이 왜 필요한데? |
