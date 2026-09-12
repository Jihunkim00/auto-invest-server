from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.brokers import user_alpaca_client as alpaca_client_module
from app.brokers.user_alpaca_client import (
    UserAlpacaLiveTradingClient,
    UserAlpacaTradingClient,
)
from app.config import get_settings
from app.db.database import get_db
from app.db.models import (
    OrderLog,
    PositionLifecycle,
    SignalLog,
    TradeRunLog,
    User,
    UserTradingSettings,
)
from app.main import app
from app.routes.user_trading import get_user_trading_execution_service
from app.services.auth_service import create_session
from app.services.market_session_service import MarketSessionService
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_risk_state_service import UserRiskStateService
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService
from app.services.user_trading_execution_service import UserTradingExecutionService


def _user(db_session, username: str) -> User:
    row = User(username=username, role="user", enabled=True, setup_completed=True)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class FakeLiveAccountService(UserBrokerAccountService):
    def __init__(self):
        pass

    def get_broker_snapshot(self, db, user, provider):
        currency = "KRW" if provider == "kis" else "USD"
        return {
            "provider": provider,
            "environment": "live",
            "connected": True,
            "account": {
                "currency": currency,
                "portfolio_value": 10000.0,
                "equity": 10000.0,
                "buying_power": 10000.0,
                "cash": 10000.0,
            },
            "positions": [],
            "open_orders": [],
        }


class FakeCredentialService(UserBrokerCredentialService):
    def __init__(self, environment="live"):
        self.environment = environment

    def get_credentials(self, db, user, provider):
        if provider == "kis":
            return {
                "environment": self.environment,
                "app_key": f"user-{user.id}-app-key",
                "app_secret": f"user-{user.id}-app-secret",
                "hts_id": f"user-{user.id}-hts",
                "account_no": f"{user.id:08d}",
                "account_product_code": "01",
            }
        return {
            "environment": self.environment,
            "api_key": f"user-{user.id}-api-key",
            "secret_key": f"user-{user.id}-secret-key",
        }


class FakeAnalysisService(UserSymbolAnalysisService):
    def __init__(self):
        pass

    def analyze(self, db, *, provider, symbol, gate_level=2, now=None):
        return {
            "provider": provider,
            "market": "KR" if provider == "kis" else "US",
            "symbol": symbol,
            "requested_symbol": symbol,
            "analyzed_symbol": symbol,
            "returned_symbol": symbol,
            "action": "buy",
            "reason": "fake_analysis",
            "current_price": 100.0,
            "final_buy_score": 80.0,
            "final_sell_score": 10.0,
            "confidence": 0.8,
            "indicator_payload": {"price": 100.0},
            "risk_flags": [],
            "gating_notes": [],
            "hard_blocked": False,
        }


class FakeSessionService(MarketSessionService):
    def get_session_status(self, market, now=None):
        return {
            "market": market,
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "local_time": "2026-09-11T10:00:00+09:00",
        }


class FakeLiveOrderClient:
    def __init__(self, calls, *, provider):
        self.calls = calls
        self.provider = provider

    def submit_market_buy_qty(self, *, symbol, qty):
        self.calls.append({"provider": self.provider, "symbol": symbol, "qty": qty})
        return SimpleNamespace(
            id=f"{self.provider}-live-order-1",
            status="submitted",
            client_order_id=f"{self.provider}-client-1",
            filled_qty=0,
            filled_avg_price=None,
        )


class FakePartialKisOrderClient:
    def __init__(self, calls):
        self.calls = calls

    def submit_market_buy_qty(self, *, symbol, qty):
        self.calls.append({"symbol": symbol, "qty": qty})
        return {
            "id": "KIS-LIVE-PARTIAL-1",
            "kis_odno": "KIS-LIVE-PARTIAL-1",
            "status": "partially_filled",
            "filled_qty": 2,
            "filled_avg_price": 100.0,
        }


class FakeFailingKisOrderClient:
    def __init__(self, calls):
        self.calls = calls

    def submit_market_buy_qty(self, *, symbol, qty):
        self.calls.append({"symbol": symbol, "qty": qty})
        raise RuntimeError("user-secret-must-not-leak")


