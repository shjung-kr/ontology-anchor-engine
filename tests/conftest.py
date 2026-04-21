from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import backend.auth as auth_module
import backend.user_storage as user_storage


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    user_root = tmp_path / "user_data"
    system_root = user_root / "_system"
    monkeypatch.setattr(user_storage, "USER_DATA_ROOT", user_root)
    monkeypatch.setattr(user_storage, "SYSTEM_ROOT", system_root)
    return {"user_root": user_root, "system_root": system_root}


@pytest.fixture(autouse=True)
def isolated_auth_env(monkeypatch, isolated_storage):
    monkeypatch.setattr(auth_module, "DEFAULT_PASSWORD_MIN_LENGTH", 8)
    monkeypatch.setattr(auth_module, "DEFAULT_SESSION_TTL_HOURS", 12)
    monkeypatch.setattr(auth_module, "DEFAULT_SESSION_IDLE_MINUTES", 60)
    monkeypatch.setattr(auth_module, "DEFAULT_LOGIN_WINDOW_SECONDS", 300)
    monkeypatch.setattr(auth_module, "DEFAULT_LOGIN_MAX_FAILURES", 5)
    return isolated_storage
