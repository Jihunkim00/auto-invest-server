from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.brokers.kis_client import KisClient
from app.db.database import get_db
from app.db.models import (
    OrderLog,
    RuntimeSetting,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
)
from app.main import app
from app.schemas.agent_chat_orchestrator import (
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_intent_router_service import AgentChatIntentRouterService
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.kis_manual_order_service import KisManualOrderService
from app.services.kis_order_sync_service import KisOrderSyncService
from app.services.order_sync_service import OrderSyncService


def test_alerts_endpoint_returns_runtime_order_promotion_and_pnl_alerts(
    db_session,
    monkeypatch,
):
    _forbid_mutating_paths(monkeypatch)
    now = _now()
    db_session.add(
        RuntimeSetting(
            dry_run=True,
            kill_switch=True,
            scheduler_enabled=True,
            strategy_auto_buy_scheduler_enabled=True,
            strategy_auto_buy_scheduler_dry_run_only=True,
            strategy_auto_buy_scheduler_allow_live_orders=False,
            kis_scheduler_buy_enabled=True,
        )
    )
    rejected = _order(
        symbol="005930",
        status="REJECTED",
        side="buy",
        at=now - timedelta(minutes=10),
        broker_status="rejected",
        broker_order_id="reject-1",
        kis_odno="reject-1",
    )
    sync_required = _order(
        symbol="000660",
        status="SUBMITTED",
        side="buy",
        at=now - timedelta(minutes=45),
        broker_status=None,
        broker_order_id=None,
        kis_odno=None,
        sync_error="token=abc123 account=1234567890 approval_key=hidden",
    )
    incomplete_buy = _order(
        symbol="035420",
        status="FILLED",
        side="buy",
        at=now - timedelta(minutes=35),
        price=None,
        broker_order_id="buy-1",
        kis_odno="buy-1",
    )
    incomplete_sell = _order(
        symbol="035420",
        status="FILLED",
        side="sell",
        at=now - timedelta(minutes=20),
        price=10000,
        broker_order_id="sell-1",
        kis_odno="sell-1",
    )
    db_session.add_all([rejected, sync_required, incomplete_buy, incomplete_sell])
    db_session.add(
        StrategyAutoBuyPromotion(
            provider="kis",
            market="KR",
            active_profile="safe",
            symbol="005930",
            status="pending",
            dry_run_action="would_buy",
            conversion_status="blocked",
            block_reason="operator_review_required",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
            expires_at=now - timedelta(hours=1),
            risk_flags=json.dumps(["promotion_stale"]),
            gating_notes=json.dumps(["promotion_expired"]),
        )
    )
    db_session.add(
        StrategyLiveAutoBuyAttempt(
            provider="kis",
            market="KR",
            active_profile="safe",
            symbol="005930",
            status="blocked",
            trigger_source="promotion_conversion",
            block_reason="target_risk_rejected",
            created_at=now - timedelta(minutes=5),
        )
    )
    db_session.commit()
    before_status = {
        row.id: (row.internal_status, row.last_synced_at, row.sync_error)
        for row in (rejected, sync_required, incomplete_buy, incomplete_sell)
    }

    body = _get_alerts(db_session)

    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["safety_flags"]["read_only"] is True
    assert body["safety_flags"]["broker_submit_called"] is False
    assert body["safety_flags"]["sync_called"] is False
    reason_codes = {item["reason_code"] for item in body["alerts"]}
    assert "kill_switch_on" in reason_codes
    assert "dry_run_on" in reason_codes
    assert "scheduler_dry_run_only" in reason_codes
    assert "rejected_order" in reason_codes
    assert "order_sync_required" in reason_codes
    assert "missing_broker_identifier" in reason_codes
    assert "stale_order_status" in reason_codes
    assert "stale_promotion" in reason_codes
    assert "promotion_conversion_blocked" in reason_codes
    assert "guarded_buy_blocked" in reason_codes
    assert "incomplete_pl_calculation" in reason_codes
    assert body["summary"]["active_alert_count"] >= 10
    assert body["summary"]["sync_required_count"] >= 1
    assert body["summary"]["rejected_order_count"] == 1
    assert body["summary"]["stale_promotion_count"] == 1
    assert body["summary"]["incomplete_pl_count"] == 1
    assert body["summary"]["blocked_attempt_count"] == 1
    assert all(item["status"] == "active" for item in body["alerts"])
    body_text = json.dumps(body).lower()
    assert "secret" not in body_text
    assert "token" not in body_text
    assert "account" not in body_text
    assert "approval_key" not in body_text

    after_rows = db_session.query(OrderLog).all()
    after_status = {
        row.id: (row.internal_status, row.last_synced_at, row.sync_error)
        for row in after_rows
    }
    assert after_status == before_status


def test_alerts_endpoint_filters_severity_and_acknowledged_status(db_session):
    db_session.add(RuntimeSetting(dry_run=True, kill_switch=True))
    db_session.commit()

    warnings = _get_alerts(db_session, query="?severity=warning")
    assert warnings["alerts"]
    assert {item["severity"] for item in warnings["alerts"]} == {"warning"}

    acknowledged = _get_alerts(db_session, query="?status=acknowledged")
    assert acknowledged["alerts"] == []
    assert acknowledged["summary"]["active_alert_count"] == 0


def test_operator_alerts_agent_chat_lookup_is_read_only(db_session):
    tool = AgentChatToolRegistry().require("operator_alerts_lookup")
    assert tool.mode == "read_only"
    assert tool.allowed_auto_execute is True
    assert tool.mutation is False

    db_session.add(RuntimeSetting(dry_run=True, kill_switch=True))
    db_session.commit()
    executor = AgentChatToolExecutor(
        kis_client_factory=lambda db: _ForbiddenKisClient(),
    )
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.READ_ONLY_OPERATOR_ALERTS_QUERY,
        provider="kis",
        market="KR",
    )

    result = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="operator_alerts_lookup"),
        intent=intent,
    )

    assert result.status == "success"
    assert result.result_type == "operator_alerts"
    assert result.safety.read_only is True
    assert result.safety.broker_submit_called is False
    assert result.safety.manual_submit_called is False
    assert result.safety.validation_called is False
    assert result.data["safety_flags"]["sync_called"] is False
    assert result.data["summary"]["active_alert_count"] >= 1


