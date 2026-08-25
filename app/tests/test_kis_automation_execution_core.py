from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, PositionLifecycle
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.runtime_setting_service import RuntimeSettingService


NOW = datetime(2026, 8, 24, 3, 30, tzinfo=UTC)


class FakeKisClient:
    def __init__(self, *, positions=None, possible_age_seconds=0):
        self.positions = list(positions or [])
        self.possible_age_seconds = possible_age_seconds
        self.price_calls = 0
        self.possible_order_calls = 0

    def list_positions(self):
        return list(self.positions)

    def list_open_orders(self):
        return []

    def get_domestic_stock_price(self, symbol):
        self.price_calls += 1
        return {"current_price": 10_000, "symbol": symbol}

    def get_domestic_possible_order(self, **kwargs):
        self.possible_order_calls += 1
        queried_at = NOW - timedelta(seconds=self.possible_age_seconds)
        return {
            "raw_status": "ok",
            "symbol": kwargs["symbol"],
            "orderable_cash": 1_000_000,
            "orderable_quantity": 100,
            "queried_at": queried_at.isoformat(),
        }


def _order(
    db,
    *,
    side,
    status=InternalOrderStatus.REQUESTED.value,
    stop_loss_pct=None,
    take_profit_pct=None,
):
    RuntimeSettingService().update_settings(db, {'automation_mode': 'live'})
    payload = {
        "source": "strategy_live_auto_buy" if side == "buy" else "strategy_live_auto_exit",
        "source_type": "profile_aware_guarded_live_auto_buy" if side == "buy" else "guarded_profile_exit",
        "automation_profile": True,
        "automation_profile_key": "aut_test_profile",
    }
    if stop_loss_pct is not None:
        payload["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None:
        payload["take_profit_pct"] = take_profit_pct
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side=side,
        order_type="market",
        qty=3,
        requested_qty=3,
        remaining_qty=3,
        notional=30_000,
        internal_status=status,
        request_payload=json.dumps(payload),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _enable_profile_scheduler(db):
    RuntimeSettingService().update_settings(
        db,
        {
            'automation_mode': 'live',
            "automation_profile_scheduler_enabled": True,
            "strategy_auto_buy_scheduler_enabled": True,
            "strategy_live_auto_buy_scheduler_enabled": True,
            "auto_buy_live_phase1_enabled": True,
            "auto_buy_live_phase1_allow_real_orders": True,
        },
    )


def test_buy_filled_promotes_lifecycle_and_keeps_profile_scheduler_flags(db_session):
    _enable_profile_scheduler(db_session)
    client = FakeKisClient()
    order = _order(db_session, side="buy", stop_loss_pct=3.0, take_profit_pct=7.0)
    calls = []

    core = KisAutomationExecutionCore(client, runtime_settings=RuntimeSettingService())
    result = core.submit_market_buy(
        db_session,
        order=order,
        symbol="005930",
        qty=3,
        expected_price=10_000,
        max_positions=1,
        max_order_notional_krw=1_000_000,
        submitter=lambda: (
            calls.append(True)
            or {
                "order_id": "KIS-BUY-1",
                "status": "filled",
                "filled_qty": 3,
                "avg_fill_price": 10_000,
            }
        ),
        now=NOW,
    )

    lifecycle = db_session.query(PositionLifecycle).one()
    settings = RuntimeSettingService().get_settings_read_only(db_session)
    assert result["status"] == "filled"
    assert calls == [True]
    assert lifecycle.status == "open"
    assert lifecycle.entry_order_id == order.id
    assert lifecycle.stop_loss_threshold_pct == 3.0
    assert lifecycle.take_profit_threshold_pct == 7.0
    assert settings["automation_profile_scheduler_enabled"] is True
    assert settings["strategy_auto_buy_scheduler_enabled"] is True

    from app.services.kis_position_lifecycle_service import KisPositionLifecycleService

    KisPositionLifecycleService(client).run_management_once(
        db_session,
        execute=False,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings_read_only(db_session)
    assert settings["automation_profile_scheduler_enabled"] is True
    assert settings["strategy_auto_buy_scheduler_enabled"] is True


def test_stale_possible_order_blocks_without_submit(db_session):
    client = FakeKisClient(possible_age_seconds=11)
    order = _order(db_session, side="buy")
    calls = []

    result = KisAutomationExecutionCore(client).submit_market_buy(
        db_session,
        order=order,
        symbol="005930",
        qty=3,
        submitter=lambda: calls.append(True) or {"order_id": "never"},
        now=NOW,
    )

    assert result["reason"] == "possible_order_snapshot_stale"
    assert calls == []


def test_profile_max_price_jit_guard_blocks_current_price_spike_without_submit(
    db_session,
):
    client = FakeKisClient()

    def current_price(symbol):
        return {'current_price': 501_000, 'symbol': symbol}

    client.get_domestic_stock_price = current_price
    order = _order(db_session, side='buy')
    calls = []

    result = KisAutomationExecutionCore(client).submit_market_buy(
        db_session,
        order=order,
        symbol='005930',
        qty=1,
        expected_price=499_000,
        min_price_krw=5_000,
        max_price_krw=500_000,
        submitter=lambda: calls.append(True) or {'order_id': 'never'},
        now=NOW,
    )

    assert result['reason'] == 'profile_max_price_exceeded'
    assert result['guard']['current_price'] == 501_000
    assert calls == []
    assert client.possible_order_calls == 0


def test_duplicate_open_position_blocks_without_submit(db_session):
    client = FakeKisClient(positions=[{"symbol": "005930", "qty": 1}])
    order = _order(db_session, side="buy")
    calls = []

    result = KisAutomationExecutionCore(client).submit_market_buy(
        db_session,
        order=order,
        symbol="005930",
        qty=1,
        submitter=lambda: calls.append(True) or {"order_id": "never"},
        now=NOW,
    )

    assert result["reason"] == "max_positions_reached"
    assert calls == []


def test_duplicate_database_order_blocks_without_submit(db_session):
    client = FakeKisClient()
    previous = _order(db_session, side="buy", status=InternalOrderStatus.SUBMITTED.value)
    previous.broker = "kis"
    db_session.commit()
    order = _order(db_session, side="buy")
    calls = []

    result = KisAutomationExecutionCore(client).submit_market_buy(
        db_session,
        order=order,
        symbol="005930",
        qty=1,
        submitter=lambda: calls.append(True) or {"order_id": "never"},
        now=NOW,
    )

    assert result["reason"] == "duplicate_open_order"
    assert calls == []
    assert order.internal_status == InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value


def test_filled_sell_closes_lifecycle_after_position_reconciliation(db_session):
    _enable_profile_scheduler(db_session)
    client = FakeKisClient(positions=[{"symbol": "005930", "qty": 3}])
    buy = _order(db_session, side="buy", status=InternalOrderStatus.FILLED.value)
    buy.filled_qty = 3
    buy.avg_fill_price = 10_000
    buy.filled_avg_price = 10_000
    buy.remaining_qty = 0
    db_session.commit()
    from app.services.kis_position_lifecycle_service import KisPositionLifecycleService

    lifecycle_result = KisPositionLifecycleService(client).sync_filled_buy(db_session, buy, now=NOW)
    assert lifecycle_result["created"] is True
    sell = _order(db_session, side="sell")

    def submit_sell():
        client.positions = []
        return {
            "order_id": "KIS-SELL-1",
            "status": "filled",
            "filled_qty": 3,
            "avg_fill_price": 10_500,
        }

    result = KisAutomationExecutionCore(client).submit_market_sell(
        db_session,
        order=sell,
        symbol="005930",
        qty=3,
        submitter=submit_sell,
        now=NOW,
    )

    lifecycle = db_session.query(PositionLifecycle).one()
    db_session.refresh(lifecycle)
    assert result["status"] == "filled"
    assert lifecycle.status == "closed"
    assert lifecycle.exit_order_id == sell.id
    settings = RuntimeSettingService().get_settings_read_only(db_session)
    assert settings["automation_profile_scheduler_enabled"] is True
