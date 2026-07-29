from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_limited_auto_buy_service import (
    GUARDED_SOURCE_TYPE,
    PREFLIGHT_MODE,
    RUN_MODE,
    STATUS_MODE,
    SOURCE,
    SOURCE_TYPE,
    KisLimitedAutoBuyService,
)


class _FakeClient:
    def __init__(
        self,
        *,
        settings=None,
        balance=None,
        positions=None,
        open_orders=None,
        current_price=52_000,
    ):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
        )
        self.balance = balance if balance is not None else _balance()
        self.positions = positions if positions is not None else []
        self.open_orders = open_orders if open_orders is not None else []
        self.current_price = current_price
        self.submit_calls = []

    def get_account_balance(self):
        return self.balance

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders

    def get_domestic_stock_price(self, symbol):
        return {"symbol": symbol, "current_price": self.current_price}

    def build_domestic_order_payload(self, **kwargs):
        return {"tr_id": "TTTC0802U", **kwargs}

    def submit_domestic_cash_order(self, **kwargs):
        self.submit_calls.append(kwargs)
        return {"rt_cd": "0", "output": {"ODNO": "KIS123"}}

    def inquire_daily_order_executions(self, **kwargs):
        return {"rt_cd": "0", "output1": [], "output2": []}


class _FakeShadowService:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else _shadow_payload()
        self.calls = 0

    def run_once(self, db_session, **kwargs):
        self.calls += 1
        return self.payload


class _OpenSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_holiday": False,
            "closure_reason": None,
            "effective_close": "15:30",
            "no_new_entry_after": "14:50",
        }


class _ClosedSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": False,
            "is_entry_allowed_now": False,
            "is_holiday": False,
            "closure_reason": "closed",
        }


class _FakeValidationResult:
    def __init__(
        self,
        *,
        validated_for_submission=True,
        block_reasons=None,
        symbol="005930",
        qty=1,
    ):
        self.provider = "kis"
        self.market = "KR"
        self.environment = "prod"
        self.dry_run = True
        self.validated_for_submission = validated_for_submission
        self.can_submit_later = validated_for_submission
        self.symbol = symbol
        self.side = "buy"
        self.qty = qty
        self.order_type = "market"
        self.current_price = 52_000
        self.estimated_amount = 52_000
        self.available_cash = 3_000_000
        self.held_qty = None
        self.warnings = []
        self.block_reasons = block_reasons or []
        self.market_session = {
            "market": "KR",
            "is_market_open": True,
            "is_entry_allowed_now": True,
        }
        self.order_preview = {}
        self.source_metadata = None
        self.primary_block_reason = self.block_reasons[0] if self.block_reasons else None
        self.message = None
        self.detail = None

    def to_dict(self):
        return {
            "provider": self.provider,
            "market": self.market,
            "environment": self.environment,
            "dry_run": self.dry_run,
            "validated_for_submission": self.validated_for_submission,
            "can_submit_later": self.can_submit_later,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "current_price": self.current_price,
            "estimated_amount": self.estimated_amount,
            "available_cash": self.available_cash,
            "block_reasons": self.block_reasons,
            "market_session": self.market_session,
            "primary_block_reason": self.primary_block_reason,
        }


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _balance(**overrides):
    payload = {
        "provider": "kis",
        "market": "KR",
        "currency": "KRW",
        "cash": 3_000_000,
        "total_asset_value": 10_000_000,
        "unrealized_pl": 0,
    }
    payload.update(overrides)
    return payload


