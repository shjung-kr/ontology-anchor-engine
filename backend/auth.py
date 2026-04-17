from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict

from fastapi import Header, HTTPException

from backend.user_storage import (
    get_accounts_path,
    get_sessions_path,
    get_user_profile_path,
    sanitize_user_id,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)


def _write_json(path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return base64.b64encode(digest).decode("ascii")


def _load_accounts() -> Dict[str, Any]:
    return _load_json(get_accounts_path(), {"users": []})


def _write_accounts(payload: Dict[str, Any]) -> None:
    _write_json(get_accounts_path(), payload)


def _load_sessions() -> Dict[str, Any]:
    return _load_json(get_sessions_path(), {"sessions": []})


def _write_sessions(payload: Dict[str, Any]) -> None:
    _write_json(get_sessions_path(), payload)


@dataclass
class AuthenticatedUser:
    user_id: str
    display_name: str
    token: str


def register_user(user_id: str, password: str, display_name: str | None = None) -> Dict[str, str]:
    normalized = sanitize_user_id(user_id)
    if len(password or "") < 4:
        raise ValueError("password must be at least 4 characters")

    payload = _load_accounts()
    if any(item.get("user_id") == normalized for item in payload.get("users", [])):
        raise ValueError(f"user already exists: {normalized}")

    salt = secrets.token_hex(16)
    user = {
        "user_id": normalized,
        "display_name": (display_name or normalized).strip() or normalized,
        "password_salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at_utc": utc_now_iso(),
    }
    payload["users"] = [user] + [item for item in payload.get("users", []) if isinstance(item, dict)]
    _write_accounts(payload)

    profile_path = get_user_profile_path(normalized)
    if not profile_path.exists():
        _write_json(
            profile_path,
            {
                "user_id": normalized,
                "display_name": user["display_name"],
                "created_at_utc": user["created_at_utc"],
            },
        )
    return {"user_id": normalized, "display_name": user["display_name"]}


def authenticate_user(user_id: str, password: str) -> Dict[str, str]:
    normalized = sanitize_user_id(user_id)
    payload = _load_accounts()
    user = next((item for item in payload.get("users", []) if item.get("user_id") == normalized), None)
    if not user:
        raise ValueError("invalid credentials")

    expected_hash = user.get("password_hash", "")
    actual_hash = _hash_password(password, str(user.get("password_salt", "")))
    if not hmac.compare_digest(expected_hash, actual_hash):
        raise ValueError("invalid credentials")

    sessions = _load_sessions()
    token = secrets.token_urlsafe(32)
    sessions["sessions"] = [
        {
            "token": token,
            "user_id": normalized,
            "display_name": user.get("display_name") or normalized,
            "created_at_utc": utc_now_iso(),
        }
    ] + [item for item in sessions.get("sessions", []) if isinstance(item, dict) and item.get("user_id") != normalized]
    _write_sessions(sessions)
    return {"token": token, "user_id": normalized, "display_name": user.get("display_name") or normalized}


def revoke_token(token: str) -> None:
    sessions = _load_sessions()
    sessions["sessions"] = [item for item in sessions.get("sessions", []) if item.get("token") != token]
    _write_sessions(sessions)


def require_authenticated_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    sessions = _load_sessions()
    item = next((entry for entry in sessions.get("sessions", []) if entry.get("token") == token), None)
    if not item:
        raise HTTPException(status_code=401, detail="invalid session")
    return AuthenticatedUser(
        user_id=str(item.get("user_id") or ""),
        display_name=str(item.get("display_name") or item.get("user_id") or ""),
        token=token,
    )
