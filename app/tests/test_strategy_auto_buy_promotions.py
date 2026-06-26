from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import (
    KisOrderValidationLog,
    OrderLog,
    StrategyAutoBuyPromotion,
)
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)


def test_promotions_list_returns_pending_promotion(db_session):
    service = StrategyAutoBuyPromotionService()
    created = service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        request_payload={"source": "pytest"},
        now=_now(),
    )

    body = service.list(db_session, status="pending")

    assert created["status"] == "pending"
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "005930"
    assert body["items"][0]["source_dry_run_trade_run_id"] == 22
    assert body["safety"]["read_only"] is True


def test_acknowledge_updates_local_state_only(db_session):
    service = StrategyAutoBuyPromotionService()
    promotion = service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        now=_now(),
    )

    body = service.acknowledge(db_session, promotion["id"])

    assert body["status"] == "acknowledged"
    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert row.status == "acknowledged"
    assert row.acknowledged_at is not None
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert body["safety"]["broker_submit_called"] is False


def test_dismiss_updates_local_state_only(db_session):
    service = StrategyAutoBuyPromotionService()
    promotion = service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        now=_now(),
    )

    body = service.dismiss(db_session, promotion["id"])

    assert body["status"] == "dismissed"
    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert row.status == "dismissed"
    assert row.dismissed_at is not None
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


def test_mark_converted_links_existing_attempt_without_submit(db_session):
    service = StrategyAutoBuyPromotionService()
    promotion = service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        now=_now(),
    )

    body = service.mark_converted(
        db_session,
        promotion["id"],
        promoted_to_live_attempt_id=7,
        related_live_order_id=9,
    )

    assert body["status"] == "converted_to_live_attempt"
    assert body["promotion"]["promoted_to_live_attempt_id"] == 7
    assert body["promotion"]["related_live_order_id"] == 9
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


def test_create_requires_would_buy(db_session):
    service = StrategyAutoBuyPromotionService()

    try:
        service.create_from_dry_run(
            db_session,
            dry_run_result={**_dry_run(), "action": "blocked"},
            now=_now(),
        )
    except ValueError as exc:
        assert str(exc) == "promotion_requires_would_buy"
    else:
        raise AssertionError("blocked dry-run must not create promotion")

    assert db_session.query(StrategyAutoBuyPromotion).count() == 0


def _dry_run() -> dict:
    return {
        "status": "ok",
        "action": "would_buy",
        "provider": "kis",
        "market": "KR",
        "active_profile": "safe",
        "selected_symbol": "005930",
        "selected_symbol_name": "Samsung Electronics",
        "buy_score": 80,
        "sell_score": 15,
        "final_score": 82,
        "confidence": 0.8,
        "recommended_notional_krw": 30000,
        "simulated_quantity": 3,
        "simulated_price": 10000,
        "simulated_notional_krw": 30000,
        "target_risk_result": {"approved": True},
        "reason": "target_aware_risk_approved",
        "risk_flags": ["dry_run_only"],
        "gating_notes": ["promotion only"],
        "signal_id": 11,
        "trade_run_id": 22,
        "simulated_order_id": 33,
    }


def _now() -> datetime:
    return datetime(2026, 6, 26, 1, 0, tzinfo=UTC)