def test_status_default_shows_auto_buy_disabled_and_no_submit_allowed(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis._client", lambda db: _FakeClient())

    response = client.get("/kis/limited-auto-buy/status")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == STATUS_MODE
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["live_auto_buy_enabled"] is False
    assert body["limited_auto_buy_enabled"] is False
    assert body["buy_readiness_enabled"] is True
    assert body["real_order_submit_allowed"] is False
    assert body["auto_order_ready"] is False
    assert body["safety"]["auto_buy_execution_enabled"] is False
    assert body["scheduler_real_orders_enabled"] is False
    assert body["supported_triggers"]["buy"] == "readiness_only"
    assert "auto_buy_execution_disabled" in body["block_reasons"]
    assert "limited_auto_buy_disabled" in body["block_reasons"]
    assert db_session.query(OrderLog).count() == 0


def test_limited_auto_buy_runtime_defaults_are_safe(db_session):
    from app.services.runtime_setting_service import RuntimeSettingService

    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_readiness_enabled"] is True
    assert settings["kis_limited_auto_buy_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_buy_max_notional_pct"] == pytest.approx(0.03)
    assert settings["kis_limited_auto_buy_min_cash_buffer_krw"] == 0
    assert settings["kis_limited_auto_buy_requires_existing_sell_guards"] is True
    assert settings["dry_run"] is True
    assert settings["kis_scheduler_allow_real_orders"] is False


def test_preflight_never_submits_validates_or_creates_order_log(
    monkeypatch,
    db_session,
):
    _enable_runtime(db_session)
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("KIS cash order path must not run"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("KIS order path must not run"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual order path must not run"),
    )
    monkeypatch.setattr(
        "app.services.kis_order_validation_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("validation must not run"),
    )

    result = _service().preflight_once(db_session)

    assert result["mode"] == PREFLIGHT_MODE
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert result["validation_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_preflight_good_candidate_returns_buy_ready_readiness_only(db_session):
    _enable_runtime(db_session)

    result = _service().preflight_once(db_session)

    assert result["mode"] == PREFLIGHT_MODE
    assert result["result"] == "ready"
    assert result["action"] == "buy_ready"
    assert result["primary_block_reason"] == "auto_buy_execution_disabled"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["review_token"]
    assert result["review"]["qty"] == 1
    assert result["review"]["estimated_notional"] == pytest.approx(52_000)
    candidate = result["final_candidate"]
    assert candidate["status"] == "BUY READY"
    assert candidate["symbol"] == "005930"
    assert candidate["company_name"] == "Samsung Electronics"
    assert candidate["final_buy_score"] == pytest.approx(82.5)
    assert candidate["required_buy_score"] == pytest.approx(75)
    assert candidate["cash_available"] == pytest.approx(3_000_000)
    assert candidate["trade_allowed"] is False
    assert candidate["buy_readiness_only"] is True
    assert candidate["buy_actionable"] is False
    assert db_session.query(OrderLog).count() == 0


def test_run_once_good_candidate_blocks_with_auto_buy_execution_disabled(db_session):
    _enable_runtime(db_session)

    result = _service().run_once(db_session)

    assert result["mode"] == RUN_MODE
    assert result["result"] == "blocked"
    assert result["action"] == "blocked_buy"
    assert result["source_type"] == GUARDED_SOURCE_TYPE
    assert result["primary_block_reason"] == "auto_buy_execution_disabled"
    assert result["order_id"] is None
    assert result["kis_odno"] is None
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 1
    assert (
        db_session.query(TradeRunLog).filter(TradeRunLog.mode == RUN_MODE).count()
        == 1
    )


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"dry_run": True}, "dry_run_enabled"),
        ({"kill_switch": True}, "kill_switch_enabled"),
        ({"kis_live_auto_buy_enabled": False}, "auto_buy_execution_disabled"),
        ({"kis_limited_auto_buy_enabled": False}, "auto_buy_execution_disabled"),
    ],
)
def test_run_once_runtime_gates_block_before_validation(
    monkeypatch,
    db_session,
    override,
    reason,
):
    values = {
        "dry_run": False,
        "kis_live_auto_buy_enabled": True,
        "kis_limited_auto_buy_enabled": True,
    }
    values.update(override)
    _enable_runtime(db_session, **values)
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("blocked run must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("blocked run must not submit"),
    )

    result = _service().run_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert result["validation_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_run_once_blocks_when_kis_real_order_disabled(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("KIS-real-order blocked run must not validate"),
    )

    result = _service(
        client=_FakeClient(
            settings=SimpleNamespace(
                kis_enabled=True,
                kis_real_order_enabled=False,
                kis_scheduler_allow_real_orders=False,
                kr_scheduler_allow_real_orders=False,
            )
        )
    ).run_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "kis_real_order_disabled"
    assert result["validation_called"] is False
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("candidate_override", "reason"),
    [
        ({"final_buy_score": 60, "final_score": 60}, "score_threshold_not_met"),
        ({"final_sell_score": 80, "final_buy_score": 100, "final_score": 100}, "sell_pressure_too_high"),
        ({"indicator_status": "insufficient_data", "indicator_payload": {}, "indicator_bar_count": 0}, "missing_indicators"),
    ],
)
def test_candidate_score_sell_pressure_and_indicator_blocks(
    db_session,
    candidate_override,
    reason,
):
    _enable_runtime(db_session)
    shadow = _FakeShadowService(_shadow_payload(**candidate_override))

    result = _service(shadow_service=shadow).preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert reason in result["block_reasons"]
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("client_override", "reason"),
    [
        ({"balance": _balance(cash=1000)}, "insufficient_cash"),
        ({"positions": [{"symbol": "005930", "qty": 1}]}, "max_positions_reached"),
        ({"open_orders": [{"symbol": "005930", "side": "buy", "status": "PENDING"}]}, "duplicate_open_buy_order"),
    ],
)
def test_cash_duplicate_position_and_open_order_blocks(
    db_session,
    client_override,
    reason,
):
    _enable_runtime(db_session)

    result = _service(client=_FakeClient(**client_override)).preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == reason
    assert result["broker_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_max_notional_exceeded_blocks(db_session):
    _enable_runtime(db_session, kis_limited_auto_buy_max_notional_pct=0.01)
    shadow = _FakeShadowService(
        _shadow_payload(suggested_notional=500_000, estimated_notional=500_000)
    )

    result = _service(shadow_service=shadow).preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "max_notional_exceeded"
    assert db_session.query(OrderLog).count() == 0


def test_daily_buy_limit_blocks(db_session):
    _enable_runtime(db_session)
    _seed_limited_buy_order(db_session)

    result = _service().preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "daily_auto_buy_limit_reached"
    assert result["candidate_count"] == 0
    assert db_session.query(OrderLog).count() == 1


def test_market_closed_blocks(db_session):
    _enable_runtime(db_session)

    result = _service(session_service=_ClosedSessionService()).preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "market_closed"
    assert result["real_order_submitted"] is False


def test_no_new_entry_after_blocks_entry(db_session):
    _enable_runtime(db_session, kis_limited_auto_buy_no_new_entry_after="14:50")
    now = datetime(2026, 5, 22, 6, 0, tzinfo=UTC)  # 15:00 Asia/Seoul

    result = _service().preflight_once(db_session, now=now)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "no_new_entry_after_blocked"
    assert result["entry_allowed_now"] is False


def test_run_once_requires_operator_token_without_validation_or_submit(
    monkeypatch,
    db_session,
):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("run-once must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("run-once must not submit"),
    )

    result = _service().run_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "operator_review_token_required"
    assert result["validation_called"] is False
    assert result["manual_submit_called"] is False
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_reviewed_execute_success_submits_one_share_and_syncs(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    client = _FakeClient()
    service = _service(client=client)
    preflight = service.preflight_once(db_session)
    validation_calls = []

    def fake_validate(self, request, **kwargs):
        validation_calls.append(request)
        assert request.side == "buy"
        assert request.qty == 1
        assert request.dry_run is True
        assert request.source_metadata["source_type"] == GUARDED_SOURCE_TYPE
        return _FakeValidationResult()

    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        fake_validate,
    )

    result = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )

    assert len(validation_calls) == 1
    assert len(client.submit_calls) == 1
    assert client.submit_calls[0]["qty"] == 1
    assert result["result"] == "submitted"
    assert result["action"] == "buy"
    assert result["source_type"] == "operator_reviewed_limited_auto_buy"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is True
    assert result["validation_called"] is True
    assert result["qty"] == 1
    assert result["kis_odno"] == "KIS123"
    order = db_session.get(OrderLog, result["order_id"])
    assert order is not None
    assert order.internal_status in {
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.FILLED.value,
    }
    assert result["review_token_used"] is True
    runtime = db_session.query(RuntimeSetting).first()
    assert runtime.dry_run is True
    assert runtime.kill_switch is True
    assert runtime.kis_limited_auto_buy_enabled is False


