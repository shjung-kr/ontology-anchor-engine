"""
I-V 도메인 공통 상수와 파일 로딩 유틸리티.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.user_storage import get_user_runs_dir

BASE_DIR = Path(__file__).resolve().parents[2]
DOMAIN_DIR = Path(__file__).resolve().parent
ONTOLOGY_ROOT = BASE_DIR / "ontology" / "iv"
LEGACY_ONTOLOGY_ROOT = BASE_DIR / "ontology"
PROMPTS_DIR = BASE_DIR.parent / "prompts"


def get_runs_dir() -> Path:
    return get_user_runs_dir()

TERM_LABEL_OVERRIDES = {
    "iv_regimes.low_field_regime": "저전압 구간",
    "iv_regimes.high_field_regime": "고전압 구간",
    "measurement_conditions.steady_state_dc_iv": "정상상태 DC I-V 측정",
    "measurement_conditions.pulsed_iv": "펄스 I-V 측정",
    "measurement_conditions.sweep_iv": "스윕 I-V 측정",
}


def get_ontology_root() -> Path:
    """
    I-V 도메인 ontology 루트를 반환한다.
    """

    if ONTOLOGY_ROOT.is_dir():
        return ONTOLOGY_ROOT
    return LEGACY_ONTOLOGY_ROOT


def unique_preserve_order(items: List[str]) -> List[str]:
    """
    입력 순서를 유지하며 중복을 제거한다.
    """

    seen = set()
    output: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def load_json_files(dir_path: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """
    디렉터리 아래 JSON 파일을 읽어 반환한다.
    """

    loaded: List[Tuple[Path, Dict[str, Any]]] = []
    if not dir_path.is_dir():
        return loaded

    for path in sorted(dir_path.glob("*.json")):
        try:
            loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return loaded


def extract_statement_from_definition(obj: Dict[str, Any]) -> Optional[str]:
    """
    assumption 정의 객체에서 대표 설명 문장을 뽑는다.
    """

    statement = obj.get("statement")
    if isinstance(statement, str) and statement.strip():
        return statement.strip()

    definition = obj.get("definition")
    if isinstance(definition, dict):
        for lang in ("ko", "en"):
            value = definition.get(lang)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(definition, str) and definition.strip():
        return definition.strip()

    labels = obj.get("labels")
    if isinstance(labels, dict):
        for lang in ("ko", "en"):
            value = labels.get(lang)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("description", "label", "summary"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def coerce_assumption_definition(
    assumption_id: str,
    obj: Dict[str, Any],
    source_file: str,
) -> Optional[Dict[str, Any]]:
    """
    다양한 assumption 표현을 표준 카드 형태로 정규화한다.
    """

    if not isinstance(assumption_id, str) or not assumption_id.strip() or not isinstance(obj, dict):
        return None

    statement = extract_statement_from_definition(obj)
    if not statement:
        return None

    impact_axis = obj.get("impact_axis")
    if not isinstance(impact_axis, list):
        impact_axis = []

    card: Dict[str, Any] = {
        "assumption_id": assumption_id.strip(),
        "statement": statement,
        "impact_axis": impact_axis,
        "_source_file": source_file,
    }

    labels = obj.get("labels")
    if isinstance(labels, dict):
        card["labels"] = labels

    for extra_key in ("severity", "source", "description_ko", "note", "tags", "category"):
        if extra_key in obj:
            card[extra_key] = obj[extra_key]

    return card


def _iter_ontology_entries(obj: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    entries: List[Tuple[str, Dict[str, Any]]] = []
    if not isinstance(obj, dict):
        return entries

    object_id = obj.get("id") or obj.get("ontology_id")
    if isinstance(object_id, str) and object_id.strip():
        entries.append((object_id.strip(), obj))

    for key, value in obj.items():
        if isinstance(key, str) and "." in key and isinstance(value, dict):
            payload = dict(value)
            payload.setdefault("id", key)
            entries.append((key.strip(), payload))

    for list_key in ("items", "assumptions"):
        items = obj.get(list_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id") or item.get("ontology_id") or item.get("assumption_id")
            if isinstance(item_id, str) and item_id.strip():
                entries.append((item_id.strip(), item))

    return entries


def _fallback_term_label(term_id: str) -> str:
    suffix = term_id.split(".", 1)[-1] if "." in term_id else term_id
    return suffix.replace("_", " ").strip() or term_id


def _contains_hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


@lru_cache(maxsize=1)
def load_iv_term_catalog() -> Dict[str, Dict[str, str]]:
    """
    I-V ontology 엔티티를 자연어 라벨/설명으로 조회하기 위한 카탈로그를 구성한다.
    """

    catalog: Dict[str, Dict[str, str]] = {}
    ontology_root = get_ontology_root()
    search_dirs = [
        ontology_root / "00_lexicon",
        ontology_root / "01_iv_regimes",
        ontology_root / "02_iv_features",
        ontology_root / "02_measurement_validations",
        ontology_root / "04_scientific_justification",
    ]

    for dir_path in search_dirs:
        for _, obj in load_json_files(dir_path):
            for term_id, payload in _iter_ontology_entries(obj):
                labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
                definition = payload.get("definition")
                explanation = ""
                if isinstance(definition, dict):
                    explanation = str(definition.get("ko") or definition.get("en") or "").strip()
                elif isinstance(definition, str):
                    explanation = definition.strip()
                if not explanation:
                    explanation = str(
                        payload.get("description_ko")
                        or payload.get("description")
                        or payload.get("statement")
                        or payload.get("label")
                        or ""
                    ).strip()

                label = str(
                    labels.get("ko")
                    or labels.get("en")
                    or payload.get("label")
                    or payload.get("canonical_name")
                    or _fallback_term_label(term_id)
                ).strip()

                existing = catalog.get(term_id, {})
                existing_label = existing.get("label", "")
                existing_description = existing.get("description", "")
                fallback_label = _fallback_term_label(term_id)

                chosen_label = label or existing_label or fallback_label
                if existing_label and existing_label != fallback_label:
                    if label == fallback_label or not label:
                        chosen_label = existing_label
                    elif _contains_hangul(existing_label) and not _contains_hangul(label):
                        chosen_label = existing_label

                chosen_description = explanation or existing_description

                catalog[term_id] = {
                    "label": chosen_label or fallback_label,
                    "description": chosen_description,
                }

    return catalog


def lookup_term_text(term_id: str) -> Dict[str, str]:
    """
    ontology ID에 대응하는 자연어 라벨/설명을 반환한다.
    """

    if not isinstance(term_id, str) or not term_id.strip():
        return {"label": "", "description": ""}
    term_id = term_id.strip()
    entry = load_iv_term_catalog().get(term_id, {})
    override_label = TERM_LABEL_OVERRIDES.get(term_id)
    return {
        "label": override_label or entry.get("label") or _fallback_term_label(term_id),
        "description": entry.get("description") or "",
    }


def term_label(term_id: str) -> str:
    return lookup_term_text(term_id).get("label", "")


def term_description(term_id: str) -> str:
    return lookup_term_text(term_id).get("description", "")


def join_term_labels(term_ids: List[str], max_items: Optional[int] = None) -> str:
    labels: List[str] = []
    for index, term_id in enumerate(term_ids):
        if max_items is not None and index >= max_items:
            break
        if not isinstance(term_id, str) or not term_id.strip():
            continue
        labels.append(term_label(term_id))
    return ", ".join(labels)


def _describe_decade_span_ko(raw_value: str) -> str:
    try:
        span = float(raw_value)
    except Exception:
        span = None

    if span is None:
        return f"데이터 전체에서 |I| 값 범위가 약 {raw_value} decade에 걸쳐 분포합니다"

    if span >= 6:
        meaning = "전류 크기가 매우 넓은 범위에 걸쳐 변해, 단일한 약한 변화라기보다 강한 구간 변화나 메커니즘 차이가 숨어 있을 가능성을 시사합니다"
    elif span >= 3:
        meaning = "전류 변화 폭이 충분히 커서 단순 잡음보다는 실제 거동 변화가 반영되었을 가능성이 큽니다"
    else:
        meaning = "전류 변화 폭이 아주 크지는 않아, 해석 시 노이즈나 측정 분해능 영향도 함께 봐야 합니다"

    return f"데이터 전체에서 |I| 값 범위가 약 {raw_value} decade에 걸쳐 분포합니다. 이는 전류의 동적 범위가 넓다는 뜻이며, {meaning}"


def _describe_regime_split_ko(raw_value: str) -> str:
    try:
        threshold = float(raw_value)
    except Exception:
        threshold = None

    if threshold is None:
        return f"|V|={raw_value} 부근에서 거동이 나뉘는 경계가 관찰됩니다"

    return (
        f"|V|={raw_value} 부근에서 거동이 나뉘는 경계가 관찰됩니다. "
        "이는 그 전압을 기준으로 저전압 구간과 고전압 구간의 전류 증가 방식이 달라질 수 있다는 뜻이며, "
        "하나의 메커니즘만으로 전체 구간을 설명하기보다 구간별 해석이 필요할 수 있음을 시사합니다"
    )


def _describe_loglog_slope_ko(raw_value: str, scaling_hint: str) -> str:
    try:
        slope = float(raw_value)
    except Exception:
        slope = None

    if slope is None:
        return f"저전압 구간의 log-log 기울기는 {raw_value}이며, {scaling_hint} 패턴으로 읽힙니다"

    if 0.85 <= slope <= 1.15:
        meaning = "전압이 증가할 때 전류도 거의 비례적으로 증가한다는 뜻입니다"
    elif slope > 1.15:
        meaning = "전압이 조금만 올라가도 전류가 훨씬 더 빠르게 증가한다는 뜻입니다"
    elif slope >= 0:
        meaning = "전압 증가에 따라 전류가 증가하긴 하지만, 거의 선형보다는 완만한 편이라는 뜻입니다"
    else:
        meaning = "저전압 구간에서 전류 변화가 단순 증가 패턴이 아니어서, 노이즈나 측정 조건의 영향을 함께 점검해야 한다는 뜻입니다"

    if abs(slope) >= 10:
        meaning += " 값이 매우 크므로 작은 전압 변화에도 전류가 급격히 변하는 매우 민감한 구간일 가능성이 큽니다"

    return f"저전압 구간의 log-log 기울기는 {raw_value}로, {scaling_hint} 스케일링을 보입니다. 이는 {meaning}"


def summarize_observation_pattern_ko(pattern: str) -> str:
    if not isinstance(pattern, str):
        return ""
    text = pattern.strip()
    if not text:
        return ""

    text = re.sub(
        r"\|I\| spans about ([0-9.+-]+) decades across the dataset",
        lambda match: _describe_decade_span_ko(match.group(1)),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"a regime split is detected near \|V\|=([0-9.eE+-]+)",
        lambda match: _describe_regime_split_ko(match.group(1)),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"the low-field log-log slope is ([0-9.+-]+), indicating approximately linear scaling",
        lambda match: _describe_loglog_slope_ko(match.group(1), "거의 선형에 가까운"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"the low-field log-log slope is ([0-9.+-]+), indicating super-linear scaling",
        lambda match: _describe_loglog_slope_ko(match.group(1), "선형보다 더 가파른 초선형"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*;\s*", ". ", text)
    if text and not text.endswith("."):
        text += "."
    return text


def format_confirmed_conditions_ko(conditions: Dict[str, Any]) -> str:
    if not isinstance(conditions, dict) or not conditions:
        return "(none)"

    parts: List[str] = []
    temperature = conditions.get("temperature")
    if temperature == "room_temperature":
        parts.append("온도 조건은 상온으로 확인되었습니다")

    reproducibility = conditions.get("reproducibility")
    if reproducibility == "reproducible":
        parts.append("반복 측정 재현성이 확인되었습니다")
    elif reproducibility == "not_reproducible":
        parts.append("반복 측정 재현성이 낮거나 불확실합니다")

    measurement_setup = conditions.get("measurement_setup")
    if measurement_setup == "pulsed_bias":
        parts.append("측정 방식은 펄스 바이어스로 이해했습니다")
    elif measurement_setup == "steady_state_dc":
        parts.append("측정 방식은 정상상태 DC로 이해했습니다")

    for key in ("device_context", "stack_or_thickness", "electrode_context", "measurement_setup_details", "sweep_context"):
        value = conditions.get(key)
        if isinstance(value, str) and value.strip():
            label_map = {
                "device_context": "디바이스/계면 맥락",
                "stack_or_thickness": "적층/두께 정보",
                "electrode_context": "전극 정보",
                "measurement_setup_details": "측정 설정 메모",
                "sweep_context": "스윕 정보",
            }
            parts.append(f"{label_map[key]}: {value.strip()}")

    for key, value in conditions.items():
        if key in {"temperature", "reproducibility", "measurement_setup", "device_context", "stack_or_thickness", "electrode_context", "measurement_setup_details", "sweep_context"}:
            continue
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")

    return "; ".join(parts) if parts else str(conditions)
