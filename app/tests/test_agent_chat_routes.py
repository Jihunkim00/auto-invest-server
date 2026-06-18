from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_agent_chat_conversation_routes_create_list_get_messages_archive(client):
    created = client.post(
        "/agent/chat/conversations",
        json={"source": "flutter_dashboard", "metadata": {"source": "flutter_dashboard"}},
    )

    assert created.status_code == 200
    conversation = created.json()["conversation"]
    key = conversation["conversation_key"]
    assert conversation["status"] == "active"

    listed = client.get("/agent/chat/conversations")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    detail = client.get(f"/agent/chat/conversations/{key}")
    assert detail.status_code == 200
    assert detail.json()["conversation"]["conversation_key"] == key

    appended = client.post(
        f"/agent/chat/conversations/{key}/messages",
        json={
            "role": "user",
            "text": "Show positions",
            "message_type": "plain_text",
        },
    )
    assert appended.status_code == 200
    assert appended.json()["message"]["text"] == "Show positions"

    messages = client.get(f"/agent/chat/conversations/{key}/messages")
    assert messages.status_code == 200
    assert messages.json()["count"] == 1
    assert messages.json()["messages"][0]["role"] == "user"

    archived = client.post(f"/agent/chat/conversations/{key}/archive")
    assert archived.status_code == 200
    assert archived.json()["conversation"]["status"] == "archived"
    assert client.get("/agent/chat/conversations").json()["count"] == 0
    assert client.get("/agent/chat/conversations", params={"status": "archived"}).json()["count"] == 1


def test_agent_chat_routes_invalid_conversation_returns_404(client):
    assert client.get("/agent/chat/conversations/missing").status_code == 404
    assert client.get("/agent/chat/conversations/missing/messages").status_code == 404
    assert (
        client.post(
            "/agent/chat/conversations/missing/messages",
            json={"role": "user", "text": "hello"},
        ).status_code
        == 404
    )
    assert client.post("/agent/chat/conversations/missing/archive").status_code == 404
