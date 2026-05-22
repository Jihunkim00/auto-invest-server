from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.main import app
from app.services.kis_limited_auto_buy_review_service import REVIEW_MODE
from app.services.kis_limited_auto_buy_service import (
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


def test_review_empty_summary_is_safe_and_read_only(client, db_session):
    response = client.get("/kis/limited-auto-buy/review")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == REVIEW_MODE
    assert body["review_only"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["summary"]["total_runs"] == 0
    assert body["summary"]["no_submit_invariant_ok"] is True
    assert body["recent_decisions"] == []
    assert body["latest_buy_ready"] is None
    assert body["safety"]["no_order_log_created"] is True
    assert db_session.query(RuntimeSetting).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_review_aggregates_buy_ready_decisions(client, db_session):
    _seed_run(
        db_session,
        result="readiness_only",
        action="buy_ready",
        reason="buy_readiness_only",
        primary_block_reason="auto_buy_execution_disabled",
        block_reasons=["auto_buy_execution_disabled"],
        final_buy_score=82.5,
        final_sell_score=12,
        required_buy_score=75,
        confidence=0.76,
    )

    body = client.get("/kis/limited-auto-buy/review").json()

    assert body["summary"]["total_runs"] == 1
    assert body["summary"]["buy_ready_count"] == 1
    assert body["summary"]["blocked_count"] == 0
    assert body["summary"]["avg_final_buy_score"] == pytest.approx(82.5)
    assert body["summary"]["avg_required_buy_score"] == pytest.approx(75)
    assert body["summary"]["latest_candidate_symbol"] == "005930"
    assert body["latest_buy_ready"]["status"] == "BUY_READY"
    assert body["latest_buy_ready"]["broker_submit_called"] is False
    assert body["top_block_reasons"] == []
    assert db_session.query(OrderLog).count() == 0


def test_review_aggregates_blocked_decisions_and_top_reasons(client, db_session):
    _seed_run(
        db_session,
        symbol="005930",
        result="blocked",
        action="hold",
        reason="score_threshold_not_met",
        primary_block_reason="score_threshold_not_met",
        block_reasons=["score_threshold_not_met", "auto_buy_execution_disabled"],
        final_buy_score=60,
        required_buy_score=75,
    )
    _seed_run(
        db_session,
        symbol="000660",
        company_name="SK Hynix",
        result="blocked",
        action="hold",
        reason="insufficient_cash",
        primary_block_reason="insufficient_cash",
        block_reasons=["insufficient_cash", "auto_buy_execution_disabled"],
        estimated_notional=500000,
        cash_available=1000,
    )

    body = client.get("/kis/limited-auto-buy/review").json()

    assert body["summary"]["blocked_count"] == 2
    assert body["summary"]["score_threshold_not_met_count"] == 1
    assert body["summary"]["insufficient_cash_count"] == 1
    top = body["top_block_reasons"]
    assert {item["reason"] for item in top} >= {
        "score_threshold_not_met",
        "insufficient_cash",
    }
    labels = {item["reason"]: item["label"] for item in top}
    assert labels["score_threshold_not_met"] == "Score threshold not met"
    assert labels["insufficient_cash"] == "Insufficient cash"


def test_review_filters_by_symbol(client, db_session):
    _seed_run(db_session, symbol="005930", company_name="Samsung Electronics")
    _seed_run(db_session, symbol="000660", company_name="SK Hynix")

    body = client.get("/kis/limited-auto-buy/review?symbol=005930").json()

    assert body["summary"]["total_runs"] == 1
    assert body["recent_decisions"][0]["symbol"] == "005930"


def test_review_respects_limit_and_days(client, db_session):
    _seed_run(db_session, symbol="005930", created_days_ago=1)
    _seed_run(db_session, symbol="000660", company_name="SK Hynix", created_days_ago=2)
    _seed_run(db_session, symbol="035420", company_name="NAVER", created_days_ago=3)
    _seed_run(db_session, symbol="051910", company_name="LG Chem", created_days_ago=60)

    body = client.get("/kis/limited-auto-buy/review?limit=2&days=30").json()

    assert body["summary"]["total_runs"] == 3
    assert len(body["recent_decisions"]) == 2
    assert [item["symbol"] for item in body["recent_decisions"]] == [
        "005930",
        "000660",
    ]


def test_review_never_creates_order_log_or_calls_submit_paths(
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

    response = client.get("/kis/limited-auto-buy/review")

    assert response.status_code == 200
    assert db_session.query(OrderLog).count() == 0
    assert response.json()["safety"]["no_order_log_created"] is True


def test_review_flags_malformed_historical_submit_row_without_submitting(
    client,
    db_session,
):
    _seed_run(
        db_session,
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
    )

    body = client.get("/kis/limited-auto-buy/review").json()

    assert body["summary"]["no_submit_invariant_ok"] is False
    assert body["safety"]["no_submit_invariant_ok"] is False
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["recent_decisions"][0]["real_order_submitted"] is True
    assert db_session.query(OrderLog).count() == 0


def _seed_run(
    db_session,
    *,
    symbol: str = "005930",
    company_name: str = "Samsung Electronics",
    mode: str = RUN_MODE,
    trigger_source: str = RUN_TRIGGER_SOURCE,
    result: str = "readiness_only",
    action: str = "buy_ready",
    reason: str = "buy_readiness_only",
    primary_block_reason: str = "auto_buy_execution_disabled",
    block_reasons: list[str] | None = None,
    final_buy_score: float | None = 82.5,
    final_sell_score: float | None = 12.0,
    required_buy_score: float | None = 75.0,
    confidence: float | None = 0.76,
    estimated_notional: float | None = 288000,
    suggested_quantity: int | None = 4,
    cash_available: float | None = 3000000,
    real_order_submitted: bool = False,
    broker_submit_called: bool = False,
    manual_submit_called: bool = False,
    created_days_ago: int = 1,
) -> TradeRunLog:
    reasons = block_reasons or ["auto_buy_execution_disabled"]
    candidate_status = "BUY READY" if action == "buy_ready" else "WATCH"
    candidate = {
        "symbol": symbol,
        "company_name": company_name,
        "status": candidate_status,
        "final_buy_score": final_buy_score,
        "final_sell_score": final_sell_score,
        "required_buy_score": required_buy_score,
        "confidence": confidence,
        "estimated_notional": estimated_notional,
        "suggested_quantity": suggested_quantity,
        "cash_available": cash_available,
        "block_reasons": [] if action == "buy_ready" else reasons,
        "duplicate_position": "duplicate_position" in reasons,
        "duplicate_open_buy_order": "duplicate_open_buy_order" in reasons,
        "market_session_allowed": "market_closed" not in reasons,
        "no_new_entry_after_blocked": "no_new_entry_after_blocked" in reasons,
    }
    payload = {
        "provider": "kis",
        "market": "KR",
        "mode": mode,
        "source": SOURCE,
        "source_type": SOURCE_TYPE,
        "trigger_source": trigger_source,
        "result": result,
        "action": action,
        "reason": reason,
        "primary_block_reason": primary_block_reason,
        "symbol": symbol,
        "company_name": company_name,
        "final_candidate": candidate,
        "candidate": candidate,
        "final_buy_score": final_buy_score,
        "final_sell_score": final_sell_score,
        "required_buy_score": required_buy_score,
        "confidence": confidence,
        "estimated_notional": estimated_notional,
        "suggested_quantity": suggested_quantity,
        "cash_available": cash_available,
        "block_reasons": reasons,
        "gate_level": 2,
        "real_order_submitted": real_order_submitted,
        "broker_submit_called": broker_submit_called,
        "manual_submit_called": manual_submit_called,
        "diagnostics": {
            "duplicate_order_check": {
                "duplicate_position": "duplicate_position" in reasons,
                "duplicate_open_buy_order": "duplicate_open_buy_order" in reasons,
            }
        },
    }
    row = TradeRunLog(
        run_key=f"review-test-{symbol}-{created_days_ago}",
        trigger_source=trigger_source,
        symbol=symbol,
        mode=mode,
        symbol_role="watchlist_candidate",
        gate_level=2,
        stage="done",
        result=result,
        reason=reason,
        request_payload=json.dumps(
            {
                "source": SOURCE,
                "source_type": SOURCE_TYPE,
                "mode": mode,
                "trigger_source": trigger_source,
                "real_order_submitted": real_order_submitted,
                "broker_submit_called": broker_submit_called,
                "manual_submit_called": manual_submit_called,
            }
        ),
        response_payload=json.dumps(payload),
        created_at=(datetime.now(UTC) - timedelta(days=created_days_ago)).replace(
            tzinfo=None
        ),
    )
    if mode == PREFLIGHT_MODE:
        row.trigger_source = PREFLIGHT_TRIGGER_SOURCE
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row