def _client(db_session, user, service):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_user_trading_execution_service] = lambda: service
    client = TestClient(app)
    client.cookies.set(get_settings().session_cookie_name, create_session(db_session, user))
    return client


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _live_settings(db_session, user, *, provider="kis"):
    db_session.add(
        UserTradingSettings(
            user_id=user.id,
            enabled=True,
            paper_trading_enabled=False,
            live_trading_enabled=True,
            kill_switch=False,
            trading_mode="live",
            max_daily_trades=2,
            max_open_positions=1,
        )
    )
    db_session.commit()


def _service(*, credentials="live", kis_factory=None, alpaca_factory=None):
    return UserTradingExecutionService(
        account_service=FakeLiveAccountService(),
        credential_service=FakeCredentialService(credentials),
        analysis_service=FakeAnalysisService(),
        session_service=FakeSessionService(),
        kis_live_client_factory=kis_factory,
        alpaca_live_client_factory=alpaca_factory,
    )


def test_live_mode_permission_confirmation_and_user_kill_switch_are_independent(db_session):
    user = _user(db_session, "pr128-gates")
    db_session.add(
        UserTradingSettings(
            user_id=user.id,
            enabled=True,
            paper_trading_enabled=False,
            live_trading_enabled=False,
            kill_switch=True,
            trading_mode="live",
        )
    )
    db_session.commit()
    calls = []
    service = _service(kis_factory=lambda db, user, credentials: FakeLiveOrderClient(calls, provider="kis"))
    client = _client(db_session, user, service)

    disabled = client.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "005930", "confirm_live": True},
    )
    assert disabled.json()["reason"] == "live_trading_disabled"
    assert calls == []

    enabled = client.patch(
        "/users/me/trading/settings",
        json={"live_trading_enabled": True},
    )
    assert enabled.status_code == 200
    blocked_by_kill = client.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "005930", "confirm_live": True},
    )
    assert blocked_by_kill.json()["reason"] == "user_kill_switch_enabled"
    assert calls == []

    client.patch("/users/me/trading/settings", json={"kill_switch": False})
    missing_confirmation = client.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "005930"},
    )
    assert missing_confirmation.json()["reason"] == "live_confirmation_required"
    assert calls == []


def test_qualified_kis_live_order_is_submitted_once_and_owned_with_partial_lifecycle(db_session):
    user = _user(db_session, "pr128-kis-live")
    _live_settings(db_session, user)
    calls = []
    service = _service(
        kis_factory=lambda db, user, credentials: FakePartialKisOrderClient(calls),
    )
    client = _client(db_session, user, service)

    response = client.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "5930", "confirm_live": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "submitted"
    assert body["real_order_submitted"] is True
    assert body["broker_submit_called"] is True
    assert calls == [{"symbol": "005930", "qty": 10}]

    order = db_session.query(OrderLog).one()
    assert order.owner_user_id == user.id
    assert order.broker_order_id == "KIS-LIVE-PARTIAL-1"
    assert order.kis_odno == "KIS-LIVE-PARTIAL-1"
    assert order.internal_status == "PARTIALLY_FILLED"
    assert order.filled_qty == 2
    lifecycle = db_session.query(PositionLifecycle).one()
    assert lifecycle.owner_user_id == user.id
    assert lifecycle.quantity == 2
    assert db_session.query(TradeRunLog).one().owner_user_id == user.id
    assert db_session.query(SignalLog).one().owner_user_id == user.id
    assert "user-" not in response.text


def test_failed_kis_live_submit_is_persisted_without_secret_leak(db_session):
    user = _user(db_session, "pr128-kis-failed")
    _live_settings(db_session, user)
    calls = []
    service = _service(
        kis_factory=lambda db, user, credentials: FakeFailingKisOrderClient(calls),
    )
    client = _client(db_session, user, service)

    response = client.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "005930", "confirm_live": True},
    )
    assert response.json()["result"] == "failed"
    assert response.json()["reason"] == "kis_live_submit_failed"
    assert calls == [{"symbol": "005930", "qty": 10}]
    assert "user-secret-must-not-leak" not in response.text
    order = db_session.query(OrderLog).one()
    assert order.internal_status == "FAILED"
    assert order.broker_order_id is None
    assert order.error_message == "user_broker_submit_failed"