def test_reviewed_execute_blocks_expired_token(db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    service = _service()
    now = datetime(2026, 5, 22, 5, 30, tzinfo=UTC)
    preflight = service.preflight_once(db_session, now=now)

    result = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
        now=now + timedelta(minutes=6),
    )

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "review_token_expired"
    assert result["real_order_submitted"] is False


def test_reviewed_execute_blocks_token_reuse(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    client = _FakeClient()
    service = _service(client=client)
    preflight = service.preflight_once(db_session)
    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        lambda self, request, **kwargs: _FakeValidationResult(qty=request.qty),
    )

    first = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    second = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )

    assert first["result"] == "submitted"
    assert second["result"] == "blocked"
    assert second["primary_block_reason"] == "review_token_already_used"
    assert len(client.submit_calls) == 1


@pytest.mark.parametrize(
    ("candidate_override", "client_mutation", "reason"),
    [
        ({"symbol": "000660"}, None, "review_token_symbol_mismatch"),
        ({"suggested_quantity": 2}, None, "review_token_qty_mismatch"),
        (None, {"current_price": 56_000}, "max_notional_krw_exceeded"),
        (None, {"balance": _balance(total_asset_value=50_000, cash=100_000)}, "max_notional_pct_exceeded"),
        (None, {"balance": _balance(cash=10_000)}, "insufficient_cash"),
        (None, {"positions": [{"symbol": "000660", "qty": 1}]}, "max_positions_reached"),
        (None, {"open_orders": [{"symbol": "005930", "side": "buy", "status": "PENDING"}]}, "duplicate_open_buy_order"),
    ],
)
def test_reviewed_execute_blocks_guard_violations(
    db_session,
    candidate_override,
    client_mutation,
    reason,
):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    client = _FakeClient()
    service = _service(client=client)
    preflight = service.preflight_once(db_session)
    if client_mutation:
        for key, value in client_mutation.items():
            setattr(client, key, value)
    execute_service = (
        _service(
            client=client,
            shadow_service=_FakeShadowService(_shadow_payload(**candidate_override)),
        )
        if candidate_override
        else service
    )

    result = execute_service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )

    assert result["result"] == "blocked"
    assert reason in result["block_reasons"]
    assert result["real_order_submitted"] is False
    assert len(client.submit_calls) == 0


