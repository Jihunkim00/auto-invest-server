from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import OrderLog
from app.services.automation_kill_rule_service import AutomationKillRuleService


def _settings(**overrides):
    values = {
        "dry_run": True,
        "kill_switch": False,
        "_app_kis_real_order_enabled": False,
        "_daily_action_limit_exhausted": False,
        "automation_soak_max_unmatched_order_count": 0,
        "automation_soak_max_pending_sync_count": 0,
        "automation_soak_max_stale_order_count": 0,
        "automation_soak_max_consecutive_failures": 2,
        "automation_soak_consecutive_failure_count": 0,
        "automation_soak_max_daily_loss_pct": 0.03,
        "automation_soak_max_daily_loss_amount": 50000,
    }
    values.update(overrides)
    return values


def _triggered_ids(rules):
    return {rule["rule_id"] for rule in rules if rule["triggered"]}


def test_kill_rules_detect_order_sync_stale_duplicate_and_pnl(db_session):
    now = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
    old = now - timedelta(days=2)
    db_session.add_all(
        [
            OrderLog(
                broker="kis",
                market="KR",
                symbol="005930",
                side="buy",
                order_type="market",
                internal_status="SYNC_FAILED",
                broker_status="pending_sync",
                created_at=old,
                updated_at=old,
                submitted_at=old,
            ),
            OrderLog(
                broker="kis",
                market="KR",
                symbol="005930",
                side="buy",
                order_type="market",
                internal_status="ACCEPTED",
                created_at=old,
                updated_at=old,
                submitted_at=old,
            ),
        ]
    )
    db_session.commit()

    rules = AutomationKillRuleService().evaluate(
        db_session,
        settings=_settings(),
        watchdog_status={"sync_health": "healthy", "blocking_reasons": []},
        automation_mode_status={"automation_mode": "dry_run_auto"},
        production_readiness={"overall_status": "ready"},
        daily_ops_summary={
            "pnl_summary": {
                "realized_pl_pct": -0.04,
                "realized_pl": -60000,
            }
        },
        now=now,
    )

    triggered = _triggered_ids(rules)
    assert "pending_sync_order_present" in triggered
    assert "stale_order_present" in triggered
    assert "duplicate_open_order_present" in triggered
    assert "daily_loss_limit_breached" in triggered


def test_kill_rules_detect_unexpected_execution_flags(db_session):
    rules = AutomationKillRuleService().evaluate(
        db_session,
        settings=_settings(),
        watchdog_status={"sync_health": "healthy", "blocking_reasons": []},
        automation_mode_status={"automation_mode": "dry_run_auto"},
        production_readiness={"overall_status": "ready"},
        orchestrator_result={
            "result_status": "blocked",
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_cancel_called": True,
        },
        now=datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
    )

    triggered = _triggered_ids(rules)
    assert "unexpected_broker_submit_flag" in triggered
    assert "unexpected_manual_submit_flag" in triggered
    assert "unexpected_order_cancel_flag" in triggered


def test_dry_run_mode_does_not_treat_automation_off_as_kill_rule(db_session):
    rules = AutomationKillRuleService().evaluate(
        db_session,
        settings=_settings(),
        watchdog_status={"sync_health": "healthy", "blocking_reasons": []},
        automation_mode_status={
            "automation_mode": "off",
            "can_attempt_phase1_live": False,
            "can_submit_live_order": False,
        },
        production_readiness={"overall_status": "ready"},
        soak_mode="dry_run_monitoring",
        now=datetime(2026, 7, 12, 1, 0, tzinfo=UTC),
    )

    assert "automation_mode_not_ready" not in _triggered_ids(rules)