def test_operator_alerts_router_selects_read_only_tool():
    intent = AgentChatIntentRouterService(openai_client=None).fallback_route(
        "show operator risk alerts and order warnings",
        {"default_provider": "kis", "default_market": "KR"},
    )

    assert intent.category == AgentChatIntentCategory.READ_ONLY_OPERATOR_ALERTS_QUERY
    assert [call.tool_name for call in intent.selected_tools] == [
        "operator_alerts_lookup"
    ]


def _get_alerts(db_session, *, query: str = "") -> dict:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get(f"/ops/alerts{query}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    return response.json()


def _order(
    *,
    symbol: str,
    status: str,
    side: str,
    at: datetime,
    price: float | None = 10000,
    broker_status: str | None = "filled",
    broker_order_id: str | None = "broker-1",
    kis_odno: str | None = "odno-1",
    sync_error: str | None = None,
    error_message: str | None = None,
) -> OrderLog:
    qty = 1.0
    return OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        requested_qty=qty,
        filled_qty=qty if status == "FILLED" else 0,
        notional=price * qty if price is not None else None,
        filled_avg_price=price,
        avg_fill_price=price,
        internal_status=status,
        broker_status=broker_status,
        broker_order_status=broker_status,
        broker_order_id=broker_order_id,
        kis_odno=kis_odno,
        sync_error=sync_error,
        error_message=error_message,
        submitted_at=at,
        filled_at=at if status == "FILLED" else None,
        created_at=at,
        updated_at=at,
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _forbid_mutating_paths(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("operator alerts must not call submit or sync paths")

    monkeypatch.setattr(KisClient, "submit_domestic_cash_order", forbidden, raising=False)
    monkeypatch.setattr(KisManualOrderService, "submit_manual", forbidden, raising=False)
    monkeypatch.setattr(KisOrderSyncService, "sync_order", forbidden, raising=False)
    monkeypatch.setattr(KisOrderSyncService, "sync_open_orders", forbidden, raising=False)
    monkeypatch.setattr(
        OrderSyncService,
        "sync_order_status_by_broker_order_id",
        forbidden,
        raising=False,
    )
    monkeypatch.setattr(
        OrderSyncService,
        "sync_open_orders_for_symbol",
        forbidden,
        raising=False,
    )


class _ForbiddenKisClient:
    def list_positions(self):
        raise AssertionError("operator alerts chat lookup must not read live positions")

    def submit_domestic_cash_order(self, *args, **kwargs):
        raise AssertionError("operator alerts chat lookup must not submit orders")
