from __future__ import annotations

from app.services.strategy_auto_buy_operations_service import (
    StrategyAutoBuyOperationsService,
)


class FakeDryRunService:
    def __init__(self, *, items=None):
        self.items = list(items or [])

    def recent(self, db, **kwargs):
        return {
            "provider": "kis",
            "market": "KR",
            "count": len(self.items),
            "items": self.items,
            "safety": {"read_only": True},
        }

    def summary(self, db, **kwargs):
        return {
            "provider": "kis",
            "market": "KR",
            "today": {"total": len(self.items), "would_buy": 0, "blocked": 0},
            "month": {},
            "profiles": {},
            "safety": {"read_only": True},
        }

    def run_once(self, db, request):
        raise AssertionError("operations status must not run dry-run")


class FakeLiveAutoBuyService:
    def readiness(self, db, **kwargs):
        return {
            "enabled": False,
            "ready": False,
            "provider": "kis",
            "market": "KR",
            "active_profile": "safe",
            "primary_block_reason": "strategy_live_auto_buy_disabled",
            "recent_dry_run_required": True,
            "recent_dry_run_found": False,
            "dry_run": False,
            "kill_switch": False,
            "kis_real_order_enabled": False,
            "orders_remaining_today": 0,
            "checks": [],
            "safety": {"read_only": True},
        }

    def recent(self, db, **kwargs):
        return {
            "provider": "kis",
            "market": "KR",
            "count": 0,
            "items": [],
            "safety": {"read_only": True},
        }

    def run_once(self, db, request):
        raise AssertionError("operations status must not run live auto-buy")


class FakeSchedulerService:
    def __init__(self, *, enabled=True, latest_status=None):
        self.enabled = enabled
        self.latest_status = latest_status

    def status(self, db, **kwargs):
        latest = (
            {
                "id": 1,
                "result": self.latest_status,
                "action": self.latest_status,
                "created_at": "2026-06-26T01:00:00+00:00",
            }
            if self.latest_status
            else None
        )
        return {
            "enabled": self.enabled,
            "dry_run_only": True,
            "allow_live_orders": False,
            "active_profile": "safe",
            "allowed_profiles": ["safe", "balanced"],
            "runs_today": 1 if latest else 0,
            "max_runs_per_day": 3,
            "latest_scheduler_run": latest,
            "next_allowed_run_at": None,
            "primary_block_reason": None,
            "pending_promotion_count": 0,
            "safety": {"read_only": True},
        }

    def run_dry_run_once(self, db, request):
        raise AssertionError("operations status must not run scheduler dry-run")


class FakePromotionService:
    def __init__(self, *, pending_count=0, latest_status=None):
        self.pending_count = pending_count
        self.latest_status = latest_status

    def summary(self, db, **kwargs):
        return {
            "pending_count": self.pending_count,
            "latest_symbol": "005930" if self.pending_count else None,
            "latest_status": self.latest_status,
            "latest_expires_at": "2026-06-26T01:45:00+00:00"
            if self.pending_count
            else None,
            "acknowledged_count_today": 0,
            "dismissed_count_today": 0,
            "safety": {"read_only": True},
        }


class FakeRiskService:
    def risk_state(self, db, **kwargs):
        return {
            "active_profile": "safe",
            "new_entries_allowed": False,
            "target_progress_pct": 0,
            "daily_loss_limit_hit": False,
            "monthly_loss_limit_hit": False,
            "safety": {"read_only": True},
        }


def test_operations_status_includes_scheduler_summary(db_session):
    body = _service(
        scheduler=FakeSchedulerService(enabled=True, latest_status="blocked"),
    ).status(db_session)

    assert body["scheduler"]["enabled"] is True
    assert body["scheduler"]["dry_run_only"] is True
    assert body["scheduler"]["allow_live_orders"] is False
    assert body["scheduler"]["runs_today"] == 1
    assert body["scheduler"]["latest_run_status"] == "blocked"
    assert body["auto_buy_stage"] == "scheduled_dry_run_blocked"
    assert body["next_operator_action"] == "wait_for_scheduled_dry_run"
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False


def test_operations_status_includes_promotion_summary_and_stage(db_session):
    body = _service(
        scheduler=FakeSchedulerService(enabled=True),
        promotions=FakePromotionService(pending_count=1, latest_status="pending"),
    ).status(db_session)

    assert body["promotions"]["pending_count"] == 1
    assert body["promotions"]["latest_symbol"] == "005930"
    assert body["promotions"]["latest_status"] == "pending"
    assert body["auto_buy_stage"] == "promotion_pending"
    assert body["next_operator_action"] == "review_promotion"


def test_operations_status_reports_expired_promotion_operator_action(db_session):
    body = _service(
        scheduler=FakeSchedulerService(enabled=True),
        promotions=FakePromotionService(pending_count=0, latest_status="expired"),
    ).status(db_session)

    assert body["auto_buy_stage"] == "promotion_expired"
    assert body["next_operator_action"] == "acknowledge_or_dismiss_promotion"


def _service(
    *,
    scheduler=None,
    promotions=None,
) -> StrategyAutoBuyOperationsService:
    return StrategyAutoBuyOperationsService(
        dry_run_service=FakeDryRunService(),
        live_auto_buy_service=FakeLiveAutoBuyService(),
        scheduler_service=scheduler or FakeSchedulerService(enabled=False),
        promotion_service=promotions or FakePromotionService(),
        target_risk_service=FakeRiskService(),
    )
