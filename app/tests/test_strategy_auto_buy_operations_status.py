from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.strategy_auto_buy_operations import (
    get_strategy_auto_buy_operations_service,
)
from app.services.strategy_auto_buy_operations_service import (
    StrategyAutoBuyOperationsService,
)


class FakeDryRunService:
    def __init__(self, *, items=None):
        self.items = list(items or [])
        self.calls: list[str] = []

    def recent(self, db, **kwargs):
        self.calls.append("recent")
        return {
            "provider": kwargs.get("provider", "kis"),
            "market": kwargs.get("market", "KR"),
            "count": len(self.items),
            "items": self.items,
            "safety": {"read_only": True},
        }

    def summary(self, db, **kwargs):
        self.calls.append("summary")
        return {
            "provider": kwargs.get("provider", "kis"),
            "market": kwargs.get("market", "KR"),
            "today": {
                "date": datetime.now(UTC).date().isoformat(),
                "total": len(self.items),
                "would_buy": len(
                    [item for item in self.items if item.get("action") == "would_buy"]
                ),
                "blocked": len(
                    [item for item in self.items if item.get("action") == "blocked"]
                ),
            },
            "month": {},
            "profiles": {},
            "safety": {"read_only": True},
        }

    def run_once(self, db, request):
        raise AssertionError("operations status must not run dry-run")


class FakeLiveAutoBuyService:
    def __init__(self, *, readiness=None, attempts=None):
        self.readiness_payload = readiness or _readiness()
        self.attempts = list(attempts or [])
        self.calls: list[str] = []

    def readiness(self, db, **kwargs):
        self.calls.append("readiness")
        return dict(self.readiness_payload)

    def recent(self, db, **kwargs):
        self.calls.append("recent")
        return {
            "provider": kwargs.get("provider", "kis"),
            "market": kwargs.get("market", "KR"),
            "count": len(self.attempts),
            "items": self.attempts,
            "safety": {"read_only": True},
        }

    def run_once(self, db, request):
        raise AssertionError("operations status must not run guarded live auto buy")

    def sync_attempt(self, db, attempt_id):
        raise AssertionError("operations status must not sync attempts")


class FakeRiskService:
    def __init__(self, *, payload=None):
        self.payload = payload or {
            "active_profile": "safe",
            "new_entries_allowed": False,
            "sizing_multiplier": 1.0,
            "target_progress_pct": 0.0,
            "daily_loss_limit_hit": False,
            "monthly_loss_limit_hit": False,
        }
        self.calls = 0

    def risk_state(self, db, **kwargs):
        self.calls += 1
        return dict(self.payload)


@pytest.fixture()
def route_client(db_session):
    dry = FakeDryRunService()
    live = FakeLiveAutoBuyService()
    risk = FakeRiskService()
    service = StrategyAutoBuyOperationsService(
        dry_run_service=dry,
        live_auto_buy_service=live,
        target_risk_service=risk,
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_strategy_auto_buy_operations_service] = (
        lambda: service
    )
    try:
        yield TestClient(app), dry, live, risk
    finally:
        app.dependency_overrides.clear()


def test_operations_status_route_is_read_only_and_reports_no_dry_run(route_client):
    client, dry, live, risk = route_client

    response = client.get("/strategy/auto-buy/operations/status")

    assert response.status_code == 200
    body = response.json()
    assert body["auto_buy_stage"] == "no_dry_run"
    assert body["next_operator_action"] == "run_dry_run"
    assert body["dry_run"]["recent_found"] is False
    assert body["live_readiness"]["primary_block_reason"] == (
        "strategy_live_auto_buy_disabled"
    )
    assert body["safety"] == {
        "read_only": True,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
    }
    assert dry.calls == ["recent", "summary"]
    assert live.calls == ["readiness", "recent"]
    assert risk.calls == 1


