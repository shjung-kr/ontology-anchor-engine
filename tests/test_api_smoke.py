from __future__ import annotations

from fastapi.testclient import TestClient

from backend.domains.iv.common import summarize_observation_pattern_ko
import backend.server as server_module


def test_sanitized_json_response_converts_nan_to_null():
    body = server_module.SanitizedJSONResponse({"value": float("nan")}).body.decode("utf-8")
    assert '"value":null' in body


def test_observation_pattern_summary_is_korean():
    text = summarize_observation_pattern_ko("|I| spans about 3.20 decades across the dataset")
    assert "데이터 전체에서 |I| 값 범위" in text
    assert "약 3.20 decade" in text


def test_health_endpoint():
    client = TestClient(server_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_auth_register_login_and_me(monkeypatch):
    monkeypatch.setattr(server_module, "_registration_enabled", lambda: True)
    client = TestClient(server_module.app)

    register_response = client.post(
        "/auth/register",
        json={"user_id": "tester", "password": "strongpass123", "display_name": "Tester"},
    )
    assert register_response.status_code == 200
    token = register_response.json()["session"]["token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["user"]["user_id"] == "tester"
