from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Dict

from fastapi import Header, HTTPException

from backend.user_storage import (
    get_accounts_path,
    get_login_attempts_path,
    get_sessions_path,
    get_user_profile_path,
    sanitize_user_id,
)

DEFAULT_PASSWORD_MIN_LENGTH = int(os.getenv("AUTH_MIN_PASSWORD_LENGTH", "8"))
DEFAULT_SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "12"))
DEFAULT_SESSION_IDLE_MINUTES = int(os.getenv("AUTH_SESSION_IDLE_MINUTES", "60"))
DEFAULT_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "300"))
DEFAULT_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


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


def _load_login_attempts() -> Dict[str, Any]:
    return _load_json(get_login_attempts_path(), {"attempts": {}})


def _write_login_attempts(payload: Dict[str, Any]) -> None:
    _write_json(get_login_attempts_path(), payload)


def _hash_session_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _is_session_expired(item: Dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_utc_timestamp(str(item.get("expires_at_utc") or ""))
    if expires_at is not None and now >= expires_at:
        return True

    last_seen_at = _parse_utc_timestamp(str(item.get("last_seen_at_utc") or item.get("created_at_utc") or ""))
    if last_seen_at is not None:
        idle_cutoff = now - timedelta(minutes=DEFAULT_SESSION_IDLE_MINUTES)
        if last_seen_at < idle_cutoff:
            return True
    return False


def _prune_sessions(sessions: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    valid_sessions = []
    for item in sessions.get("sessions", []):
        if not isinstance(item, dict):
            continue
        if _is_session_expired(item, now):
            continue
        valid_sessions.append(item)
    cleaned = {"sessions": valid_sessions}
    if cleaned != sessions:
        _write_sessions(cleaned)
    return cleaned


def _check_login_rate_limit(rate_limit_key: str) -> None:
    now = datetime.now(timezone.utc)
    attempts = _load_login_attempts()
    entries = attempts.get("attempts", {})
    recent = []
    for raw_value in entries.get(rate_limit_key, []):
        parsed = _parse_utc_timestamp(str(raw_value))
        if parsed is None:
            continue
        if (now - parsed).total_seconds() <= DEFAULT_LOGIN_WINDOW_SECONDS:
            recent.append(parsed)
    if len(recent) >= DEFAULT_LOGIN_MAX_FAILURES:
        raise ValueError("too many login attempts; please wait and try again")


def _record_login_failure(rate_limit_key: str) -> None:
    now = datetime.now(timezone.utc)
    attempts = _load_login_attempts()
    entries = attempts.setdefault("attempts", {})
    recent = []
    for raw_value in entries.get(rate_limit_key, []):
        parsed = _parse_utc_timestamp(str(raw_value))
        if parsed is None:
            continue
        if (now - parsed).total_seconds() <= DEFAULT_LOGIN_WINDOW_SECONDS:
            recent.append(parsed)
    recent.append(now)
    entries[rate_limit_key] = [item.replace(microsecond=0).isoformat().replace("+00:00", "Z") for item in recent]
    _write_login_attempts(attempts)


def _clear_login_failures(rate_limit_key: str) -> None:
    attempts = _load_login_attempts()
    entries = attempts.get("attempts", {})
    if rate_limit_key in entries:
        entries.pop(rate_limit_key, None)
        _write_login_attempts(attempts)


@dataclass
class AuthenticatedUser:
    user_id: str
    display_name: str
    token: str


def register_user(user_id: str, password: str, display_name: str | None = None) -> Dict[str, str]:
    normalized = sanitize_user_id(user_id)
    if len(password or "") < DEFAULT_PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {DEFAULT_PASSWORD_MIN_LENGTH} characters")

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


def authenticate_user(user_id: str, password: str, rate_limit_key: str | None = None) -> Dict[str, str]:
    normalized = sanitize_user_id(user_id)
    login_key = rate_limit_key or f"user:{normalized}"
    _check_login_rate_limit(login_key)
    payload = _load_accounts()
    user = next((item for item in payload.get("users", []) if item.get("user_id") == normalized), None)
    if not user:
        _record_login_failure(login_key)
        raise ValueError("invalid credentials")

    expected_hash = user.get("password_hash", "")
    actual_hash = _hash_password(password, str(user.get("password_salt", "")))
    if not hmac.compare_digest(expected_hash, actual_hash):
        _record_login_failure(login_key)
        raise ValueError("invalid credentials")

    _clear_login_failures(login_key)
    sessions = _prune_sessions(_load_sessions())
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = now + timedelta(hours=DEFAULT_SESSION_TTL_HOURS)
    sessions["sessions"] = [
        {
            "token_hash": _hash_session_token(token),
            "user_id": normalized,
            "display_name": user.get("display_name") or normalized,
            "created_at_utc": now.isoformat().replace("+00:00", "Z"),
            "last_seen_at_utc": now.isoformat().replace("+00:00", "Z"),
            "expires_at_utc": expires_at.isoformat().replace("+00:00", "Z"),
        }
    ] + [item for item in sessions.get("sessions", []) if isinstance(item, dict) and item.get("user_id") != normalized]
    _write_sessions(sessions)
    return {"token": token, "user_id": normalized, "display_name": user.get("display_name") or normalized}


def revoke_token(token: str) -> None:
    token_hash = _hash_session_token(token)
    sessions = _prune_sessions(_load_sessions())
    sessions["sessions"] = [
        item
        for item in sessions.get("sessions", [])
        if item.get("token_hash") != token_hash and item.get("token") != token
    ]
    _write_sessions(sessions)


def require_authenticated_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    token_hash = _hash_session_token(token)
    sessions = _prune_sessions(_load_sessions())
    item = next(
        (
            entry
            for entry in sessions.get("sessions", [])
            if entry.get("token_hash") == token_hash or entry.get("token") == token
        ),
        None,
    )
    if not item:
        raise HTTPException(status_code=401, detail="invalid session")
    item["last_seen_at_utc"] = utc_now_iso()
    _write_sessions(sessions)
    return AuthenticatedUser(
        user_id=str(item.get("user_id") or ""),
        display_name=str(item.get("display_name") or item.get("user_id") or ""),
        token=token,
    )
