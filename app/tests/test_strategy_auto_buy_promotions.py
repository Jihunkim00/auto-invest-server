from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import (
    KisOrderValidationLog,
    OrderLog,
    StrategyAutoBuyPromotion,
)
from app.main import app
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
    assert body["items"][0]["review_status"] == "pending_review"
    assert body["items"][0]["review_required"] is True
    assert body["items"][0]["conversion_allowed_by_state"] is True
    assert body["items"][0]["conversion_block_reason"] is None
    assert body["items"][0]["proposed_notional_krw"] == 30000
    assert body["items"][0]["dry_run_evidence"]["action"] == "would_buy"
    assert body["items"][0]["score_summary"]["score"] == 82
    assert body["safety"]["read_only"] is True


def test_promotions_route_returns_review_metadata(db_session):
    service = StrategyAutoBuyPromotionService()
    service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        request_payload={"source": "pytest"},
        now=_now(),
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/strategy/auto-buy/promotions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["review_status"] == "pending_review"
    assert item["review_required"] is True
    assert item["review_checklist"]
    assert item["review_summary"]
    assert item["target_risk_summary"]["approved"] is True


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


def test_mark_reviewed_updates_local_state_only(db_session):
    service = StrategyAutoBuyPromotionService()
    promotion = service.create_from_dry_run(
        db_session,
        dry_run_result=_dry_run(),
        now=_now(),
    )

    body = service.mark_reviewed(db_session, promotion["id"])

    assert body["status"] == "reviewed"
    assert body["promotion"]["review_status"] == "reviewed"
    assert body["promotion"]["review_required"] is False
    assert body["promotion"]["conversion_allowed_by_state"] is True
    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert row.status == "reviewed"
    assert row.acknowledged_at is not None
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0


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


def test_create_sanitizes_sensitive_payload_fields(db_session):
    service = StrategyAutoBuyPromotionService()

    body = service.create_from_dry_run(
        db_session,
        dry_run_result={
            **_dry_run(),
            "target_risk_result": {
                "approved": True,
                "appsecret": "secret-value",
                "authorization": "Bearer secret-token",
                "account_no": "1234567890",
            },
        },
        request_payload={
            "appkey": "secret-key",
            "account_number": "1234567890",
        },
        now=_now(),
    )

    assert body["target_risk_result"]["appsecret"] == "***"
    assert body["target_risk_result"]["authorization"] == "***"
    assert body["target_risk_result"]["account_no"] == "12******90"
    assert body["request_payload"]["appkey"] == "***"
    assert body["request_payload"]["account_number"] == "12******90"


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
    return datetime.now(UTC)

