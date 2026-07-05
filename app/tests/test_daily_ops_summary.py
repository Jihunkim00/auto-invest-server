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
    StrategyLiveAutoExitAttempt,
    StrategyPerformanceSnapshot,
    StrategyProfile,
    TradeRunLog,
)
from app.main import app
from app.schemas.agent_chat_orchestrator import (
    AgentChatIntent,
    AgentChatIntentCategory,
)
from app.schemas.agent_chat_tool import AgentChatToolCall
from app.services.agent_chat_tool_executor import AgentChatToolExecutor
from app.services.agent_chat_tool_registry import AgentChatToolRegistry
from app.services.kis_manual_order_service import KisManualOrderService


def test_daily_summary_route_is_local_read_only_and_reports_reconciliation(
    db_session,
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("daily summary must not call broker or submit paths")

    monkeypatch.setattr(KisClient, "list_positions", forbidden, raising=False)
    monkeypatch.setattr(KisClient, "submit_domestic_cash_order", forbidden, raising=False)
    monkeypatch.setattr(KisManualOrderService, "submit_manual", forbidden, raising=False)

    now = datetime(2026, 7, 3, 1, 0, tzinfo=UTC)
    db_session.add(
        RuntimeSetting(
            dry_run=True,
            kill_switch=True,
            scheduler_enabled=True,
            strategy_auto_buy_scheduler_enabled=True,
            strategy_auto_buy_scheduler_dry_run_only=True,
            strategy_auto_buy_scheduler_allow_live_orders=False,
            max_trades_per_day=3,
            max_open_positions=2,
        )
    )
    db_session.add(
        StrategyProfile(
            profile_name="safe",
            display_name="Safe",
            description="test",
            monthly_target_return_pct=0.02,
            monthly_target_min_pct=0.01,
            monthly_target_max_pct=0.02,
            monthly_max_loss_pct=0.03,
            daily_max_loss_pct=0.01,
            max_order_notional_pct=0.03,
            max_order_notional_krw=50000,
            max_trades_per_day=3,
            max_positions=2,
            buy_score_threshold=75,
            sell_score_threshold=30,
            stop_loss_pct=0.03,
            take_profit_pct=0.05,
            max_holding_days=10,
            is_active=True,
        )
    )
    db_session.add_all(
        [
            _order(
                symbol="005930",
                side="buy",
                status="FILLED",
                qty=2,
                price=5000,
                notional=10000,
                at=now,
                broker_order_id="buy-1",
                kis_odno="buy-1",
            ),
            _order(
                symbol="005930",
                side="sell",
                status="FILLED",
                qty=2,
                price=5400,
                notional=10800,
                at=now + timedelta(minutes=30),
                broker_order_id="sell-1",
                kis_odno="sell-1",
            ),
            _order(
                symbol="000660",
                side="buy",
                status="SUBMITTED",
                qty=1,
                price=80000,
                notional=80000,
                at=now + timedelta(minutes=40),
                broker_status=None,
                broker_order_id=None,
                kis_odno=None,
            ),
            _order(
                symbol="035420",
                side="buy",
                status="DRY_RUN_SIMULATED",
                qty=1,
                price=180000,
                notional=180000,
                at=now + timedelta(minutes=50),
                request_payload={"dry_run": True},
            ),
        ]
    )
    db_session.add(
        StrategyLiveAutoBuyAttempt(
            provider="kis",
            market="KR",
            active_profile="safe",
            symbol="005930",
            status="submitted",
            trigger_source="promotion_conversion",
            created_at=now,
        )
    )
    db_session.add(
        StrategyLiveAutoExitAttempt(
            provider="kis",
            market="KR",
            active_profile="safe",
            symbol="000660",
            status="blocked",
            trigger_source="risk_exit",
            block_reason="target_risk_rejected",
            created_at=now,
        )
    )
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
            created_at=now,
            expires_at=now + timedelta(minutes=45),
        )
    )
    db_session.add(
        TradeRunLog(
            run_key="scheduler-1",
            trigger_source="strategy_auto_buy_dry_run",
            symbol="005930",
            mode="strategy_auto_buy_scheduler_dry_run",
            stage="completed",
            result="would_buy",
            response_payload=json.dumps({"action": "would_buy", "created_promotion": True}),
            created_at=now,
        )
    )
    db_session.add(
        StrategyPerformanceSnapshot(
            provider="kis",
            market="KR",
            profile_name="safe",
            period_type="daily",
            period_key="2026-07-03",
            realized_pnl=800,
            unrealized_pnl=120,
            gross_pnl=920,
            estimated_fees=0,
            net_pnl_estimated=920,
            pnl_pct=0.08,
            orders_count=2,
            filled_orders_count=2,
            rejected_orders_count=0,
            win_rate=1.0,
            max_drawdown_pct=0,
            source_payload=json.dumps({"cash": 500000, "total_position_value": 120000}),
            created_at=now,
        )
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get(
            "/ops/daily-summary?date=2026-07-03&provider=kis&market=KR"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-07-03"
    assert body["runtime_state"]["dry_run"] is True
    assert body["runtime_state"]["kill_switch"] is True
    assert body["runtime_state"]["scheduler_real_orders_allowed"] is False
    assert body["trade_activity"]["guarded_buy_attempt_count"] == 1
    assert body["trade_activity"]["guarded_sell_attempt_count"] == 1
    assert body["trade_activity"]["blocked_attempt_count"] == 1
    assert body["trade_activity"]["dry_run_simulated_count"] >= 1
    assert body["pnl_summary"]["realized_pl"] == 800
    assert body["pnl_summary"]["realized_pl_pct"] == 0.08
    assert body["pnl_summary"]["unrealized_pl"] == 120
    assert body["pnl_summary"]["cash"] == 500000
    assert body["order_summary"]["total_orders_today"] == 4
    assert body["order_summary"]["sync_required_count"] == 1
    assert body["promotion_summary"]["pending"] == 1
    assert body["scheduler_summary"]["would_buy_count"] == 1
    assert body["scheduler_summary"]["real_order_submitted"] is False
    assert body["reconciliation"]["status"] == "attention_required"
    assert body["reconciliation"]["missing_kis_odno_count"] == 1
    assert body["reconciliation"]["broker_read_available"] is False
    assert body["safety"] == {
        "read_only": True,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "validation_called": False,
        "sync_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "order_state_mutated": False,
    }
    assert "request_payload" not in json.dumps(body["details"])
    assert "secret" not in json.dumps(body).lower()


def test_daily_summary_marks_missing_fill_data_incomplete(db_session):
    now = datetime(2026, 7, 3, 1, 0, tzinfo=UTC)
    db_session.add_all(
        [
            _order(
                symbol="005930",
                side="buy",
                status="FILLED",
                qty=1,
                price=None,
                notional=None,
                at=now,
                broker_order_id="buy-1",
                kis_odno="buy-1",
            ),
            _order(
                symbol="005930",
                side="sell",
                status="FILLED",
                qty=1,
                price=5400,
                notional=5400,
                at=now + timedelta(minutes=10),
                broker_order_id="sell-1",
                kis_odno="sell-1",
            ),
        ]
    )
    db_session.commit()

    from app.services.daily_ops_summary_service import DailyOpsSummaryService

    body = DailyOpsSummaryService().summary(
        db_session,
        date_value=datetime(2026, 7, 3).date(),
        provider="kis",
        market="KR",
    )

    assert body["pnl_summary"]["realized_pl"] == 0
    assert body["pnl_summary"]["realized_pl_pct"] is None
    assert body["pnl_summary"]["incomplete_calculation_count"] >= 1
    assert "missing_fill_price" in body["pnl_summary"]["audit_flags"]


def test_daily_ops_summary_agent_chat_lookup_is_read_only(db_session):
    tool = AgentChatToolRegistry().require("daily_ops_summary_lookup")
    assert tool.mode == "read_only"
    assert tool.allowed_auto_execute is True
    assert tool.mutation is False

    executor = AgentChatToolExecutor(
        kis_client_factory=lambda db: _ForbiddenKisClient(),
    )
    intent = AgentChatIntent(
        category=AgentChatIntentCategory.READ_ONLY_DAILY_OPS_SUMMARY_QUERY,
        provider="kis",
        market="KR",
    )

    result = executor.execute(
        db_session,
        call=AgentChatToolCall(tool_name="daily_ops_summary_lookup"),
        intent=intent,
    )

    assert result.status == "success"
    assert result.result_type == "daily_ops_summary"
    assert result.safety.read_only is True
    assert result.safety.broker_submit_called is False
    assert result.safety.manual_submit_called is False
    assert result.safety.validation_called is False
    assert result.data["safety"]["sync_called"] is False
    assert result.data["reconciliation"]["broker_read_available"] is False


def _order(
    *,
    symbol: str,
    side: str,
    status: str,
    qty: float,
    price: float | None,
    notional: float | None,
    at: datetime,
    broker_status: str | None = "filled",
    broker_order_id: str | None = "broker-1",
    kis_odno: str | None = "odno-1",
    request_payload: dict[str, object] | None = None,
) -> OrderLog:
    return OrderLog(
        broker="kis",
        market="KR",
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        requested_qty=qty,
        filled_qty=qty if status in {"FILLED", "PARTIALLY_FILLED", "DRY_RUN_SIMULATED"} else 0,
        notional=notional,
        filled_avg_price=price,
        avg_fill_price=price,
        internal_status=status,
        broker_status=broker_status,
        broker_order_status=broker_status,
        broker_order_id=broker_order_id,
        kis_odno=kis_odno,
        submitted_at=at,
        filled_at=at if status in {"FILLED", "DRY_RUN_SIMULATED"} else None,
        created_at=at,
        updated_at=at,
        request_payload=json.dumps(request_payload) if request_payload else None,
    )


class _ForbiddenKisClient:
    def list_positions(self):
        raise AssertionError("daily ops chat lookup must not read live positions")

    def submit_domestic_cash_order(self, *args, **kwargs):
        raise AssertionError("daily ops chat lookup must not submit orders")
