from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, TradeRunLog
from app.main import app
from app.services.kis_scheduler_guarded_sell_service import (
    MODE,
    KisSchedulerGuardedSellService,
)
from app.tests.test_kis_limited_auto_sell import _FakeValidationResult


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_real_order_enabled": True,
        "kis_scheduler_enabled": True,
        "kis_scheduler_dry_run": False,
        "kis_scheduler_allow_real_orders": True,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(self, *, settings=None):
        self.settings = settings or _settings()


class _RuntimeSettings:
    def __init__(self, **overrides):
        self.payload = _runtime(**overrides)

    def get_settings(self, db):
        return dict(self.payload)


class _FakeLimitedSellService:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.kwargs = []

    def run_once(self, db, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        return dict(self.result)


class _OrderCreatingLimitedSellService(_FakeLimitedSellService):
    def run_once(self, db, **kwargs):
        self.calls += 1
        self.kwargs.append(kwargs)
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.SUBMITTED.value,
            broker_order_id="KIS-SCHED-1",
            kis_odno="KIS-SCHED-1",
            submitted_at=datetime.now(UTC).replace(tzinfo=None),
            request_payload=json.dumps({"mode": "kis_limited_auto_stop_loss_run"}),
            response_payload=json.dumps(
                {
                    "mode": "kis_limited_auto_stop_loss_run",
                    "source": "kis_limited_auto_stop_loss",
                    "source_type": "guarded_stop_loss_auto_sell",
                    "real_order_submitted": True,
                }
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        result = dict(self.result)
        result["order_id"] = row.id
        result["order_log_id"] = row.id
        return result


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_default_endpoint_blocks_without_order_submit(client, db_session):
    response = client.post("/kis/scheduler/run-guarded-sell-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == MODE
    assert body["sell_only"] is True
    assert body["buy_execution_allowed"] is False
    assert body["result"] == "blocked"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["primary_block_reason"] in {
        "scheduler_real_orders_disabled",
        "scheduler_sell_disabled",
    }
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"dry_run": True}, "runtime_dry_run_true"),
        ({"kill_switch": True}, "kill_switch_enabled"),
        ({"kis_scheduler_allow_real_orders": False}, "scheduler_real_orders_disabled"),
        ({"kis_scheduler_sell_enabled": False}, "scheduler_sell_disabled"),
        ({}, "kis_real_order_disabled"),
        ({"kis_live_auto_sell_enabled": False}, "kis_live_auto_sell_disabled"),
    ],
)
def test_scheduler_runtime_gates_block_before_limited_sell(
    db_session,
    overrides,
    reason,
):
    settings = _settings(kis_real_order_enabled=(reason != "kis_real_order_disabled"))
    runtime_overrides = overrides if reason != "kis_real_order_disabled" else {}
    limited = _FakeLimitedSellService(_submitted_sell())
    service = _service(
        settings=settings,
        runtime=_RuntimeSettings(**runtime_overrides),
        limited=limited,
    )

    result = service.run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert result["real_order_submitted"] is False
    assert limited.calls == 0
    assert db_session.query(OrderLog).count() == 0


def test_no_sell_candidate_blocks_through_limited_auto_sell_service(db_session):
    limited = _FakeLimitedSellService(
        _blocked_sell("no_exit_candidate", block_reasons=["no_exit_candidate"])
    )

    result = _service(limited=limited).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert limited.calls == 1
    assert result["result"] == "blocked"
    assert result["reason"] == "no_exit_candidate"
    assert "no_exit_candidate" in result["block_reasons"]
    assert result["buy_result"]["skipped_for_sell_only_scheduler"] is True
    assert result["buy_result"]["validation_called"] is False


@pytest.mark.parametrize(
    "reason",
    ["duplicate_open_sell_order", "daily_auto_sell_limit_reached"],
)
def test_limited_sell_blocks_are_reflected(db_session, reason):
    limited = _FakeLimitedSellService(_blocked_sell(reason, block_reasons=[reason]))

    result = _service(limited=limited).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert limited.calls == 1
    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False


