from datetime import datetime, timezone
from types import SimpleNamespace

from app.db.models import OrderLog
from app.services.risk_service import RiskService


def _runtime(**overrides):
    values = {
        "global_daily_entry_limit": 1,
        "per_symbol_daily_entry_limit": 1,
    }
    values.update(overrides)
    return values


class _FakeBroker:
    def get_position(self, symbol):
        return None

    def get_account(self):
        return SimpleNamespace(equity=100000.0)


def _add_order(db_session, *, broker: str, symbol: str, status: str = "SUBMITTED"):
    row = OrderLog(
        broker=broker,
        symbol=symbol,
        side="buy",
        order_type="market",
        qty=1,
        internal_status=status,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _service(monkeypatch, runtime=None):
    svc = RiskService()
    svc.broker = _FakeBroker()
    monkeypatch.setattr(svc, "_is_near_market_close", lambda now_utc: False)
    monkeypatch.setattr(
        svc.runtime_settings,
        "get_settings",
        lambda db: runtime or _runtime(),
    )
    return svc


def test_alpaca_daily_entry_limit_ignores_kis_orders(monkeypatch, db_session):
    _add_order(db_session, broker="kis", symbol="005930")
    svc = _service(monkeypatch)

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
    )

    assert result["daily_trade_count"] == 0
    assert "global_daily_entry_limit_reached" not in result["risk_flags"]
    assert result["approved"] is True
    assert result["broker"] == "alpaca"
    assert result["market"] == "US"


def test_alpaca_per_symbol_entry_limit_ignores_same_symbol_kis_orders(
    monkeypatch,
    db_session,
):
    _add_order(db_session, broker="kis", symbol="AAPL")
    svc = _service(monkeypatch, _runtime(global_daily_entry_limit=10))

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
    )

    assert "per_symbol_daily_entry_limit_reached" not in result["risk_flags"]
    assert result["approved"] is True


def test_alpaca_per_symbol_entry_limit_counts_alpaca_orders(
    monkeypatch,
    db_session,
):
    _add_order(db_session, broker="alpaca", symbol="AAPL")
    svc = _service(monkeypatch, _runtime(global_daily_entry_limit=10))

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
    )

    assert "per_symbol_daily_entry_limit_reached" in result["risk_flags"]
    assert result["approved"] is False
