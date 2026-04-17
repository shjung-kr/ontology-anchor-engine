from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import List

from backend.conversation.memory import utc_now_iso
from backend.experiment_sets.models import (
    ExperimentRunLink,
    ExperimentSet,
    ExperimentSetAddRunRequest,
    ExperimentSetCreateRequest,
    ExperimentSetUpdateRequest,
)
from backend.user_storage import get_user_experiment_sets_path


BASE_DIR = Path(__file__).resolve().parent


def _store_path() -> Path:
    return get_user_experiment_sets_path()


def _ensure_store() -> None:
    store_path = _store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if not store_path.exists():
        store_path.write_text(json.dumps({"sets": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_store() -> dict:
    _ensure_store()
    try:
        return json.loads(_store_path().read_text(encoding="utf-8"))
    except Exception:
        return {"sets": []}


def _write_store(payload: dict) -> None:
    _ensure_store()
    _store_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_experiment_sets() -> List[ExperimentSet]:
    payload = _load_store()
    items = [ExperimentSet(**item) for item in payload.get("sets", []) if isinstance(item, dict)]
    items.sort(key=lambda item: item.updated_at_utc, reverse=True)
    return items


def get_experiment_set(set_id: str) -> ExperimentSet:
    for item in list_experiment_sets():
        if item.set_id == set_id:
            return item
    raise KeyError(f"unknown experiment set: {set_id}")


def create_experiment_set(data: ExperimentSetCreateRequest) -> ExperimentSet:
    now = utc_now_iso()
    item = ExperimentSet(
        set_id=f"set_{secrets.token_hex(4)}",
        title=data.title,
        experiment_goal=data.experiment_goal,
        primary_question=data.primary_question,
        hypotheses=data.hypotheses,
        control_variables=data.control_variables,
        sweep_variables=data.sweep_variables,
        success_criteria=data.success_criteria,
        created_at_utc=now,
        updated_at_utc=now,
    )
    payload = _load_store()
    payload["sets"] = [item.model_dump()] + list(payload.get("sets", []))
    _write_store(payload)
    return item


def update_experiment_set(set_id: str, data: ExperimentSetUpdateRequest) -> ExperimentSet:
    payload = _load_store()
    updated: List[dict] = []
    found = False
    for raw in payload.get("sets", []):
        if not isinstance(raw, dict):
            continue
        item = ExperimentSet(**raw)
        if item.set_id == set_id:
            found = True
            patch = data.model_dump(exclude_none=True)
            for key, value in patch.items():
                setattr(item, key, value)
            item.updated_at_utc = utc_now_iso()
            updated.append(item.model_dump())
        else:
            updated.append(item.model_dump())
    if not found:
        raise KeyError(f"unknown experiment set: {set_id}")
    payload["sets"] = updated
    _write_store(payload)
    return get_experiment_set(set_id)


def add_run_to_experiment_set(set_id: str, data: ExperimentSetAddRunRequest) -> ExperimentSet:
    payload = _load_store()
    updated: List[dict] = []
    found = False
    for raw in payload.get("sets", []):
        if not isinstance(raw, dict):
            continue
        item = ExperimentSet(**raw)
        if item.set_id == set_id:
            found = True
            existing = [run for run in item.runs if run.run_id != data.run_id]
            existing.append(ExperimentRunLink(**data.model_dump()))
            item.runs = existing
            item.updated_at_utc = utc_now_iso()
            updated.append(item.model_dump())
        else:
            updated.append(item.model_dump())
    if not found:
        raise KeyError(f"unknown experiment set: {set_id}")
    payload["sets"] = updated
    _write_store(payload)
    return get_experiment_set(set_id)


def save_experiment_set(item: ExperimentSet) -> ExperimentSet:
    payload = _load_store()
    updated: List[dict] = []
    found = False
    for raw in payload.get("sets", []):
        if not isinstance(raw, dict):
            continue
        existing = ExperimentSet(**raw)
        if existing.set_id == item.set_id:
            found = True
            updated.append(item.model_dump())
        else:
            updated.append(existing.model_dump())
    if not found:
        updated.append(item.model_dump())
    payload["sets"] = updated
    _write_store(payload)
    return get_experiment_set(item.set_id)