def test_all_scheduler_gates_true_calls_limited_auto_sell_guarded_path(db_session):
    limited = _FakeLimitedSellService(_submitted_sell())

    result = _service(limited=limited).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert limited.calls == 1
    assert "now" in limited.kwargs[0]
    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["sell_result"]["source_type"] == "guarded_stop_loss_auto_sell"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is True
    assert result["order_id"] == 123
    assert result["broker_order_id"] == "BRK123"
    assert result["kis_odno"] == "KIS123"
    assert result["safety"]["existing_limited_auto_sell_path_reused"] is True
    assert result["safety"]["limited_auto_buy_not_called_in_submit_mode"] is True


def test_scheduler_service_does_not_call_buy_module_in_submit_capable_mode(db_session):
    result = _service(limited=_FakeLimitedSellService(_submitted_sell())).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert result["buy_execution_allowed"] is False
    assert result["buy_result"]["reason"] == "buy_scheduler_execution_disabled"
    assert result["safety"]["scheduler_buy_execution_blocked"] is True


def test_blocked_scheduler_attempt_creates_no_order_log(db_session):
    result = _service(
        runtime=_RuntimeSettings(kis_scheduler_sell_enabled=False),
        limited=_FakeLimitedSellService(_submitted_sell()),
    ).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert result["result"] == "blocked"
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_submitted_attempt_uses_order_created_by_limited_sell_path_only(db_session):
    limited = _OrderCreatingLimitedSellService(_submitted_sell(order_id=None))

    result = _service(limited=limited).run_once(
        db_session,
        slot_label="position_management",
        trigger_source="scheduler",
    )

    assert limited.calls == 1
    assert result["result"] == "submitted"
    assert db_session.query(OrderLog).count() == 1
    order = db_session.query(OrderLog).one()
    assert result["order_id"] == order.id
    assert order.symbol == "005930"
    assert order.side == "sell"
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_scheduler_guarded_sell_service_has_no_direct_order_submission_calls():
    source = inspect.getsource(KisSchedulerGuardedSellService)

    for forbidden in [
        "submit_order",
        "submit_domestic_cash_order",
        "submit_market_buy",
        "submit_market_sell",
        "submit_manual",
        "self.client.submit",
        "self.broker.submit",
    ]:
        assert forbidden not in source


def test_guarded_sell_preserves_account_state_metadata(db_session):
    # limited service returns state metadata and guarded sell should preserve it
    state_meta = {
        "source": "cache_after_rate_limit",
        "cache_age_seconds": 1.2,
        "rate_limited": True,
        "warnings": ["kis_rate_limited"],
    }
    limited = _FakeLimitedSellService({
        "status": "ok",
        "result": "blocked",
        "reason": "no_exit_candidate",
        "real_order_submitted": False,
        "state_source": "cache_after_rate_limit",
        "state_meta": state_meta,
    })

    result = _service(limited=limited).run_once(db_session, slot_label="position_management", trigger_source="scheduler")
    assert limited.calls == 1
    sell_result = result.get("sell_result") or {}
    assert sell_result.get("state_source") == "cache_after_rate_limit"
    assert sell_result.get("state_meta") == state_meta


def test_guarded_sell_reconciles_limited_auto_sell_with_existing_filled_order(monkeypatch, db_session):
    # Monkeypatch manual submit to create OrderLog during submit and return the id
    def fake_submit(self, db, request, *, now=None):
        row2 = OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.FILLED.value,
            broker_order_id="SCHED-FILL",
            kis_odno="SCHED-FILL",
            submitted_at=datetime.now(UTC).replace(tzinfo=None),
            request_payload=json.dumps({"mode": "manual_live"}),
            response_payload=json.dumps({"mode": "manual_live", "real_order_submitted": True}),
        )
        db.add(row2)
        db.commit()
        db.refresh(row2)
        return 200, {"order_id": row2.id, "order_log_id": row2.id, "broker_order_id": row2.broker_order_id, "kis_odno": row2.kis_odno}

    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit,
    )
    # Ensure validation passes
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda self, request, *, now=None: _FakeValidationResult(validated=True),
    )

    # Ensure market session allows sells (open market)
    from app.tests.test_kis_limited_auto_sell import _OpenSessionService
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _OpenSessionService().get_session_status(market, **kwargs),
    )

    # Use the real KisLimitedAutoSellService (with a client that provides positions)
    from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
    from app.tests.test_kis_limited_auto_sell import _FakeClient as LimitedFakeClient, _enable_runtime

    limited_real = KisLimitedAutoSellService(LimitedFakeClient(), runtime_settings=_RuntimeSettings(), session_service=None, allow_scheduler_guarded_sell=True)
    service = _service(limited=limited_real)
    _enable_runtime(db_session, kis_limited_auto_sell_max_orders_per_day=2)
    result = service.run_once(db_session, slot_label="position_management", trigger_source="scheduler")
    assert result["result"] != "blocked"
    assert result["action"] == "sell"
    created = db_session.query(OrderLog).order_by(OrderLog.id.desc()).first()
    assert result["order_id"] == created.id
    assert result["summary"]["order_id"] == created.id
    assert result.get("kis_odno") == created.kis_odno
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["reason"] != "manual_submit_blocked"


