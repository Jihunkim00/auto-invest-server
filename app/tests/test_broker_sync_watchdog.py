from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
from app.main import app
from app.routes.broker_sync_watchdog import get_broker_sync_watchdog_service
from app.services.broker_sync_watchdog_service import BrokerSyncWatchdogService


class FakeBroker:
    def __init__(
        self,
        *,
        open_orders: list[dict] | None = None,
        positions: list[dict] | None = None,
        fail: bool = False,
    ) -> None:
        self.open_orders = open_orders or []
        self.positions = positions or []
        self.fail = fail
        self.read_calls = 0
        self.submit_calls = 0

    def list_open_orders(self):
        self.read_calls += 1
        if self.fail:
            raise RuntimeError("broker read failed")
        return list(self.open_orders)

    def list_positions(self):
        self.read_calls += 1
        if self.fail:
            raise RuntimeError("broker read failed")
        return list(self.positions)

    def get_account(self):
        self.read_calls += 1
        if self.fail:
            raise RuntimeError("broker read failed")
        return {"cash": 100000, "currency": "KRW"}

    def submit_market_buy(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("watchdog must not submit")

    def submit_market_sell(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("watchdog must not submit")

    def submit_order(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("watchdog must not submit")


def test_watchdog_status_defaults_safe_and_does_not_submit(db_session):
    broker = FakeBroker()
    service = BrokerSyncWatchdogService(broker_factory=lambda db: broker)

    result = service.run_once(db_session)

    assert result["sync_health"] == "healthy"
    assert result["automation_blocked_by_sync"] is False
    assert result["safety_flags"]["read_only"] is True
    assert result["safety_flags"]["real_order_submitted"] is False
    assert result["safety_flags"]["broker_submit_called"] is False
    assert result["safety_flags"]["manual_submit_called"] is False
    assert result["safety_flags"]["order_cancel_called"] is False
    assert broker.submit_calls == 0
    assert db_session.query(TradeRunLog).filter_by(mode="broker_sync_watchdog").count() == 1


def test_stale_local_order_creates_blocking_issue(db_session):
    db_session.add(
        _order(
            "005930",
            InternalOrderStatus.ACCEPTED.value,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30),
            broker_order_id="A1",
            kis_odno="A1",
        )
    )
    db_session.commit()

    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(open_orders=[_broker_order("A1", "005930")])
    ).status(db_session)

    assert result["sync_health"] == "unsafe"
    assert result["stale_local_order_count"] == 1
    assert result["should_block_auto_buy"] is True
    assert _issue_types(result) >= {"stale_local_order"}


def test_pending_sync_order_blocks_auto_buy_and_orchestrator(db_session):
    db_session.add(_order("005930", InternalOrderStatus.SYNC_FAILED.value))
    db_session.commit()

    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker()
    ).status(db_session)

    assert result["pending_sync_order_count"] == 1
    assert result["should_block_auto_buy"] is True
    assert result["should_block_orchestrator"] is True
    assert "pending_sync_order" in result["blocking_reasons"]


def test_missing_kis_odno_creates_issue(db_session):
    db_session.add(
        _order(
            "005930",
            InternalOrderStatus.SUBMITTED.value,
            broker_order_id="B1",
            kis_odno=None,
        )
    )
    db_session.commit()

    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(open_orders=[_broker_order("B1", "005930")])
    ).status(db_session)

    assert result["missing_kis_odno_count"] == 1
    assert "missing_kis_odno" in _issue_types(result)


def test_broker_open_order_missing_local_record_creates_issue(db_session):
    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(open_orders=[_broker_order("BR1", "000660")])
    ).status(db_session)

    assert result["broker_unmatched_order_count"] == 1
    assert result["should_block_orchestrator"] is True
    assert "broker_order_missing_local_record" in _issue_types(result)


def test_local_open_order_missing_broker_record_creates_issue(db_session):
    db_session.add(
        _order(
            "005930",
            InternalOrderStatus.ACCEPTED.value,
            broker_order_id="L1",
            kis_odno="L1",
        )
    )
    db_session.commit()

    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(open_orders=[])
    ).status(db_session)

    assert result["local_unmatched_order_count"] >= 1
    assert "local_order_missing_broker_record" in _issue_types(result)


def test_position_quantity_mismatch_creates_issue(db_session):
    db_session.add(
        _order(
            "005930",
            InternalOrderStatus.FILLED.value,
            qty=5,
            filled_qty=5,
            broker_order_id="F1",
            kis_odno="F1",
        )
    )
    db_session.commit()

    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(positions=[{"symbol": "005930", "qty": 3}])
    ).status(db_session)

    assert result["position_mismatch_count"] == 1
    assert "position_quantity_mismatch" in _issue_types(result)


def test_broker_read_failure_returns_unknown_and_blocks(db_session):
    result = BrokerSyncWatchdogService(
        broker_factory=lambda db: FakeBroker(fail=True)
    ).status(db_session)

    assert result["sync_health"] == "unknown"
    assert result["automation_blocked_by_sync"] is True
    assert result["should_block_orchestrator"] is True
    assert "broker_read_failed" in _issue_types(result)


def test_watchdog_routes_are_read_only(db_session):
    broker = FakeBroker()
    service = BrokerSyncWatchdogService(broker_factory=lambda db: broker)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_broker_sync_watchdog_service] = lambda: service
    try:
        client = TestClient(app)
        status = client.get("/broker-sync/watchdog/status")
        run_once = client.post("/broker-sync/watchdog/run-once")
        latest = client.get("/broker-sync/watchdog/latest")
    finally:
        app.dependency_overrides.clear()

    assert status.status_code == 200
    assert run_once.status_code == 200
    assert latest.status_code == 200
    assert run_once.json()["safety_flags"]["broker_submit_called"] is False
    assert broker.submit_calls == 0


def _order(
    symbol: str,
    status: str,
    *,
    qty: float | None = 1,
    filled_qty: float | None = None,
    side: str = "buy",
    broker_order_id: str | None = None,
    kis_odno: str | None = None,
    created_at: datetime | None = None,
) -> OrderLog:
    return OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        requested_qty=qty,
        filled_qty=filled_qty,
        internal_status=status,
        broker_order_id=broker_order_id,
        kis_odno=kis_odno,
        created_at=created_at or datetime.now(UTC).replace(tzinfo=None),
    )


def _broker_order(order_id: str, symbol: str) -> dict:
    return {
        "order_id": order_id,
        "symbol": symbol,
        "side": "buy",
        "qty": 1,
        "unfilled_qty": 1,
        "status": "pending",
    }


def _issue_types(result: dict) -> set[str]:
    return {str(item.get("issue_type")) for item in result.get("issues", [])}
