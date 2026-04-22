from types import SimpleNamespace

from app.db.models import OrderLog, SignalLog, TradeRunLog
from app.routes.ops import manual_close_position
from app.services.trading_service import TradingService


class FakeOrder:
    id = "broker-order-1"
    client_order_id = "client-1"
    status = "filled"
    filled_qty = 2
    filled_avg_price = 100.0
    submitted_at = None
    filled_at = None
    canceled_at = None

    def dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "filled_avg_price": self.filled_avg_price,
        }


class FakeBroker:
    def get_position(self, symbol):
        return SimpleNamespace(symbol=symbol, qty="2", unrealized_plpc=-0.02)

    def get_latest_price(self, symbol):
        return {"symbol": symbol, "price": 100.0}

    def submit_market_sell(self, symbol, qty):
        return FakeOrder()


class ExplodingBroker(FakeBroker):
    def submit_market_sell(self, symbol, qty):
        raise RuntimeError("broker submit failed")


def test_manual_close_endpoint_closes_and_logs(monkeypatch, db_session):
    monkeypatch.setattr("app.services.trading_service.AlpacaClient", lambda: FakeBroker())

    response = manual_close_position("AAPL", db=db_session)

    assert response["result"] == "executed"
    assert response["executed"] is True
    assert response["order"]["side"] == "sell"

    order = db_session.query(OrderLog).filter(OrderLog.symbol == "AAPL", OrderLog.side == "sell").one()
    run = db_session.query(TradeRunLog).filter(TradeRunLog.id == response["run_id"]).one()
    assert order.qty == 2
    assert run.result == "executed"
    assert run.run_key.startswith("manual_close_AAPL_")


def test_position_management_hold_can_be_escalated_to_sell(monkeypatch, db_session):
    monkeypatch.setattr("app.services.trading_service.AlpacaClient", lambda: FakeBroker())
    service = TradingService()

    signal = SignalLog(
        symbol="AAPL",
        action="hold",
        gate_level=2,
        gate_profile_name="conservative",
        gating_notes="[]",
        risk_flags="[]",
        final_sell_score=75,
        final_buy_score=20,
        signal_status="created",
    )
    db_session.add(signal)
    db_session.commit()
    db_session.refresh(signal)
    monkeypatch.setattr(service.signal_service, "run", lambda *a, **k: signal)

    result = service.run_once(
        db_session,
        symbol="AAPL",
        mode="position_management",
        allowed_actions=["hold", "sell"],
    )

    assert result["result"] == "executed"
    assert result["action"] == "sell"
    assert result["order"]["side"] == "sell"


def test_manual_close_blocked_on_conflicting_open_order(monkeypatch, db_session):
    monkeypatch.setattr("app.services.trading_service.AlpacaClient", lambda: FakeBroker())
    service = TradingService()
    monkeypatch.setattr(
        service.execution_guard_service,
        "action_check",
        lambda db, symbol, action, intent="entry": {
            "allowed": False,
            "reason": "conflicting_open_order_exists",
        },
    )

    result = service.manual_close_position(db_session, symbol="AAPL", trigger_source="manual_close")

    run = db_session.query(TradeRunLog).filter(TradeRunLog.id == result["run_id"]).one()
    assert result["result"] == "skipped"
    assert result["reason"] == "conflicting_open_order_exists"
    assert run.result == "skipped"
    assert run.reason == "conflicting_open_order_exists"


def test_manual_close_broker_failure_sets_error_result(monkeypatch, db_session):
    monkeypatch.setattr("app.services.trading_service.AlpacaClient", lambda: ExplodingBroker())
    service = TradingService()
    monkeypatch.setattr(
        service.execution_guard_service,
        "action_check",
        lambda db, symbol, action, intent="entry": {"allowed": True, "reason": "exit_action_guard_passed"},
    )

    result = service.manual_close_position(db_session, symbol="AAPL", trigger_source="manual_close")

    run = db_session.query(TradeRunLog).filter(TradeRunLog.id == result["run_id"]).one()
    assert result["result"] == "error"
    assert "broker submit failed" in result["reason"]
    assert run.result == "error"
    assert run.stage == "done"
    assert "broker submit failed" in run.reason
