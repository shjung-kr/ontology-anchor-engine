from typing import Dict, Any, List

def infer_measurement_conditions(stats: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    inferred: List[str] = []

    if stats.get("n_points", 0) >= 20 and stats.get("V_unique", 0) >= 5:
        inferred.append("measurement_conditions.sweep_iv")

    if any(k in metadata for k in ["pulse_width", "duty_cycle", "pulse_period", "pulse_frequency"]):
        inferred.append("measurement_conditions.pulsed_iv")

    if any(k in metadata for k in ["dwell_time", "settling_time", "delay_time", "integration_time"]):
        inferred.append("measurement_conditions.steady_state_dc_iv")

    return inferred
