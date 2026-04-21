from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent
USER_DATA_ROOT = BASE_DIR / "user_data"
SYSTEM_ROOT = USER_DATA_ROOT / "_system"

_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def sanitize_user_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower())
    normalized = normalized.strip(".-_")
    if not normalized:
        raise ValueError("user_id must contain at least one letter or digit")
    if normalized in {".", "..", "_system"}:
        raise ValueError("user_id is not allowed")
    return normalized


def get_current_user_id() -> str:
    user_id = _current_user_id.get()
    if not user_id:
        raise RuntimeError("user context is not set")
    return user_id


@contextmanager
def user_scope(user_id: str) -> Iterator[str]:
    normalized = sanitize_user_id(user_id)
    token = _current_user_id.set(normalized)
    try:
        yield normalized
    finally:
        _current_user_id.reset(token)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_root(user_id: str | None = None) -> Path:
    return ensure_dir(USER_DATA_ROOT / sanitize_user_id(user_id or get_current_user_id()))


def get_user_runs_dir(user_id: str | None = None) -> Path:
    return ensure_dir(get_user_root(user_id) / "runs")


def get_user_overlay_dir(user_id: str | None = None) -> Path:
    return ensure_dir(get_user_root(user_id) / "ontology_overlays")


def get_user_experiment_sets_path(user_id: str | None = None) -> Path:
    return get_user_root(user_id) / "experiment_sets" / "sets.json"


def get_user_profile_path(user_id: str | None = None) -> Path:
    return get_user_root(user_id) / "profile.json"


def get_accounts_path() -> Path:
    return ensure_dir(SYSTEM_ROOT) / "accounts.json"


def get_sessions_path() -> Path:
    return ensure_dir(SYSTEM_ROOT) / "sessions.json"


def get_login_attempts_path() -> Path:
    return ensure_dir(SYSTEM_ROOT) / "login_attempts.json"
