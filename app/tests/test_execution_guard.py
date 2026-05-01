from datetime import datetime, timedelta, timezone

from app.db.models import OrderLog
from app.services.execution_guard_service import ExecutionGuardService


class DummyOrderSync:
    def sync_open_orders_for_symbol(self, db, symbol, **kwargs):
        return []

    def has_conflicting_open_order(self, db, symbol, **kwargs):
        return False


def _settings(**overrides):
    base = {
        "bot_enabled": True,
        "kill_switch": False,
        "global_daily_entry_limit": 1,
        "per_symbol_daily_entry_limit": 1,
        "near_close_block_minutes": 15,
        "same_direction_cooldown_minutes": 0,
    }
    base.update(overrides)
    return base


def test_near_close_blocks_new_entry_buy(monkeypatch, db_session):
    svc = ExecutionGuardService()
    svc.order_sync = DummyOrderSync()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: _settings())
    monkeypatch.setattr(svc, "_is_near_close_blocked", lambda mins: True)

    result = svc.action_check(db_session, "AAPL", "buy", intent="entry")

    assert result["allowed"] is False
    assert result["reason"] == "near_market_close_entry_block"


def test_exit_allowed_even_when_entry_caps_exhausted(monkeypatch, db_session):
    svc = ExecutionGuardService()
    svc.order_sync = DummyOrderSync()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: _settings(global_daily_entry_limit=0, per_symbol_daily_entry_limit=0))
    monkeypatch.setattr(svc, "_daily_entry_count", lambda db, symbol=None: 99)

    precheck = svc.precheck(db_session, "AAPL", enforce_entry_limits=True, intent="exit")
    action = svc.action_check(db_session, "AAPL", "sell", intent="exit")

    assert precheck["allowed"] is True
    assert action["allowed"] is True


def test_entry_caps_still_apply_for_entry_precheck(monkeypatch, db_session):
    svc = ExecutionGuardService()
    svc.order_sync = DummyOrderSync()
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: _settings(global_daily_entry_limit=1))
    monkeypatch.setattr(svc, "_daily_entry_count", lambda db, symbol=None: 1)

    blocked = svc.precheck(db_session, "MSFT", enforce_entry_limits=True, intent="entry")

    assert blocked["allowed"] is False
    assert blocked["reason"] == "global_daily_entry_limit_reached"


def test_entry_count_ignores_kis_orders_with_same_symbol(monkeypatch, db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        OrderLog(
            broker="kis",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=1,
            internal_status="FILLED",
            broker_status="filled",
            created_at=now,
        )
    )
    db_session.commit()
    svc = ExecutionGuardService()
    monkeypatch.setattr(
        svc,
        "_day_bounds_utc",
        lambda: (now - timedelta(hours=1), now + timedelta(hours=1)),
    )

    assert svc._daily_entry_count(db_session, symbol="AAPL") == 0
