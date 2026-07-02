from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, StrategyAutoBuyPromotion
from app.main import app
from app.routes.strategy_live import get_profile_aware_guarded_live_auto_buy_service
from app.tests.test_strategy_live_auto_buy_service import (
    FakeBroker,
    FakeOrderSyncService,
    FakeValidationResult,
    FakeValidationService,
    add_dry_run,
    add_promotion_for_dry_run,
    enable_live_settings,
    live_request,
    live_service,
)


def test_result_returns_blocked_conversion_without_order(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session)
    broker = FakeBroker()
    validation = FakeValidationService(
        FakeValidationResult(
            validated_for_submission=False,
            block_reasons=["market_closed"],
            primary_block_reason="market_closed",
        )
    )
    service = live_service(validation=validation, broker=broker)
    blocked = service.run_once(db_session, live_request(client_request_id="blocked-result"))

    result = service.result(db_session, blocked["attempt_id"])

    assert result["result_status"] == "blocked"
    assert result["block_reason"] == "market_closed"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert result["order_id"] is None
    assert result["related_order_log_id"] is None
    assert result["next_safe_action"] == "review_block_reason"
    assert result["safety"]["read_only"] is True
    assert broker.calls == []
    assert db_session.query(OrderLog).count() == 0


def test_result_returns_submitted_order_trace_and_promotion_links(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    broker = FakeBroker()
    service = live_service(broker=broker)
    submitted = service.run_once(
        db_session,
        live_request(
            promotion_id=promotion["id"],
            source_dry_run_id=dry_run.id,
            client_request_id="submitted-result",
        ),
    )

    result = service.result(db_session, submitted["attempt_id"])

    assert result["result_status"] == "submitted"
    assert result["promotion_id"] == promotion["id"]
    assert result["order_id"] == submitted["related_order_id"]
    assert result["related_order_log_id"] == submitted["related_order_id"]
    assert result["broker_order_id"] == "KIS-ORDER-1"
    assert result["kis_odno"] == "KIS-ORDER-1"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is False
    assert result["submitted_quantity"] == 3
    assert result["submitted_notional"] == 30000
    assert result["promotion_conversion_status"] == "live_order_created"
    assert result["audit_trace"]["promotion"]["promotion_id"] == promotion["id"]
    assert result["next_safe_action"] == "refresh_result"
    assert "SECRET" not in json.dumps(result)
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(OrderLog).count() == 1


def test_result_sync_updates_existing_order_without_new_submit(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    broker = FakeBroker()
    sync = FakeOrderSyncService()
    service = live_service(broker=broker, order_sync_service=sync)
    submitted = service.run_once(
        db_session,
        live_request(
            promotion_id=promotion["id"],
            source_dry_run_id=dry_run.id,
            client_request_id="sync-result",
        ),
    )
    order_count = db_session.query(OrderLog).count()

    result = service.sync_result(db_session, submitted["attempt_id"])

    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert result["result_status"] == "filled"
    assert result["order_id"] == submitted["related_order_id"]
    assert result["broker_order_id"] == "KIS-ORDER-1"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["safety"]["read_only"] is True
    assert result["safety"]["sync_only"] is True
    assert row.last_sync_status == "filled"
    assert sync.calls == [submitted["related_order_id"]]
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(OrderLog).count() == order_count


def test_result_routes_expose_read_only_get_and_safe_sync(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session)
    broker = FakeBroker()
    sync = FakeOrderSyncService()
    service = live_service(broker=broker, order_sync_service=sync)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_profile_aware_guarded_live_auto_buy_service] = (
        lambda: service
    )
    try:
        client = TestClient(app)
        submitted = client.post(
            "/strategy/live/auto-buy/run-once",
            json={
                "confirm_operator_ack": True,
                "trigger_source": "route-result",
                "client_request_id": "route-result",
            },
        ).json()
        get_response = client.get(
            f"/strategy/live-auto-buy/results/{submitted['attempt_id']}"
        )
        sync_response = client.post(
            f"/strategy/live-auto-buy/results/{submitted['attempt_id']}/sync",
            json={},
        )
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 200
    assert get_response.json()["result_status"] == "submitted"
    assert get_response.json()["safety"]["read_only"] is True
    assert sync_response.status_code == 200
    assert sync_response.json()["result_status"] == "filled"
    assert sync_response.json()["safety"]["sync_only"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert sync.calls == [submitted["related_order_id"]]