def test_reviewed_execute_blocks_daily_limit(db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    service = _service()
    preflight = service.preflight_once(db_session)
    _seed_limited_buy_order(db_session)

    result = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )

    assert result["result"] == "blocked"
    assert "daily_auto_buy_limit_reached" in result["block_reasons"]


def test_reviewed_execute_blocks_after_1450(db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
        kis_limited_auto_buy_no_new_entry_after="14:50",
    )
    service = _service()
    preflight_time = datetime(2026, 5, 22, 5, 48, tzinfo=UTC)
    preflight = service.preflight_once(db_session, now=preflight_time)

    result = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
        now=preflight_time + timedelta(minutes=3),
    )

    assert result["result"] == "blocked"
    assert "no_new_entry_after_blocked" in result["block_reasons"]


def test_reviewed_execute_blocks_bad_confirmation_and_scheduler_context(db_session):
    _enable_runtime(db_session)
    service = _service()

    bad_confirmation = service.execute_reviewed_once(
        db_session,
        review_token="missing",
        confirm_live=True,
        confirmation="WRONG",
    )
    scheduler = service.execute_reviewed_once(
        db_session,
        review_token="missing",
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
        scheduler_context=True,
    )

    assert bad_confirmation["primary_block_reason"] == "confirmation_mismatch"
    assert scheduler["primary_block_reason"] == "scheduler_context_blocked"
    assert bad_confirmation["real_order_submitted"] is False
    assert scheduler["real_order_submitted"] is False


def test_reviewed_execute_restores_safe_settings_on_exception(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        dry_run=False,
        kill_switch=False,
        kis_live_auto_buy_enabled=True,
        kis_limited_auto_buy_enabled=True,
        kis_limited_auto_buy_max_notional_pct=0.94,
    )
    service = _service()
    preflight = service.preflight_once(db_session)

    monkeypatch.setattr(
        "app.services.kis_limited_auto_buy_service.KisOrderValidationService.validate",
        lambda self, request, **kwargs: _FakeValidationResult(qty=request.qty),
    )
    monkeypatch.setattr(
        service,
        "_submit_reviewed_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = service.execute_reviewed_once(
        db_session,
        review_token=preflight["review_token"],
        confirm_live=True,
        confirmation="TEST3 LIVE BUY 1 SHARE",
    )

    runtime = db_session.query(RuntimeSetting).first()
    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "reviewed_execute_failed"
    assert runtime.dry_run is True
    assert runtime.kill_switch is True
    assert runtime.kis_live_auto_buy_enabled is False


def test_kill_switch_blocks_without_candidate_source(db_session):
    _enable_runtime(db_session, kill_switch=True)
    shadow = _FakeShadowService()

    result = _service(shadow_service=shadow).preflight_once(db_session)

    assert result["result"] == "blocked"
    assert result["primary_block_reason"] == "kill_switch_enabled"
    assert shadow.calls == 0
    assert result["real_order_submitted"] is False


