# label_ko.py
"""
Korean labels for L1 keywords and SJ ontology
(OUTPUT LAYER ONLY)
"""

L1_KEYWORD_KO = {
    "strong_temperature_dependence": "강한 온도 의존성",
    "moderate_temperature_dependence": "중간 수준의 온도 의존성",
    "weak_temperature_dependence": "약한 온도 의존성",

    "strong_voltage_dependence": "강한 전압 의존성",
    "moderate_voltage_dependence": "중간 수준의 전압 의존성",
    "weak_voltage_dependence": "약한 전압 의존성",

    "generic_dependence": "일반적인 의존성",
    "INJECTION_DOMINATED_CONDUCTION": "전류 주입에 의해 지배되는 전도 메커니즘",
    "RECOMBINATION_LIMITED_CURRENT": "재결합 과정에 의해 제한되는 전류 거동",
}

SJ_ONTOLOGY_KO = {
    "SJ_IV_TRANSPORT_ROOM_EXP": {
        "label": "실온 IV 수송의 지수적 거동",
        "description": (
            "실온 조건에서 전압 증가에 따라 전류가 "
            "비선형적으로 증가하는 수송 특성을 설명하는 "
            "과학적 정당화입니다."
        )
    }
}
