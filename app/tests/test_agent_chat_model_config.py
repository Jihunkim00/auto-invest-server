from __future__ import annotations

from types import SimpleNamespace

from app.config import Settings
from app.services.agent_command_parser_service import AgentCommandParserService


def _settings(**values):
    base = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "_env_file": None,
    }
    base.update(values)
    return Settings(**base)


def test_agent_chat_model_default_is_gpt_5_4_mini():
    settings = _settings()

    assert settings.agent_chat_model == "gpt-5.4-mini"
    assert settings.agent_chat_reasoning_effort == "low"
    assert settings.agent_chat_temperature == 0
    assert settings.agent_chat_timeout_seconds == 20
    assert settings.agent_chat_fallback_enabled is True


def test_agent_chat_model_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_MODEL", "test-chat-model")
    monkeypatch.setenv("AGENT_CHAT_REASONING_EFFORT", "minimal")
    monkeypatch.setenv("AGENT_CHAT_TEMPERATURE", "0.25")
    monkeypatch.setenv("AGENT_CHAT_TIMEOUT_SECONDS", "7")

    settings = _settings()

    assert settings.agent_chat_model == "test-chat-model"
    assert settings.agent_chat_reasoning_effort == "minimal"
    assert settings.agent_chat_temperature == 0.25
    assert settings.agent_chat_timeout_seconds == 7


class _FakeResponses:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text=(
                '{"schema_version":"autoinvest_command_v1",'
                '"command_type":"SHOW_POSITIONS","domain":"position",'
                '"intent":"show_positions","market":"KR","provider":"kis"}'
            )
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


def test_parser_uses_agent_chat_model_config(db_session):
    client = _FakeClient()
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="legacy-model",
        openai_reasoning_effort="medium",
        agent_chat_model="agent-chat-test-model",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=0,
        agent_chat_timeout_seconds=20,
        agent_chat_fallback_enabled=True,
    )
    service = AgentCommandParserService(openai_client=client, settings=settings)

    response = service.parse(
        db_session,
        message="positions",
        context={"default_market": "KR", "default_provider": "kis"},
    )

    assert response["parser_status"] == "gpt"
    assert response["model_name"] == "agent-chat-test-model"
    assert client.responses.kwargs["model"] == "agent-chat-test-model"
    assert client.responses.kwargs["reasoning"] == {"effort": "low"}
    assert client.responses.kwargs["temperature"] == 0