def test_no_direct_broker_or_manual_submit_calls_in_readiness_service():
    text = Path("app/services/kis_limited_auto_buy_service.py").read_text()

    for forbidden in [
        "submit_order",
        "submit_domestic_cash_order",
        "submit_market_buy",
        "submit_market_sell",
        "self.client.submit",
        "self.broker.submit",
    ]:
        assert forbidden not in text


def _service(
    *,
    client=None,
    shadow_service=None,
    session_service=None,
):
    return KisLimitedAutoBuyService(
        client or _FakeClient(),
        shadow_service=shadow_service or _FakeShadowService(),
        session_service=session_service or _OpenSessionService(),
    )


def _enable_runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": True,
        "kill_switch": False,
        "kis_live_auto_enabled": False,
        "kis_live_auto_buy_enabled": False,
        "kis_live_auto_sell_enabled": False,
        "kis_limited_auto_sell_enabled": True,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_buy_enabled": False,
        "kis_limited_auto_buy_readiness_enabled": True,
        "kis_limited_auto_buy_shadow_enabled": True,
        "kis_limited_auto_buy_requires_shadow_review": True,
        "kis_limited_auto_buy_max_orders_per_day": 1,
        "kis_limited_auto_buy_max_notional_pct": 0.03,
        "kis_limited_auto_buy_max_notional_krw": 55_000,
        "kis_limited_auto_buy_min_cash_buffer_krw": 0,
        "kis_limited_auto_buy_requires_existing_sell_guards": True,
        "kis_limited_auto_buy_min_final_score": 75,
        "kis_limited_auto_buy_min_confidence": 0.70,
        "kis_limited_auto_buy_max_positions": 1,
        "kis_limited_auto_buy_block_if_position_exists": True,
        "kis_limited_auto_buy_block_if_open_order_exists": True,
        "kis_limited_auto_buy_allow_reentry_same_day": False,
        "kis_limited_auto_buy_require_market_open": True,
        "kis_limited_auto_buy_no_new_entry_after": "23:59",
        "kis_limited_auto_buy_allow_gpt_hard_block": False,
        "kis_scheduler_live_enabled": False,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_allow_limited_auto_buy": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


def _shadow_payload(**candidate_overrides):
    candidate = _candidate(**candidate_overrides)
    return {
        "status": "ok",
        "mode": "shadow_buy_dry_run",
        "decision": "would_buy",
        "result": "would_buy",
        "action": "buy",
        "reason": "Shadow buy candidate only. No broker path.",
        "symbol": candidate["symbol"],
        "candidate": candidate,
        "candidates": [candidate],
        "candidate_count": 1,
        "real_order_submitted": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "run": {"run_key": "shadow-buy-run"},
    }


def _candidate(**overrides):
    payload = {
        "symbol": "005930",
        "company_name": "Samsung Electronics",
        "market": "KR",
        "provider": "kis",
        "final_score": 82.5,
        "final_buy_score": 82.5,
        "final_entry_score": 82.5,
        "final_sell_score": 12.0,
        "quant_score": 78.0,
        "quant_buy_score": 78.0,
        "quant_sell_score": 10.0,
        "gpt_buy_score": 65.0,
        "ai_buy_score": 65.0,
        "ai_sell_score": 14.0,
        "confidence": 0.76,
        "current_price": 52_000,
        "suggested_notional": 52_000,
        "estimated_notional": 52_000,
        "suggested_quantity": 1,
        "indicator_status": "ok",
        "indicator_bar_count": 120,
        "indicator_payload": {
            "price": 52_000,
            "ema20": 50_500,
            "ema50": 49_000,
            "vwap": 51_200,
            "rsi": 57.5,
            "atr": 1200,
            "volume_ratio": 1.3,
            "recent_return": 0.018,
            "momentum": 0.021,
            "price_position": "above_ema20",
        },
        "reason": "Shadow buy candidate only. No broker path.",
        "gpt_reason": "Quant-first buy setup is constructive.",
        "risk_flags": [],
        "gating_notes": ["shadow_buy_only"],
        "audit_metadata": {
            "source": "kis_buy_shadow_decision",
            "source_type": "dry_run_buy_simulation",
        },
    }
    payload.update(overrides)
    return payload


def _seed_limited_buy_order(db_session):
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="buy",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.FILLED.value,
        broker_order_id="BUY-TODAY",
        kis_odno="BUY-TODAY",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps({"mode": RUN_MODE, "source": SOURCE}),
        response_payload=json.dumps({"mode": RUN_MODE, "source": SOURCE, "source_type": SOURCE_TYPE}),
    )
    db_session.add(row)
    db_session.commit()