def test_alpaca_live_uses_only_live_factory_and_user_credentials(db_session):
    user = _user(db_session, "pr128-alpaca-live")
    _live_settings(db_session, user, provider="alpaca")
    calls = []
    received = []

    def factory(credentials):
        received.append(dict(credentials))
        return FakeLiveOrderClient(calls, provider="alpaca")

    client = _client(db_session, user, _service(alpaca_factory=factory))
    response = client.post(
        "/users/me/trading/run-once",
        json={"provider": "alpaca", "symbol": "AAPL", "confirm_live": True},
    )
    assert response.json()["result"] == "submitted"
    assert calls == [{"provider": "alpaca", "symbol": "AAPL", "qty": 10}]
    assert received[0]["api_key"] == f"user-{user.id}-api-key"
    assert received[0]["environment"] == "live"
    assert "secret-key" not in response.text
    assert db_session.query(OrderLog).one().owner_user_id == user.id


def test_alpaca_environment_cannot_cross_modes(db_session):
    user = _user(db_session, "pr128-alpaca-env")
    db_session.add(
        UserTradingSettings(
            user_id=user.id,
            enabled=True,
            paper_trading_enabled=True,
            live_trading_enabled=False,
            kill_switch=True,
            trading_mode="paper",
        )
    )
    db_session.commit()
    factory_calls = []
    service = _service(
        credentials="live",
        alpaca_factory=lambda credentials: factory_calls.append(credentials),
    )
    client = _client(db_session, user, service)
    paper_with_live_credentials = client.post(
        "/users/me/trading/run-once",
        json={"provider": "alpaca", "symbol": "AAPL"},
    )
    assert paper_with_live_credentials.json()["reason"] == "paper_credentials_required"
    assert factory_calls == []

    db_session.query(UserTradingSettings).filter_by(user_id=user.id).update(
        {
            "trading_mode": "live",
            "paper_trading_enabled": False,
            "live_trading_enabled": True,
            "kill_switch": False,
        }
    )
    db_session.commit()
    paper_credentials_service = _service(
        credentials="paper",
        alpaca_factory=lambda credentials: factory_calls.append(credentials),
    )
    client = _client(db_session, user, paper_credentials_service)
    live_with_paper_credentials = client.post(
        "/users/me/trading/run-once",
        json={"provider": "alpaca", "symbol": "AAPL", "confirm_live": True},
    )
    assert live_with_paper_credentials.json()["reason"] == "live_credentials_required"
    assert factory_calls == []


def test_alpaca_clients_have_explicit_paper_flags(monkeypatch):
    flags = []

    class FakeTradingClient:
        def __init__(self, **kwargs):
            flags.append(kwargs["paper"])

    monkeypatch.setattr(alpaca_client_module, "TradingClient", FakeTradingClient)
    UserAlpacaLiveTradingClient(
        {"environment": "live", "api_key": "live-key", "secret_key": "live-secret"}
    )
    UserAlpacaTradingClient(
        {"environment": "paper", "api_key": "paper-key", "secret_key": "paper-secret"}
    )
    assert flags == [False, True]


def test_user_live_history_stays_isolated(db_session):
    user_a = _user(db_session, "pr128-history-a")
    user_b = _user(db_session, "pr128-history-b")
    _live_settings(db_session, user_a)
    _live_settings(db_session, user_b)
    calls = []
    service = _service(
        kis_factory=lambda db, user, credentials: FakeLiveOrderClient(calls, provider=f"kis-{user.id}"),
    )
    client_a = _client(db_session, user_a, service)
    client_b = _client(db_session, user_b, service)

    assert client_a.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "005930", "confirm_live": True},
    ).json()["result"] == "submitted"
    assert client_b.post(
        "/users/me/trading/run-once",
        json={"provider": "kis", "symbol": "000660", "confirm_live": True},
    ).json()["result"] == "submitted"

    assert [item["owner_user_id"] for item in client_a.get("/users/me/trading/orders").json()["items"]] == [user_a.id]
    assert [item["owner_user_id"] for item in client_b.get("/users/me/trading/orders").json()["items"]] == [user_b.id]
    assert calls[0]["provider"] == f"kis-{user_a.id}"
    assert calls[1]["provider"] == f"kis-{user_b.id}"