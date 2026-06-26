from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import (
    KisOrderValidationLog,
    OrderLog,
    StrategyAutoBuyPromotion,
    TradeRunLog,
)
from app.services.strategy_auto_buy_scheduler_service import (
    MODE,
    StrategyAutoBuySchedulerService,
)
from app.services.strategy_profile_service import StrategyProfileService


class FakeRuntimeSettings:
    def __init__(self, **overrides):
        self.values = {
            "strategy_auto_buy_scheduler_enabled": False,
            "strategy_auto_buy_scheduler_dry_run_only": True,
            "strategy_auto_buy_scheduler_allow_live_orders": False,
            "strategy_auto_buy_scheduler_profile_source": "active",
            "strategy_auto_buy_scheduler_max_runs_per_day": 3,
            "strategy_auto_buy_scheduler_min_minutes_between_runs": 60,
            "strategy_auto_buy_scheduler_promotion_ttl_minutes": 45,
            "strategy_auto_buy_scheduler_create_promotion_on_would_buy": True,
            "strategy_auto_buy_scheduler_block_when_kill_switch": True,
            "strategy_auto_buy_scheduler_block_when_market_closed": True,
            "strategy_auto_buy_scheduler_block_after_no_new_entry_time": True,
            "strategy_auto_buy_scheduler_no_new_entry_after": "15:00",
            "strategy_auto_buy_scheduler_allowed_profiles": ["safe", "balanced"],
            "strategy_auto_buy_scheduler_allow_aggressive": False,
            "kill_switch": False,
        }
        self.values.update(overrides)

    def get_settings(self, db):
        return dict(self.values)

    def get_settings_read_only(self, db):
        return dict(self.values)


class FakeDryRunService:
    def __init__(self, *, action: str = "would_buy"):
        self.action = action
        self.calls = []

    def run_once(self, db, request):
        self.calls.append(request)
        if self.action != "would_buy":
            return {
                "status": "ok",
                "action": "blocked",
                "provider": "kis",
                "market": "KR",
                "active_profile": "safe",
                "selected_symbol": "005930",
                "reason": "risk_blocked",
                "safety": _dry_safety(),
            }
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
            "gating_notes": ["no real order submitted"],
            "signal_id": 11,
            "trade_run_id": 22,
            "simulated_order_id": 33,
            "safety": _dry_safety(),
        }


class FakeMarketSessions:
    def __init__(self, *, open: bool = True):
        self.open = open

    def get_session_status(self, market, now=None):
        return {
            "market": market,
            "is_market_open": self.open,
            "is_entry_allowed_now": self.open,
        }


def scheduler_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    dry_run: FakeDryRunService | None = None,
    market_sessions: FakeMarketSessions | None = None,
):
    return StrategyAutoBuySchedulerService(
        runtime_settings=runtime or FakeRuntimeSettings(),
        dry_run_service=dry_run or FakeDryRunService(),
        market_sessions=market_sessions or FakeMarketSessions(),
    )


def enabled_settings(**overrides) -> FakeRuntimeSettings:
    values = {
        "strategy_auto_buy_scheduler_enabled": True,
        "strategy_auto_buy_scheduler_min_minutes_between_runs": 0,
        "strategy_auto_buy_scheduler_block_after_no_new_entry_time": False,
    }
    values.update(overrides)
    return FakeRuntimeSettings(**values)