def test_operations_status_reports_ready_for_operator_confirm(db_session):
    dry = FakeDryRunService(items=[_dry_run(action="would_buy")])
    live = FakeLiveAutoBuyService(readiness=_readiness(ready=True, enabled=True))
    risk = FakeRiskService(
        payload={
            "active_profile": "safe",
            "new_entries_allowed": True,
            "sizing_multiplier": 1.0,
            "target_progress_pct": 12.5,
            "daily_loss_limit_hit": False,
            "monthly_loss_limit_hit": False,
        }
    )
    service = StrategyAutoBuyOperationsService(
        dry_run_service=dry,
        live_auto_buy_service=live,
        target_risk_service=risk,
    )

    body = service.status(db_session)

    assert body["auto_buy_stage"] == "ready_for_operator_confirm"
    assert body["next_operator_action"] == "confirm_guarded_live_buy"
    assert body["dry_run"]["latest_action"] == "would_buy"
    assert body["live_readiness"]["ready"] is True
    assert body["risk"]["entry_allowed"] is True
    assert body["safety"]["validation_called"] is False
    assert body["safety"]["broker_submit_called"] is False


def test_operations_status_prioritizes_sync_required(db_session):
    dry = FakeDryRunService(items=[_dry_run(action="would_buy")])
    live = FakeLiveAutoBuyService(
        readiness=_readiness(ready=True, enabled=True),
        attempts=[
            {
                "attempt_id": 1,
                "status": "sync_required",
                "action": "sync_required",
                "symbol": "005930",
                "created_at": _now(),
            }
        ],
    )
    service = StrategyAutoBuyOperationsService(
        dry_run_service=dry,
        live_auto_buy_service=live,
        target_risk_service=FakeRiskService(
            payload={
                "active_profile": "safe",
                "new_entries_allowed": True,
                "daily_loss_limit_hit": False,
                "monthly_loss_limit_hit": False,
            }
        ),
    )

    body = service.status(db_session)

    assert body["auto_buy_stage"] == "sync_required"
    assert body["next_operator_action"] == "sync_latest_attempt"
    assert body["live_attempts"]["sync_required_count"] == 1
    assert body["live_attempts"]["submitted_count_today"] == 1


def test_operations_status_reports_dry_run_block_reason(db_session):
    dry = FakeDryRunService(items=[_dry_run(action="blocked")])
    service = StrategyAutoBuyOperationsService(
        dry_run_service=dry,
        live_auto_buy_service=FakeLiveAutoBuyService(
            readiness=_readiness(
                ready=False,
                enabled=True,
                primary_block_reason="target_risk_rejected",
            )
        ),
        target_risk_service=FakeRiskService(),
    )

    body = service.status(db_session)

    assert body["auto_buy_stage"] == "dry_run_blocked"
    assert body["next_operator_action"] == "review_block_reason"
    assert body["dry_run"]["blocked_count_today"] == 1
    assert body["safety"]["setting_changed"] is False
    assert body["safety"]["scheduler_changed"] is False


def _readiness(
    *,
    ready: bool = False,
    enabled: bool = False,
    primary_block_reason: str = "strategy_live_auto_buy_disabled",
):
    return {
        "enabled": enabled,
        "ready": ready,
        "provider": "kis",
        "market": "KR",
        "active_profile": "safe",
        "dry_run": False,
        "kill_switch": False,
        "kis_real_order_enabled": ready,
        "scheduler_live_enabled": False,
        "recent_dry_run_required": True,
        "recent_dry_run_found": ready,
        "orders_remaining_today": 1 if ready else 0,
        "primary_block_reason": None if ready else primary_block_reason,
        "checks": [
            {
                "key": "target_aware_risk",
                "ok": ready,
                "message": "target risk checked",
            }
        ],
        "safety": {"read_only": True},
    }


def _dry_run(*, action: str):
    return {
        "provider": "kis",
        "market": "KR",
        "action": action,
        "active_profile": "safe",
        "selected_symbol": "005930",
        "final_score": 80,
        "created_at": _now(),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
