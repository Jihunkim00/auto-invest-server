from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import (
    OrderLog,
    SignalLog,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
    StrategyLiveAutoExitAttempt,
)
from app.main import app
from app.routes.strategy_positions import get_position_lifecycle_audit_service
from app.services.position_lifecycle_audit_service import PositionLifecycleAuditService


BASE_TIME = datetime(2026, 7, 3, 0, 0, 0)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _order(
    db_session,
    *,
    symbol: str = "005930",
    side: str,
    qty: float,
    price: float | None,
    minutes: int,
    status: str = "FILLED",
    broker_order_id: str | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
) -> OrderLog:
    submitted_at = BASE_TIME + timedelta(minutes=minutes)
    filled_at = submitted_at + timedelta(minutes=1)
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        time_in_force="day",
        qty=qty,
        requested_qty=qty,
        filled_qty=qty,
        remaining_qty=0,
        avg_fill_price=price,
        filled_avg_price=price,
        notional=(qty * price) if price is not None else None,
        internal_status=status,
        broker_status="filled" if status == "FILLED" else "submitted",
        broker_order_status="filled" if status == "FILLED" else "submitted",
        broker_order_id=broker_order_id or f"KIS-{side}-{minutes}",
        kis_odno=broker_order_id or f"KIS-{side}-{minutes}",
        submitted_at=submitted_at,
        filled_at=filled_at if status == "FILLED" else None,
        created_at=submitted_at,
        updated_at=filled_at,
        request_payload=json.dumps(request_payload or {}, ensure_ascii=False),
        response_payload=json.dumps(response_payload or {}, ensure_ascii=False),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _buy_payload(**extra):
    return {
        "source": "strategy_live_auto_buy",
        "trigger_source": "profile_aware_guarded_live_auto_buy",
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": False,
        **extra,
    }


def _sell_payload(**extra):
    return {
        "source": "guarded_position_sell",
        "trigger_source": "manual_guarded_position_sell",
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        **extra,
    }


def test_lifecycle_endpoint_returns_open_position_with_cached_unrealized_pl(
    client,
    db_session,
):
    buy = _order(
        db_session,
        side="buy",
        qty=2,
        price=5000,
        minutes=0,
        response_payload=_buy_payload(),
    )
    db_session.add(
        StrategyLiveAutoBuyAttempt(
            provider="kis",
            market="KR",
            symbol="005930",
            symbol_name="Samsung",
            status="filled",
            trigger_source="profile_aware_guarded_live_auto_buy",
            related_order_id=buy.id,
            response_payload=json.dumps({"symbol": "005930"}),
            created_at=BASE_TIME,
        )
    )
    db_session.commit()

    def loader(db, provider, market):
        return [
            {
                "symbol": "005930",
                "name": "Samsung",
                "qty": 2,
                "current_price": 4900,
                "current_value": 9800,
                "cost_basis": 10000,
                "unrealized_pl": -200,
            }
        ]

    app.dependency_overrides[get_position_lifecycle_audit_service] = (
        lambda: PositionLifecycleAuditService(position_loader=loader)
    )

    response = client.get("/strategy/positions/lifecycle?status=open")

    assert response.status_code == 200
    body = response.json()
    assert body["safety"]["read_only"] is True
    assert body["safety"]["submit_service_called"] is False
    assert body["totals"]["open_position_count"] == 1
    assert body["totals"]["total_current_value"] == 9800
    assert body["totals"]["total_unrealized_pl"] == -200
    item = body["items"][0]
    assert item["lifecycle_status"] == "open"
    assert item["entry_source"] == "manual_live_buy"
    assert item["current_quantity"] == 2
    assert item["unrealized_pl"] == -200
    assert "calculation_incomplete" not in item["audit_flags"]
    assert [event["event_type"] for event in item["events"]] == [
        "buy_preflight",
        "guarded_buy_submitted",
        "buy_filled",
        "position_opened",
    ]