def test_guarded_sell_rate_limit_reason_propagates(db_session):
    # limited service indicates rate limit; guarded sell should report kis_rate_limited
    limited = _FakeLimitedSellService({
        "status": "ok",
        "result": "blocked",
        "reason": "kis_rate_limited",
        "block_reasons": ["kis_rate_limited"],
        "real_order_submitted": False,
    })

    result = _service(limited=limited).run_once(db_session, slot_label="position_management", trigger_source="scheduler")
    assert limited.calls == 1
    assert result["result"] == "blocked"
    assert "kis_rate_limited" in result.get("block_reasons", []) or result.get("reason") == "kis_rate_limited"


def _service(*, settings=None, runtime=None, limited=None):
    return KisSchedulerGuardedSellService(
        _FakeClient(settings=settings),
        runtime_settings=runtime or _RuntimeSettings(),
        limited_auto_sell_service=limited or _FakeLimitedSellService(_blocked_sell()),
    )


def _runtime(**overrides):
    values = {
        "scheduler_enabled": True,
        "dry_run": False,
        "kill_switch": False,
        "kis_live_auto_sell_enabled": True,
        "kis_live_auto_buy_enabled": True,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_stop_loss_enabled": True,
        "kis_limited_auto_take_profit_enabled": False,
        "kis_limited_auto_sell_max_orders_per_day": 1,
        "kis_scheduler_enabled": True,
        "kis_scheduler_dry_run": False,
        "kis_scheduler_configured_allow_real_orders": True,
        "kis_scheduler_allow_real_orders": True,
        "kis_scheduler_sell_enabled": True,
        "kis_scheduler_allow_limited_auto_buy": False,
        "kis_scheduler_allow_limited_auto_sell": False,
    }
    values.update(overrides)
    return values


def _blocked_sell(reason="no_exit_candidate", *, block_reasons=None):
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_stop_loss_run",
        "source": "kis_limited_auto_stop_loss",
        "source_type": "guarded_stop_loss_auto_sell",
        "result": "blocked",
        "action": "hold",
        "reason": reason,
        "block_reasons": block_reasons or [reason],
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "duplicate_order_check": {"duplicate_open_sell_order": reason == "duplicate_open_sell_order"},
        "market_session": {"is_market_open": True},
        "sell_session_allowed": True,
    }


def _submitted_sell(order_id=123):
    return {
        "status": "ok",
        "provider": "kis",
        "market": "KR",
        "mode": "kis_limited_auto_stop_loss_run",
        "source": "kis_limited_auto_stop_loss",
        "source_type": "guarded_stop_loss_auto_sell",
        "result": "submitted",
        "action": "sell",
        "reason": "stop_loss_auto_sell_submitted",
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "quantity": 1,
        "trigger": "stop_loss",
        "real_order_submitted": True,
        "broker_submit_called": True,
        "manual_submit_called": True,
        "order_id": order_id,
        "order_log_id": order_id,
        "broker_order_id": "BRK123",
        "kis_odno": "KIS123",
        "duplicate_order_check": {"duplicate_open_sell_order": False},
        "market_session": {"is_market_open": True},
        "sell_session_allowed": True,
    }