def test_scheduler_status_default_disabled(db_session):
    body = scheduler_service().status(db_session, now=_now())

    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["enabled"] is False
    assert body["dry_run_only"] is True
    assert body["promotion_queue_only"] is True
    assert body["allow_live_orders"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["primary_block_reason"] == "scheduler_disabled"
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["promotion_queue_only"] is True
    assert body["safety"]["real_order_submit_allowed"] is False


def test_scheduler_status_safety_allow_live_orders_false(db_session):
    body = scheduler_service(
        runtime=enabled_settings(strategy_auto_buy_scheduler_allow_live_orders=True)
    ).status(db_session, now=_now())

    assert body["allow_live_orders"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["primary_block_reason"] == "scheduler_live_orders_forbidden"


def test_manual_scheduler_dry_run_blocked_when_scheduler_disabled(db_session):
    dry = FakeDryRunService()
    body = scheduler_service(dry_run=dry).run_dry_run_once(
        db_session,
        {},
        now=_now(),
    )

    assert body["status"] == "blocked"
    assert body["block_reason"] == "scheduler_disabled"
    assert dry.calls == []
    assert db_session.query(StrategyAutoBuyPromotion).count() == 0


def test_manual_scheduler_dry_run_uses_pr73_and_never_submits(db_session):
    dry = FakeDryRunService()
    body = scheduler_service(
        runtime=enabled_settings(),
        dry_run=dry,
    ).run_dry_run_once(db_session, {}, now=_now())

    assert len(dry.calls) == 1
    assert dry.calls[0].trigger_source == "strategy_auto_buy_dry_run"
    assert body["status"] == "ok"
    assert body["created_promotion"] is True
    assert body["real_order_submitted"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["validation_called"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["safety"]["dry_run_only"] is True
    assert body["safety"]["promotion_queue_only"] is True
    assert body["safety"]["allow_live_orders"] is False
    assert body["safety"]["real_order_submit_allowed"] is False
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_would_buy_creates_pending_promotion(db_session):
    body = scheduler_service(runtime=enabled_settings()).run_dry_run_once(
        db_session,
        {},
        now=_now(),
    )

    assert body["promotion"]["status"] == "pending"
    row = db_session.query(StrategyAutoBuyPromotion).one()
    assert row.symbol == "005930"
    assert row.status == "pending"
    assert row.source_dry_run_trade_run_id == 22


def test_blocked_dry_run_does_not_create_promotion(db_session):
    body = scheduler_service(
        runtime=enabled_settings(),
        dry_run=FakeDryRunService(action="blocked"),
    ).run_dry_run_once(db_session, {}, now=_now())

    assert body["action"] == "blocked"
    assert body["created_promotion"] is False
    assert db_session.query(StrategyAutoBuyPromotion).count() == 0


def test_max_runs_per_day_blocks_extra_dry_run(db_session):
    service = scheduler_service(
        runtime=enabled_settings(strategy_auto_buy_scheduler_max_runs_per_day=1)
    )
    first = service.run_dry_run_once(db_session, {}, now=_now())
    second = service.run_dry_run_once(db_session, {}, now=_now() + timedelta(minutes=1))

    assert first["status"] == "ok"
    assert second["status"] == "blocked"
    assert second["block_reason"] == "max_runs_per_day_reached"


def test_min_interval_blocks_too_frequent_dry_run(db_session):
    service = scheduler_service(
        runtime=enabled_settings(
            strategy_auto_buy_scheduler_max_runs_per_day=3,
            strategy_auto_buy_scheduler_min_minutes_between_runs=60,
        )
    )
    first = service.run_dry_run_once(db_session, {}, now=_now())
    second = service.run_dry_run_once(db_session, {}, now=_now() + timedelta(minutes=5))

    assert first["status"] == "ok"
    assert second["status"] == "blocked"
    assert second["block_reason"] == "min_interval_not_elapsed"


def test_no_new_entry_after_blocks_scheduler_dry_run(db_session):
    service = scheduler_service(
        runtime=enabled_settings(
            strategy_auto_buy_scheduler_block_after_no_new_entry_time=True,
            strategy_auto_buy_scheduler_no_new_entry_after="15:00",
        )
    )
    body = service.run_dry_run_once(
        db_session,
        {},
        now=datetime(2026, 6, 26, 6, 30, tzinfo=UTC),
    )

    assert body["status"] == "blocked"
    assert body["block_reason"] == "after_no_new_entry_time"


def test_aggressive_profile_blocked_by_default(db_session):
    profiles = StrategyProfileService()
    profiles.ensure_seeded(db_session)
    for row in db_session.query(type(profiles.active_profile(db_session))).all():
        row.is_active = row.profile_name == "aggressive"
    db_session.commit()

    body = scheduler_service(runtime=enabled_settings()).run_dry_run_once(
        db_session,
        {},
        now=_now(),
    )

    assert body["status"] == "blocked"
    assert body["block_reason"] == "aggressive_profile_blocked"


def test_scheduler_run_log_safety_flags(db_session):
    scheduler_service(runtime=enabled_settings()).run_dry_run_once(
        db_session,
        {},
        now=_now(),
    )

    row = db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).one()
    assert row.trigger_source == "strategy_auto_buy_dry_run"
    assert row.result == "would_buy"
    assert "broker_submit_called" in row.request_payload


def test_scheduler_source_has_no_live_order_calls():
    source_paths = [
        "app/services/strategy_auto_buy_scheduler_service.py",
        "app/routes/strategy_auto_buy_scheduler.py",
    ]
    forbidden = [
        "submit_market_buy",
        "submit_market_sell",
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "ProfileAwareGuardedLiveAutoBuyService",
        "KisOrderValidationService",
        "KisManualOrderService",
        "live/auto-buy/run-once",
    ]

    for path in source_paths:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for pattern in forbidden:
            assert pattern not in source


def _now() -> datetime:
    return datetime(2026, 6, 26, 1, 0, tzinfo=UTC)


def _dry_safety() -> dict:
    return {
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
    }