def test_lifecycle_endpoint_returns_closed_trade_and_realized_pl(
    client,
    db_session,
):
    buy = _order(
        db_session,
        side="buy",
        qty=2,
        price=5000,
        minutes=0,
        response_payload=_buy_payload(promotion_id=10),
    )
    sell = _order(
        db_session,
        side="sell",
        qty=2,
        price=5400,
        minutes=60,
        response_payload=_sell_payload(),
    )
    promotion = StrategyAutoBuyPromotion(
        id=10,
        provider="kis",
        market="KR",
        symbol="005930",
        symbol_name="Samsung",
        status="converted_to_live_attempt",
        promotion_reason="scheduler_dry_run_would_buy",
        converted_order_id=buy.id,
        related_live_order_id=buy.id,
        created_at=BASE_TIME - timedelta(minutes=10),
        acknowledged_at=BASE_TIME - timedelta(minutes=5),
        converted_at=BASE_TIME,
    )
    db_session.add(promotion)
    db_session.add(
        SignalLog(
            symbol="005930",
            action="buy",
            related_order_id=buy.id,
            trigger_source="profile_aware_guarded_live_auto_buy",
            created_at=BASE_TIME,
        )
    )
    db_session.add(
        StrategyLiveAutoBuyAttempt(
            provider="kis",
            market="KR",
            symbol="005930",
            status="filled",
            trigger_source="profile_aware_guarded_live_auto_buy",
            related_order_id=buy.id,
            response_payload=json.dumps({"promotion_id": 10}),
            created_at=BASE_TIME,
        )
    )
    db_session.add(
        StrategyLiveAutoExitAttempt(
            provider="kis",
            market="KR",
            symbol="005930",
            status="filled",
            trigger_source="manual_guarded_position_sell",
            quantity=2,
            related_order_id=sell.id,
            response_payload=json.dumps({"order_id": sell.id}),
            created_at=BASE_TIME + timedelta(minutes=55),
        )
    )
    db_session.commit()

    response = client.get("/strategy/positions/lifecycle?status=closed")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["closed_lifecycle_count"] == 1
    assert body["totals"]["total_realized_pl"] == 800
    assert body["totals"]["total_realized_pl_pct"] == 0.08
    item = body["items"][0]
    assert item["entry_source"] == "promotion_conversion"
    assert item["related_promotion_id"] == 10
    assert item["related_signal_id"] is not None
    assert item["entry_notional"] == 10000
    assert item["exit_notional"] == 10800
    assert item["realized_pl"] == 800
    assert item["realized_pl_pct"] == 0.08
    assert item["holding_period_minutes"] == 60
    assert "calculation_incomplete" not in item["audit_flags"]
    event_types = [event["event_type"] for event in item["events"]]
    assert "promotion_created" in event_types
    assert "promotion_reviewed" in event_types
    assert "guarded_buy_submitted" in event_types
    assert "guarded_sell_submitted" in event_types
    assert "sell_filled" in event_types
    assert "position_closed" in event_types


def test_lifecycle_realized_pl_is_incomplete_when_fill_data_missing(
    client,
    db_session,
):
    _order(
        db_session,
        side="buy",
        qty=1,
        price=None,
        minutes=0,
        response_payload=_buy_payload(),
    )
    _order(
        db_session,
        side="sell",
        qty=1,
        price=5200,
        minutes=30,
        response_payload=_sell_payload(),
    )
    db_session.commit()

    response = client.get("/strategy/positions/lifecycle?status=closed")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["realized_pl"] is None
    assert item["realized_pl_pct"] is None
    assert "average_entry_price_missing" in item["audit_flags"]
    assert "calculation_incomplete" in item["audit_flags"]
    assert response.json()["totals"]["incomplete_calculation_count"] == 1


def test_lifecycle_partial_exit_calculates_sold_quantity_only(
    client,
    db_session,
):
    _order(
        db_session,
        side="buy",
        qty=3,
        price=1000,
        minutes=0,
        response_payload=_buy_payload(),
    )
    _order(
        db_session,
        side="sell",
        qty=1,
        price=1300,
        minutes=20,
        response_payload=_sell_payload(),
    )
    db_session.commit()

    response = client.get("/strategy/positions/lifecycle")

    assert response.status_code == 200
    body = response.json()
    closed = next(item for item in body["items"] if item["lifecycle_status"] == "closed")
    open_item = next(item for item in body["items"] if item["lifecycle_status"] == "open")
    assert closed["exit_quantity"] == 1
    assert closed["cost_basis"] == 1000
    assert closed["realized_pl"] == 300
    assert open_item["current_quantity"] == 2
    assert open_item["entry_notional"] == 2000
    assert body["totals"]["closed_lifecycle_count"] == 1
    assert body["totals"]["open_position_count"] == 1


def test_lifecycle_endpoint_is_read_only_and_does_not_submit(
    monkeypatch,
    client,
    db_session,
):
    buy = _order(
        db_session,
        side="buy",
        qty=1,
        price=5000,
        minutes=0,
        status="FILLED",
        response_payload=_buy_payload(),
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("lifecycle read must not submit manual orders"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("lifecycle read must not call broker submit"),
    )

    before = {
        "internal_status": buy.internal_status,
        "broker_status": buy.broker_status,
        "last_synced_at": buy.last_synced_at,
    }
    response = client.get("/strategy/positions/lifecycle")
    db_session.refresh(buy)

    assert response.status_code == 200
    assert response.json()["safety"]["order_state_mutated"] is False
    assert buy.internal_status == before["internal_status"]
    assert buy.broker_status == before["broker_status"]
    assert buy.last_synced_at == before["last_synced_at"]
