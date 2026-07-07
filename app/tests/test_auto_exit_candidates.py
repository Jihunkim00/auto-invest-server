from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting
from app.main import app
from app.schemas.agent_chat_orchestrator import AgentChatIntent, AgentChatIntentCategory
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_result_summarizer import AgentChatResultSummarizer
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.auto_exit_candidate_service import AutoExitCandidateService


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_real_order_enabled": True,
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _open_session(*, entry_allowed=True):
    return {
        "market": "KR",
        "timezone": "Asia/Seoul",
        "is_market_open": True,
        "is_entry_allowed_now": entry_allowed,
        "is_near_close": not entry_allowed,
        "effective_close": "15:30",
        "no_new_entry_after": "15:00",
    }


def _position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung",
        "qty": 2,
        "available_quantity": 2,
        "current_price": 4900,
        "avg_entry_price": 5000,
        "cost_basis": 10000,
        "market_value": 9800,
        "unrealized_pl": -200,
        "unrealized_plpc": -99,
    }
    payload.update(overrides)
    return payload


class _FakeClient:
    settings = _settings()

    def list_positions(self):
        return [_position()]

    def list_open_orders(self):
        return []


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def safe_context(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.strategy_positions.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.position_exit_review_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.services.auto_exit_candidate_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _open_session(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [_position()],
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [],
    )
    db_session.add(RuntimeSetting(dry_run=False, kill_switch=False))
    db_session.commit()


def _candidate(body, candidate_type):
    return next(
        item for item in body["candidates"] if item["candidate_type"] == candidate_type
    )


def test_exit_candidates_endpoint_returns_stop_loss_candidate(client):
    response = client.get("/strategy/positions/exit-candidates")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["summary"]["stop_loss_count"] == 1
    assert body["summary"]["candidate_count"] >= 1
    assert body["safety_flags"][:3] == [
        "read_only",
        "no_live_orders",
        "no_broker_submit",
    ]

    item = _candidate(body, "stop_loss")
    assert item["symbol"] == "005930"
    assert item["severity"] == "critical"
    assert item["action_hint"] == "run_sell_preflight"
    assert item["cost_basis"] == pytest.approx(10000)
    assert item["current_value"] == pytest.approx(9800)
    assert item["unrealized_pl_pct"] == pytest.approx(-0.02)
    assert item["stop_loss_triggered"] is True
    assert item["can_run_sell_preflight"] is True
    assert item["sell_preflight_endpoint_hint"] == "/strategy/positions/005930/sell-preflight"


def test_exit_candidates_endpoint_returns_take_profit_candidate(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(current_price=5150, market_value=10300, unrealized_pl=300)
        ],
    )

    body = client.get("/strategy/positions/exit-candidates").json()

    item = _candidate(body, "take_profit")
    assert body["summary"]["take_profit_count"] == 1
    assert item["severity"] == "warning"
    assert item["take_profit_triggered"] is True
    assert item["unrealized_pl_pct"] == pytest.approx(0.03)


def test_missing_cost_basis_creates_manual_review_not_guessed_pl(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_positions",
        lambda self: [
            _position(avg_entry_price=0, cost_basis=0, market_value=9800, unrealized_pl=-200)
        ],
    )

    body = client.get("/strategy/positions/exit-candidates").json()

    assert body["summary"]["stop_loss_count"] == 0
    item = _candidate(body, "manual_review")
    assert item["severity"] == "warning"
    assert item["cost_basis"] is None
    assert "incomplete_pl_inputs" in item["risk_flags"]
    assert item["can_run_sell_preflight"] is False


def test_duplicate_open_sell_order_creates_conflict_candidate(monkeypatch, client):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.list_open_orders",
        lambda self: [{"symbol": "005930", "side": "sell", "status": "SUBMITTED"}],
    )

    body = client.get("/strategy/positions/exit-candidates").json()

    item = _candidate(body, "duplicate_sell_conflict")
    assert body["summary"]["duplicate_sell_block_count"] == 1
    assert item["severity"] == "critical"
    assert item["open_sell_order_conflict"] is True
    assert item["can_run_sell_preflight"] is False
    assert item["sell_preflight_endpoint_hint"] is None


def test_sync_required_order_creates_sync_candidate(client, db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            internal_status="UNKNOWN_STALE",
        )
    )
    db_session.commit()

    body = client.get("/strategy/positions/exit-candidates").json()

    item = _candidate(body, "sync_required")
    assert body["summary"]["sync_required_count"] == 1
    assert item["sync_required"] is True
    assert item["action_hint"] == "sync_required"
    assert item["can_run_sell_preflight"] is False


def test_exit_candidates_endpoint_does_not_mutate_or_create_orders(client, db_session):
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="buy",
            order_type="market",
            internal_status="FILLED",
        )
    )
    db_session.commit()
    before_orders = db_session.query(OrderLog).count()
    before_settings = db_session.query(RuntimeSetting).count()

    response = client.get("/strategy/positions/exit-candidates")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == before_orders
    assert db_session.query(RuntimeSetting).count() == before_settings


def test_exit_candidates_endpoint_does_not_call_sell_submit_paths(monkeypatch, client):
    for method in (
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
    ):
        monkeypatch.setattr(
            "app.brokers.kis_client.KisClient." + method,
            lambda *args, **kwargs: pytest.fail("candidate detection must not submit"),
            raising=False,
        )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("candidate detection must not use manual live flow"),
    )

    response = client.get("/strategy/positions/exit-candidates")

    assert response.status_code == 200
    assert response.json()["summary"]["candidate_count"] >= 1


def test_agent_chat_summarizes_exit_candidates_read_only(db_session):
    registry = AgentChatToolRegistry()
    assert registry.can_auto_execute("strategy_exit_candidate_lookup") is True
    executor = AgentChatToolExecutor(
        registry=registry,
        kis_client_factory=lambda db: _FakeClient(),
    )
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.STRATEGY_EXIT_CANDIDATE_QUERY,
        provider="kis",
        market="KR",
        symbol="005930",
    )
    result = executor.execute(
        db_session,
        call=AgentChatToolCall(
            tool_name="strategy_exit_candidate_lookup",
            arguments={"symbol": "005930"},
        ),
        intent=intent,
    )

    assert result.status == "success"
    assert result.result_type == "strategy_exit_candidate"
    assert result.safety.read_only is True
    assert result.data["summary"]["candidate_count"] >= 1
    answer = AgentChatResultSummarizer().answer_for_results(
        intent=intent,
        tool_results=[result],
        fallback_answer=None,
    )
    assert "Auto exit candidates" in answer.text
    assert "did not run sell preflight or execute a sell order" in answer.text


def test_auto_exit_candidate_service_has_no_direct_sell_path_references():
    source = inspect.getsource(AutoExitCandidateService)
    for forbidden in [
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "KisManualOrderService",
        "guarded_sell",
        "confirm_live",
    ]:
        assert forbidden not in source
