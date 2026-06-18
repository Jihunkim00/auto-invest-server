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
    assert settings.agent_chat_temperature is None
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
        self.calls = []

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.calls.append(kwargs)
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


def test_default_agent_chat_temperature_is_omitted_from_openai_payload(db_session):
    client = _FakeClient()
    settings = _settings(openai_api_key="test-key")
    service = AgentCommandParserService(openai_client=client, settings=settings)

    response = service.parse(
        db_session,
        message="positions",
        context={"default_market": "KR", "default_provider": "kis"},
    )

    assert response["parser_status"] == "gpt"
    assert client.responses.kwargs["model"] == "gpt-5.4-mini"
    assert "temperature" not in client.responses.kwargs


def test_gpt_5_agent_chat_model_does_not_send_temperature(db_session):
    client = _FakeClient()
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="legacy-model",
        openai_reasoning_effort="medium",
        agent_chat_model="gpt-5.4-mini",
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
    assert response["model_name"] == "gpt-5.4-mini"
    assert client.responses.kwargs["model"] == "gpt-5.4-mini"
    assert "temperature" not in client.responses.kwargs


class _TemperatureRetryResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise Exception("Unsupported parameter: 'temperature' is not supported with this model.")
        return SimpleNamespace(
            output_text=(
                '{"schema_version":"autoinvest_command_v1",'
                '"command_type":"SHOW_POSITIONS","domain":"position",'
                '"intent":"show_positions","market":"KR","provider":"kis"}'
            )
        )


class _TemperatureRetryClient:
    def __init__(self):
        self.responses = _TemperatureRetryResponses()


def test_unsupported_temperature_error_retries_without_temperature(db_session):
    client = _TemperatureRetryClient()
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="legacy-model",
        openai_reasoning_effort="medium",
        agent_chat_model="temperature-test-model",
        agent_chat_reasoning_effort="low",
        agent_chat_temperature=0.2,
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
    assert response["error_message"] is None
    assert response["model_name"] == "temperature-test-model"
    assert len(client.responses.calls) == 2
    assert client.responses.calls[0]["temperature"] == 0.2
    assert "temperature" not in client.responses.calls[1]
