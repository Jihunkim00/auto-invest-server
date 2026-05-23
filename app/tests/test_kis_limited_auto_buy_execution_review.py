from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
from app.main import app
from app.services.kis_limited_auto_buy_execution_review_service import REVIEW_MODE
from app.services.kis_limited_auto_buy_service import (
    GUARDED_SOURCE_TYPE,
    PREFLIGHT_MODE,
    PREFLIGHT_TRIGGER_SOURCE,
    RUN_MODE,
    RUN_TRIGGER_SOURCE,
    SOURCE,
    SOURCE_TYPE,
)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_execution_review_empty_summary_is_safe(client, db_session):
    response = client.get("/kis/limited-auto-buy/execution-review")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == REVIEW_MODE
    assert body["review_only"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["summary"]["total_decisions"] == 0
    assert body["summary"]["submitted_buy_count"] == 0
    assert body["summary"]["blocked_count"] == 0
    assert body["summary"]["no_submit_invariant_ok"] is True
    assert body["submitted_buys"] == []
    assert body["blocked_decisions"] == []
    assert body["safety_violations"] == []
    assert body["safety"]["no_broker_submit_from_review"] is True
    assert db_session.query(OrderLog).count() == 0


def test_execution_review_aggregates_submitted_guarded_buy_rows(client, db_session):
    order = _seed_order(db_session)
    _seed_run(
        db_session,
        result="submitted",
        action="buy",
        reason="guarded_limited_auto_buy_submitted",
        block_reasons=[],
        order_id=order.id,
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
        validation_called=True,
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["summary"]["submitted_buy_count"] == 1
    assert body["summary"]["submitted_rows_have_audit_metadata"] is True
    assert body["summary"]["submitted_rows_have_order_ids"] is True
    assert body["summary"]["submitted_rows_have_kis_odno_count"] == 1
    item = body["submitted_buys"][0]
    assert item["order_id"] == order.id
    assert item["broker_order_id"] == "KIS123"
    assert item["kis_odno"] == "KIS123"
    assert item["symbol"] == "005930"
    assert item["quantity"] == 4
    assert item["estimated_notional"] == pytest.approx(288000)
    assert item["final_buy_score"] == pytest.approx(82.5)
    assert item["required_buy_score"] == pytest.approx(75)
    assert item["validation_called"] is True
    assert item["manual_submit_called"] is True
    assert item["broker_submit_called"] is True
    assert body["safety_violations"] == []


def test_execution_review_aggregates_blocked_decisions(client, db_session):
    _seed_run(
        db_session,
        result="blocked",
        action="blocked_buy",
        reason="insufficient_cash",
        primary_block_reason="insufficient_cash",
        block_reasons=["insufficient_cash"],
        estimated_notional=500000,
        cash_available=1000,
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["summary"]["blocked_count"] == 1
    assert body["summary"]["cash_block_count"] == 1
    item = body["blocked_decisions"][0]
    assert item["symbol"] == "005930"
    assert item["primary_block_reason"] == "insufficient_cash"
    assert item["estimated_notional"] == pytest.approx(500000)
    assert item["cash_available"] == pytest.approx(1000)
    assert item["real_order_submitted"] is False
    assert item["broker_submit_called"] is False
    assert item["manual_submit_called"] is False


def test_execution_review_reports_top_block_reasons(client, db_session):
    _seed_run(
        db_session,
        symbol="005930",
        reason="score_threshold_not_met",
        primary_block_reason="score_threshold_not_met",
        block_reasons=["score_threshold_not_met"],
    )
    _seed_run(
        db_session,
        symbol="000660",
        reason="score_threshold_not_met",
        primary_block_reason="score_threshold_not_met",
        block_reasons=["score_threshold_not_met"],
    )
    _seed_run(
        db_session,
        symbol="035420",
        reason="duplicate_position",
        primary_block_reason="duplicate_position",
        block_reasons=["duplicate_position"],
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["top_block_reasons"][0] == {
        "reason": "score_threshold_not_met",
        "count": 2,
        "label": "Score threshold not met",
    }
    assert body["summary"]["score_block_count"] == 2
    assert body["summary"]["duplicate_position_block_count"] == 1


def test_execution_review_detects_submitted_row_missing_audit_metadata(
    client,
    db_session,
):
    order = _seed_order(db_session, include_metadata=False)
    _seed_run(
        db_session,
        result="submitted",
        action="buy",
        order_id=order.id,
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
        validation_called=True,
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["summary"]["submitted_buy_count"] == 1
    assert body["summary"]["submitted_rows_have_audit_metadata"] is False
    assert {
        item["code"] for item in body["safety_violations"]
    } >= {"submitted_buy_missing_source_metadata"}


def test_execution_review_detects_readiness_row_with_broker_submit_called(
    client,
    db_session,
):
    _seed_run(
        db_session,
        mode=PREFLIGHT_MODE,
        trigger_source=PREFLIGHT_TRIGGER_SOURCE,
        source_type=SOURCE_TYPE,
        result="ready",
        action="buy_ready",
        reason="buy_readiness_only",
        block_reasons=[],
        broker_submit_called=True,
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["summary"]["no_submit_invariant_ok"] is False
    assert body["safety"]["no_submit_invariant_ok"] is False
    assert {
        item["code"] for item in body["safety_violations"]
    } >= {"readiness_row_broker_submit_called"}


def test_execution_review_detects_daily_limit_exceeded(client, db_session):
    first = _seed_order(db_session, symbol="005930", broker_order_id="KIS001")
    second = _seed_order(db_session, symbol="000660", broker_order_id="KIS002")
    _seed_run(
        db_session,
        symbol="005930",
        result="submitted",
        action="buy",
        order_id=first.id,
        block_reasons=[],
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
        validation_called=True,
    )
    _seed_run(
        db_session,
        symbol="000660",
        result="submitted",
        action="buy",
        order_id=second.id,
        block_reasons=[],
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
        validation_called=True,
    )

    body = client.get("/kis/limited-auto-buy/execution-review").json()

    assert body["summary"]["submitted_buy_count"] == 2
    assert body["summary"]["max_daily_buy_count_observed"] == 2
    assert body["daily_usage"][0]["limit_exceeded"] is True
    assert {
        item["code"] for item in body["safety_violations"]
    } >= {"submitted_buy_daily_limit_exceeded"}


def test_execution_review_filters_by_symbol(client, db_session):
    samsung = _seed_order(db_session, symbol="005930", broker_order_id="KIS001")
    hynix = _seed_order(db_session, symbol="000660", broker_order_id="KIS002")
    _seed_run(db_session, symbol="005930", order_id=samsung.id)
    _seed_run(db_session, symbol="000660", order_id=hynix.id)

    body = client.get("/kis/limited-auto-buy/execution-review?symbol=005930").json()

    assert body["summary"]["total_decisions"] == 1
    assert body["summary"]["submitted_buy_count"] == 1
    assert body["submitted_buys"][0]["symbol"] == "005930"
    assert body["recent_decisions"][0]["symbol"] == "005930"


def test_execution_review_respects_limit_and_days(client, db_session):
    _seed_run(db_session, symbol="005930", created_days_ago=1)
    _seed_run(db_session, symbol="000660", created_days_ago=2)
    _seed_run(db_session, symbol="035420", created_days_ago=3)
    _seed_run(db_session, symbol="051910", created_days_ago=60)

    body = client.get("/kis/limited-auto-buy/execution-review?limit=2&days=30").json()

    assert body["summary"]["total_decisions"] == 3
    assert len(body["recent_decisions"]) == 2
    assert [item["symbol"] for item in body["recent_decisions"]] == [
        "005930",
        "000660",
    ]


def test_execution_review_never_creates_order_log(client, db_session):
    _seed_run(db_session)
    before = db_session.query(OrderLog).count()

    response = client.get("/kis/limited-auto-buy/execution-review")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == before


def test_execution_review_never_calls_broker_or_manual_submit(
    monkeypatch,
    client,
    db_session,
):
    _seed_run(db_session)

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("KIS cash order path must not run"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("KIS order path must not run"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual order path must not run"),
        raising=False,
    )

    response = client.get("/kis/limited-auto-buy/execution-review")

    assert response.status_code == 200
    assert response.json()["safety"]["no_broker_submit_from_review"] is True
    assert db_session.query(OrderLog).count() == 0


def _seed_run(
    db_session,
    *,
    symbol: str = "005930",
    company_name: str = "Samsung Electronics",
    mode: str = RUN_MODE,
    trigger_source: str = RUN_TRIGGER_SOURCE,
    source_type: str = GUARDED_SOURCE_TYPE,
    result: str = "blocked",
    action: str = "blocked_buy",
    reason: str = "score_threshold_not_met",
    primary_block_reason: str | None = "score_threshold_not_met",
    block_reasons: list[str] | None = None,
    final_buy_score: float | None = 60,
    final_sell_score: float | None = 12,
    required_buy_score: float | None = 75,
    confidence: float | None = 0.76,
    estimated_notional: float | None = 288000,
    suggested_quantity: int | None = 4,
    cash_available: float | None = 3000000,
    order_id: int | None = None,
    real_order_submitted: bool = False,
    broker_submit_called: bool = False,
    manual_submit_called: bool = False,
    validation_called: bool = False,
    created_days_ago: int = 1,
) -> TradeRunLog:
    reasons = block_reasons if block_reasons is not None else ["score_threshold_not_met"]
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": mode,
        "source": SOURCE,
        "source_type": source_type,
        "trigger_source": trigger_source,
        "result": result,
        "action": action,
        "reason": reason,
        "primary_block_reason": primary_block_reason,
        "symbol": symbol,
        "company_name": company_name,
        "quantity": suggested_quantity,
        "suggested_quantity": suggested_quantity,
        "current_price": 72000,
        "estimated_notional": estimated_notional,
        "final_buy_score": final_buy_score,
        "final_sell_score": final_sell_score,
        "required_buy_score": required_buy_score,
        "confidence": confidence,
        "cash_available": cash_available,
        "daily_buy_limit": 1,
        "daily_buy_limit_remaining": 1,
        "max_notional_pct": 0.03,
        "total_asset_value": 10000000,
        "block_reasons": reasons,
        "order_id": order_id,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "validation_called": validation_called,
        "source_metadata": _metadata(
            symbol=symbol,
            company_name=company_name,
            source_type=source_type,
            validation_called=validation_called,
            real_order_submitted=real_order_submitted,
            broker_submit_called=broker_submit_called,
            manual_submit_called=manual_submit_called,
        ),
        "diagnostics": {
            "duplicate_order_check": {
                "duplicate_position": "duplicate_position" in reasons,
                "duplicate_open_buy_order": "duplicate_open_buy_order" in reasons,
            },
            "daily_limit_summary": {
                "daily_buy_count": 0,
                "daily_buy_limit": 1,
                "daily_buy_limit_remaining": 1,
            },
        },
    }
    row = TradeRunLog(
        run_key=f"execution-review-{symbol}-{created_days_ago}-{order_id or 'x'}",
        trigger_source=trigger_source,
        symbol=symbol,
        mode=mode,
        symbol_role="watchlist_candidate",
        gate_level=2,
        stage="done",
        result=result,
        reason=reason,
        order_id=order_id,
        request_payload=json.dumps(
            {
                "provider": "kis",
                "market": "KR",
                "source": SOURCE,
                "source_type": source_type,
                "mode": mode,
                "trigger_source": trigger_source,
                "real_order_submitted": real_order_submitted,
                "broker_submit_called": broker_submit_called,
                "manual_submit_called": manual_submit_called,
                "validation_called": validation_called,
            }
        ),
        response_payload=json.dumps(payload),
        created_at=(datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
            tzinfo=None
        ),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _seed_order(
    db_session,
    *,
    symbol: str = "005930",
    company_name: str = "Samsung Electronics",
    broker_order_id: str = "KIS123",
    include_metadata: bool = True,
    validation_called: bool = True,
    created_days_ago: int = 1,
) -> OrderLog:
    metadata = _metadata(
        symbol=symbol,
        company_name=company_name,
        validation_called=validation_called,
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
    )
    source_fields = {
        "source": SOURCE,
        "source_type": GUARDED_SOURCE_TYPE,
        "mode": RUN_MODE,
        "trigger_source": RUN_TRIGGER_SOURCE,
        "source_metadata": metadata,
        "validation_called": validation_called,
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
    }
    request_payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "symbol": symbol,
        "side": "buy",
        "qty": 4,
        "order_type": "market",
        "dry_run": False,
        "confirm_live": True,
    }
    response_payload = {
        "provider": "kis",
        "market": "KR",
        "mode": "manual_live",
        "symbol": symbol,
        "side": "buy",
        "qty": 4,
        "order_type": "market",
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        "validation_called": validation_called,
        "broker_order_id": broker_order_id,
        "kis_odno": broker_order_id,
    }
    if include_metadata:
        request_payload.update(source_fields)
        response_payload.update(source_fields)
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side="buy",
        order_type="market",
        time_in_force="day",
        qty=4,
        requested_qty=4,
        remaining_qty=4,
        notional=288000,
        internal_status="SUBMITTED",
        broker_status="submitted",
        broker_order_status="submitted",
        broker_order_id=broker_order_id,
        kis_odno=broker_order_id,
        request_payload=json.dumps(request_payload),
        response_payload=json.dumps(response_payload),
        created_at=(datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
            tzinfo=None
        ),
        submitted_at=(datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
            tzinfo=None
        ),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _metadata(
    *,
    symbol: str,
    company_name: str,
    source_type: str = GUARDED_SOURCE_TYPE,
    validation_called: bool,
    real_order_submitted: bool,
    broker_submit_called: bool,
    manual_submit_called: bool,
) -> dict:
    return {
        "source": SOURCE,
        "source_type": source_type,
        "mode": RUN_MODE,
        "trigger_source": RUN_TRIGGER_SOURCE,
        "symbol": symbol,
        "company_name": company_name,
        "quantity": 4,
        "suggested_quantity": 4,
        "current_price": 72000,
        "estimated_notional": 288000,
        "available_cash": 3000000,
        "total_asset_value": 10000000,
        "max_notional_pct": 0.03,
        "final_buy_score": 82.5,
        "required_buy_score": 75,
        "final_sell_score": 12,
        "confidence": 0.76,
        "gate_level": 2,
        "daily_limit_summary": {
            "daily_buy_count": 0,
            "daily_buy_limit": 1,
            "daily_buy_limit_remaining": 1,
        },
        "duplicate_order_check": {
            "duplicate_position": False,
            "duplicate_open_buy_order": False,
        },
        "market_session_snapshot": {
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "no_new_entry_after_blocked": False,
        },
        "runtime_snapshot": {
            "dry_run": False,
            "kill_switch": False,
            "kis_scheduler_allow_real_orders": False,
        },
        "validation_summary": {
            "validated_for_submission": True,
            "current_price": 72000,
            "estimated_amount": 288000,
        },
        "validation_called": validation_called,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
    }
