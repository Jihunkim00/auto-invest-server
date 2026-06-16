from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _disable_agent_openai(monkeypatch):
    settings = SimpleNamespace(
        openai_api_key=None,
        openai_model="test-agent-model",
        openai_reasoning_effort="low",
    )
    monkeypatch.setattr("app.services.agent_command_parser_service.get_settings", lambda: settings)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_parse_agent_command_endpoint_logs_and_returns_safety(client):
    response = client.post(
        "/agent/commands/parse",
        json={
            "conversation_id": "conv-pr56",
            "message": "내일 10시에 삼성전자 조건 맞으면 3만원 사줘",
            "context": {
                "default_market": "KR",
                "default_provider": "kis",
                "timezone": "Asia/Seoul",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "parsed"
    assert body["parser_status"] == "fallback"
    assert body["command_log_id"] is not None
    assert body["command"]["command_type"] == "CREATE_AGENT_PLAN"
    assert body["command"]["requires_auth"] is True
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["setting_changed"] is False

    recent = client.get("/agent/commands/recent", params={"conversation_id": "conv-pr56"})
    assert recent.status_code == 200
    recent_body = recent.json()
    assert recent_body["count"] == 1
    item = recent_body["commands"][0]
    assert item["id"] == body["command_log_id"]
    assert item["command_type"] == "CREATE_AGENT_PLAN"
    assert item["command"]["symbol"] == "005930"
    assert item["safety"]["scheduler_changed"] is False

    detail = client.get(f"/agent/commands/{body['command_log_id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["command"]["budget"]["amount"] == 30000


def test_parse_agent_command_endpoint_handles_ambiguous_buy(client):
    response = client.post(
        "/agent/commands/parse",
        json={
            "message": "삼성전자 사줘",
            "context": {"default_market": "KR", "default_provider": "kis"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["command"]["needs_clarification"] is True
    assert body["command"]["clarification_question"]
    assert body["safety"]["real_order_submitted"] is False


def test_agent_command_detail_404(client):
    response = client.get("/agent/commands/999999")

    assert response.status_code == 404
