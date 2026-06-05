from __future__ import annotations

import json
import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, RuntimeSetting, SignalLog, TradeRunLog
from app.main import app
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.runtime_setting_service import RuntimeSettingService


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
        "kis_scheduler_allow_real_orders": False,
        "kr_scheduler_allow_real_orders": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeClient:
    def __init__(
        self,
        *,
        settings=None,
        balance=None,
        positions=None,
        open_orders=None,
    ):
        self.settings = settings or SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
            kis_confirmation_phrase="I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER",
        )
        self.balance = balance or {
            "provider": "kis",
            "market": "KR",
            "total_asset_value": 10_000_000,
            "cash": 1_000_000,
        }
        self.positions = positions if positions is not None else [_stop_loss_position()]
        self.open_orders = open_orders or []

    def get_account_balance(self):
        return self.balance

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders

    def _request_balance(self):
        return {
            "output2": {
                "dnca_tot_amt": self.balance.get("cash"),
                "nass_amt": self.balance.get("total_asset_value"),
                "tot_asst_amt": self.balance.get("total_asset_value"),
                "cash": self.balance.get("cash"),
                "scts_evlu_amt": self.balance.get("stock_evaluation_amount", 0),
            },
            "output1": [
                {
                    "hldg_qty": pos.get("qty"),
                    "prpr": pos.get("current_price"),
                    "pchs_avg_pric": pos.get("avg_entry_price"),
                    "pchs_amt": pos.get("cost_basis"),
                    "pdno": pos.get("symbol"),
                    "prdt_name": pos.get("name"),
                    "evlu_amt": pos.get("market_value"),
                    "evlu_pfls_amt": pos.get("unrealized_pl"),
                    "evlu_pfls_rt": pos.get("unrealized_plpc"),
                }
                for pos in self.positions
            ],
        }

    def _request_positions(self):
        return self.positions

    def _request_open_orders(self):
        return self.open_orders


class _OpenSessionService:
    def get_session_status(self, market, **kwargs):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "is_holiday": False,
            "closure_reason": None,
            "effective_close": "15:30",
            "no_new_entry_after": "15:00",
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


def test_status_endpoint_returns_default_disabled_off_state(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _OpenSessionService().get_session_status(
            market, **kwargs
        ),
    )

    response = client.get("/kis/limited-auto-sell/status")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["market"] == "KR"
    assert body["live_auto_sell_enabled"] is False
    assert body["stop_loss_auto_sell_enabled"] is False
    assert body["take_profit_auto_sell_enabled"] is False
    assert body["take_profit_readiness_enabled"] is True
    assert body["take_profit_execution_enabled"] is False
    assert body["take_profit_non_actionable"] is True
    assert body["supported_triggers"]["stop_loss"]["mode"] == "guarded_execution"
    assert body["supported_triggers"]["take_profit"]["mode"] == "readiness_only"
    assert body["scheduler_real_orders_enabled"] is False
    assert body["dry_run"] is True
    assert body["kill_switch"] is False
    assert body["kis_enabled"] is True
    assert body["kis_real_order_enabled"] is True
    assert body["market_open"] is True
    assert body["sell_session_allowed"] is True
    assert body["auto_order_ready"] is False
    assert body["real_order_submit_allowed"] is False
    assert body["live_auto_buy_enabled"] is False
    assert "dry_run_true" in body["block_reasons"]
    assert "kis_live_auto_sell_disabled" in body["block_reasons"]
    assert "stop_loss_auto_sell_disabled" in body["block_reasons"]
    assert body["safety"]["real_order_submitted"] is False
    assert body["safety"]["broker_submit_called"] is False
    assert body["safety"]["manual_submit_called"] is False
    assert body["safety"]["take_profit_execution_enabled"] is False
    assert body["safety"]["take_profit_non_actionable"] is True
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0


def test_preflight_endpoint_never_submits_orders(
    monkeypatch,
    client,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.MarketSessionService.get_session_status",
        lambda self, market, **kwargs: _OpenSessionService().get_session_status(
            market, **kwargs
        ),
    )
    class FakeCache:
        def get_account_state(self, *, read_only=True, require_fresh=False):
            return {
                "provider": "kis",
                "market": "KR",
                "source": "fresh",
                "fetch_success": True,
                "cache_age_seconds": 0.0,
                "rate_limited": False,
                "warnings": [],
                "balance": {"cash": 1_000_000, "total_asset_value": 10_000_000},
                "positions": [_stop_loss_position()],
                "open_orders": [],
            }

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisAccountStateCacheService.get_or_create",
        lambda client: FakeCache(),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("preflight must not submit"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("preflight must not call manual submit"),
    )

    response = client.post("/kis/limited-auto-sell/preflight-once", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kis_limited_auto_stop_loss_preflight"
    assert body["result"] == "preview_only"
    assert body["final_candidate"]["status"] == "SELL_READY"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0


def test_preflight_valid_stop_loss_candidate_returns_sell_ready(db_session):
    result = _service().preflight_once(db_session)

    assert result["result"] == "preview_only"
    assert result["action"] == "sell_ready"
    assert result["candidate_count"] == 1
    assert result["final_candidate"]["symbol"] == "005930"
    assert result["final_candidate"]["company_name"] == "Samsung Electronics"
    assert result["final_candidate"]["status"] == "SELL_READY"
    assert result["final_candidate"]["stop_loss_triggered"] is True
    assert result["final_candidate"]["take_profit_triggered"] is False
    assert result["final_candidate"]["unrealized_pl_pct"] == pytest.approx(-0.04)
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0


def test_preflight_returns_take_profit_candidate_as_readiness_only(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("take-profit preflight must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("take-profit preflight must not submit"),
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.preflight_once(db_session)

    candidate = result["final_candidate"]
    assert result["result"] == "preview_only"
    assert result["action"] == "review_sell"
    assert result["source"] == "kis_limited_auto_take_profit"
    assert result["source_type"] == "take_profit_readiness_only"
    assert result["take_profit_readiness_enabled"] is True
    assert result["take_profit_execution_enabled"] is False
    assert result["take_profit_non_actionable"] is True
    assert result["real_order_submit_allowed"] is False
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert candidate["status"] == "TAKE_PROFIT_READY"
    assert candidate["stop_loss_triggered"] is False
    assert candidate["take_profit_triggered"] is True
    assert candidate["take_profit_readiness_only"] is True
    assert candidate["take_profit_actionable"] is False
    assert candidate["take_profit_execution_disabled"] is True
    assert candidate["trigger_source"] == "take_profit"
    assert "take_profit_execution_disabled" in candidate["block_reasons"]
    assert "take_profit_readiness_only" in candidate["block_reasons"]
    assert "take_profit_execution_disabled" in result["block_reasons"]
    assert result["audit_metadata"]["source"] == "kis_limited_auto_take_profit"
    assert result["audit_metadata"]["source_type"] == "take_profit_readiness_only"
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0


def test_runtime_defaults_expose_safe_limited_auto_sell_aliases(db_session):
    settings = RuntimeSettingService().get_settings(db_session)

    assert settings["dry_run"] is True
    assert settings["kill_switch"] is False
    assert settings["kis_live_auto_sell_enabled"] is False
    assert settings["kis_limited_auto_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_take_profit_enabled"] is False
    assert settings["kis_limited_auto_take_profit_readiness_enabled"] is True
    assert settings["kis_limited_auto_take_profit_requires_valid_cost_basis"] is True
    assert settings["kis_limited_auto_take_profit_min_profit_pct"] == pytest.approx(0.03)
    assert settings["kis_limited_auto_sell_stop_loss_enabled"] is False
    assert settings["kis_limited_auto_sell_take_profit_enabled"] is False
    assert settings["kis_limited_auto_sell_take_profit_readiness_enabled"] is True
    assert settings["kis_limited_auto_sell_max_orders_per_day"] == 1
    assert settings["kis_limited_auto_sell_requires_valid_cost_basis"] is True
    assert settings["kis_scheduler_allow_real_orders"] is False


def test_missing_cost_basis_requires_manual_review_and_blocks_auto_sell(db_session):
    service = _service(client=_FakeClient(positions=[_missing_cost_basis_position()]))

    result = service.preflight_once(db_session)

    candidate = result["final_candidate"]
    assert candidate["status"] == "REVIEW_SELL"
    assert candidate["stop_loss_triggered"] is False
    assert candidate["take_profit_triggered"] is False
    assert candidate["take_profit_readiness_only"] is False
    assert candidate["unrealized_pl_pct"] is None
    assert "manual_review_required" in candidate["block_reasons"]
    assert "missing_cost_basis" in candidate["block_reasons"]
    assert "manual_review_required" in result["block_reasons"]
    assert result["real_order_submitted"] is False


def test_run_once_with_defaults_blocks_and_does_not_call_submit(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("default run must not submit"),
    )

    result = _service().run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "dry_run_true"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dry_run", True, "dry_run_true"),
        ("kill_switch", True, "kill_switch_enabled"),
        ("kis_live_auto_sell_enabled", False, "kis_live_auto_sell_disabled"),
        (
            "kis_limited_auto_sell_stop_loss_enabled",
            False,
            "stop_loss_auto_sell_disabled",
        ),
        ("kis_live_auto_buy_enabled", True, "live_auto_buy_must_remain_disabled"),
    ],
)
def test_run_once_runtime_gates_block_without_submit(
    db_session,
    field,
    value,
    reason,
):
    _enable_runtime(db_session, **{field: value})

    result = _service().run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == reason
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_run_once_kill_switch_blocks(db_session):
    _enable_runtime(db_session, kill_switch=True)

    result = _service().run_once(db_session)

    assert result["reason"] == "kill_switch_enabled"
    assert result["real_order_submitted"] is False


def test_run_once_take_profit_candidate_blocks_when_disabled(monkeypatch, db_session):
    _enable_runtime(db_session, kis_limited_auto_sell_max_orders_per_day=2)
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("disabled take-profit must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("disabled take-profit must not submit"),
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "take_profit_auto_sell_disabled"
    assert result["primary_block_reason"] == "take_profit_auto_sell_disabled"
    assert result["action"] == "blocked_sell"
    assert result["source"] == "kis_limited_auto_take_profit"
    assert result["source_type"] == "guarded_take_profit_auto_sell"
    assert result["mode"] == "kis_limited_auto_take_profit_run"
    assert result["take_profit_auto_sell_enabled"] is False
    assert result["take_profit_execution_enabled"] is False
    assert result["take_profit_non_actionable"] is True
    assert result["final_candidate"]["take_profit_triggered"] is True
    assert result["final_candidate"]["stop_loss_triggered"] is False
    assert "take_profit_auto_sell_disabled" in result["block_reasons"]
    assert result["validation_status"] == "not_called"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dry_run", True, "dry_run_enabled"),
        ("kill_switch", True, "kill_switch_enabled"),
        ("kis_live_auto_sell_enabled", False, "kis_live_auto_sell_disabled"),
    ],
)
def test_run_once_take_profit_runtime_gates_block_without_validation_or_submit(
    monkeypatch,
    db_session,
    field,
    value,
    reason,
):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
        **{field: value},
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("runtime-blocked take-profit must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("runtime-blocked take-profit must not submit"),
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == reason
    assert result["primary_block_reason"] == reason
    assert result["source"] == "kis_limited_auto_take_profit"
    assert result["source_type"] == "guarded_take_profit_auto_sell"
    assert result["take_profit_auto_sell_enabled"] is True
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False
    assert result["validation_status"] == "not_called"
    assert db_session.query(OrderLog).count() == 0


def test_run_once_take_profit_blocks_when_kis_real_order_disabled(
    monkeypatch,
    db_session,
):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("KIS-real-order blocked take-profit must not validate"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("KIS-real-order blocked take-profit must not submit"),
    )
    service = _service(
        client=_FakeClient(
            settings=_settings(kis_real_order_enabled=False),
            positions=[_take_profit_position()],
        )
    )

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "kis_real_order_disabled"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert result["validation_status"] == "not_called"
    assert db_session.query(OrderLog).count() == 0


def test_run_once_take_profit_missing_cost_basis_blocks(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("invalid cost basis must not validate"),
    )
    service = _service(client=_FakeClient(positions=[_missing_cost_basis_position()]))

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "invalid_cost_basis"
    assert result["primary_block_reason"] == "invalid_cost_basis"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert result["validation_status"] == "not_called"
    assert db_session.query(OrderLog).count() == 0


def test_run_once_take_profit_threshold_not_met_blocks(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("below-threshold take-profit must not validate"),
    )
    service = _service(
        client=_FakeClient(
            positions=[
                _take_profit_position(
                    current_price=102_000,
                    current_value=102_000,
                    market_value=102_000,
                    unrealized_pl=2_000,
                    unrealized_plpc=2.0,
                )
            ]
        )
    )

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "take_profit_threshold_not_met"
    assert result["primary_block_reason"] == "take_profit_threshold_not_met"
    assert result["take_profit_triggered"] is False
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert result["validation_status"] == "not_called"


def test_run_once_take_profit_duplicate_open_sell_blocks(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("duplicate take-profit must not validate"),
    )
    service = _service(
        client=_FakeClient(
            positions=[_take_profit_position()],
            open_orders=[{"symbol": "005930", "side": "sell"}],
        )
    )

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "duplicate_open_sell_order"
    assert result["final_candidate"]["duplicate_open_sell_order"] is True
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert result["validation_status"] == "not_called"
    assert db_session.query(OrderLog).count() == 0


def test_run_once_take_profit_daily_limit_blocks(monkeypatch, db_session):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    _seed_limited_auto_sell_order(db_session)
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda *args, **kwargs: pytest.fail("daily-limited take-profit must not validate"),
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "daily_auto_sell_limit_reached"
    assert result["primary_block_reason"] == "daily_auto_sell_limit_reached"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert result["validation_status"] == "not_called"
    assert db_session.query(OrderLog).count() == 1


def test_run_once_take_profit_validation_failure_blocks_before_manual_submit(
    monkeypatch,
    db_session,
):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    validation_calls = []

    def fake_validate(self, request, *, now=None):
        validation_calls.append(request)
        metadata = request.source_metadata
        assert request.side == "sell"
        assert metadata["source"] == "kis_limited_auto_take_profit"
        assert metadata["source_type"] == "guarded_take_profit_auto_sell"
        assert metadata["mode"] == "kis_limited_auto_take_profit_run"
        assert metadata["take_profit_triggered"] is True
        assert metadata["stop_loss_triggered"] is False
        return _FakeValidationResult(
            validated=False,
            block_reasons=["validation_failed_for_test"],
        )

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        fake_validate,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.record_kis_order_validation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual submit must not run after take-profit validation failure"),
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.run_once(db_session)

    assert len(validation_calls) == 1
    assert result["result"] == "blocked"
    assert result["action"] == "blocked_sell"
    assert result["reason"] == "validation_failed"
    assert "validation_failed_for_test" in result["block_reasons"]
    assert result["validation_status"] == "blocked"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False


def test_run_once_take_profit_all_gates_true_submits_through_guarded_path(
    monkeypatch,
    db_session,
):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    validation_calls = []
    manual_calls = []

    def fake_validate(self, request, *, now=None):
        validation_calls.append(request)
        metadata = request.source_metadata
        assert metadata["source"] == "kis_limited_auto_take_profit"
        assert metadata["source_type"] == "guarded_take_profit_auto_sell"
        assert metadata["mode"] == "kis_limited_auto_take_profit_run"
        assert metadata["trigger_source"] == "limited_auto_sell_run_once"
        assert metadata["symbol"] == "005930"
        assert metadata["quantity"] == 1
        assert metadata["current_price"] == 103_000
        assert metadata["cost_basis"] == 100_000
        assert metadata["current_value"] == 103_000
        assert metadata["unrealized_pl"] == 3_000
        assert metadata["unrealized_pl_pct"] == pytest.approx(0.03)
        assert metadata["take_profit_threshold_pct"] == pytest.approx(3.0)
        assert metadata["take_profit_triggered"] is True
        assert metadata["stop_loss_triggered"] is False
        assert metadata["take_profit_actionable"] is True
        assert metadata["runtime_safety_snapshot"]["kis_limited_auto_take_profit_enabled"] is True
        return _FakeValidationResult(validated=True)

    def fake_submit_manual(self, db, request, *, now=None):
        manual_calls.append(request)
        metadata = request.source_metadata
        assert request.side == "sell"
        assert request.dry_run is False
        assert request.confirm_live is True
        assert request.confirmation == "I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER"
        assert metadata["source"] == "kis_limited_auto_take_profit"
        assert metadata["source_type"] == "guarded_take_profit_auto_sell"
        assert metadata["mode"] == "kis_limited_auto_take_profit_run"
        assert metadata["real_order_submit_allowed"] is True
        assert metadata["validation_summary"]["validation_status"] == "passed"
        return 200, {
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": 789,
            "order_log_id": 789,
            "broker_order_id": "TP789",
            "kis_odno": "TP789",
            "broker_status": "submitted",
        }

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        fake_validate,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.record_kis_order_validation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit_manual,
    )
    service = _service(client=_FakeClient(positions=[_take_profit_position()]))

    result = service.run_once(db_session)

    assert len(validation_calls) == 1
    assert len(manual_calls) == 1
    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["side"] == "sell"
    assert result["trigger"] == "take_profit"
    assert result["source"] == "kis_limited_auto_take_profit"
    assert result["source_type"] == "guarded_take_profit_auto_sell"
    assert result["mode"] == "kis_limited_auto_take_profit_run"
    assert result["reason"] == "take_profit_auto_sell_submitted"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is True
    assert result["order_id"] == 789
    assert result["broker_order_id"] == "TP789"
    assert result["kis_odno"] == "TP789"
    assert result["validation_status"] == "passed"
    assert result["source_metadata"]["real_order_submitted"] is True
    assert result["source_metadata"]["broker_submit_called"] is True
    assert result["source_metadata"]["manual_submit_called"] is True
    assert result["source_metadata"]["validation_summary"]["validation_status"] == "passed"
    assert db_session.query(SignalLog).count() == 1
    assert (
        db_session.query(TradeRunLog)
        .filter(TradeRunLog.mode == "kis_limited_auto_take_profit_run")
        .count()
        == 1
    )


def test_manual_submit_returning_existing_filled_order_is_reconciled(monkeypatch, db_session):
    # Simulate manual submit creating a FILLED OrderLog and returning its id
    _enable_runtime(db_session, kis_limited_auto_sell_max_orders_per_day=2)

    def fake_submit(self, db, request, *, now=None):
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol="005930",
            side="sell",
            order_type="market",
            qty=1,
            requested_qty=1,
            internal_status=InternalOrderStatus.FILLED.value,
            broker_order_id="SEED-1",
            kis_odno="SEED-1",
            submitted_at=datetime.now(UTC).replace(tzinfo=None),
            request_payload=json.dumps({"mode": "manual_live"}),
            response_payload=json.dumps({"mode": "manual_live", "real_order_submitted": True}),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return 200, {
            "order_id": row.id,
            "order_log_id": row.id,
            "broker_order_id": row.broker_order_id,
            "kis_odno": row.kis_odno,
        }

    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit,
    )
    # Ensure order validation passes so submit path is reached
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        lambda self, request, *, now=None: _FakeValidationResult(validated=True),
    )

    result = _service().run_once(db_session)
    assert result["result"] != "blocked"
    assert result["action"] == "sell"
    created = db_session.query(OrderLog).order_by(OrderLog.id.desc()).first()
    assert result["order_id"] == created.id
    assert result.get("kis_odno") == created.kis_odno
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result.get("execution_path") == "limited_auto_sell_via_manual_order_service"
    assert result.get("scheduler_origin") in (True, False)


def test_manual_submit_returning_missing_order_does_not_reconcile(monkeypatch, db_session):
    _enable_runtime(db_session)

    def fake_submit_missing(self, db, request, *, now=None):
        return 200, {"order_id": 9999999, "order_log_id": 9999999}

    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit_missing,
    )

    result = _service().run_once(db_session)

    # No real OrderLog -> should remain blocked/error according to flow
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False


def test_rate_limited_without_cache_blocks_as_kis_rate_limited(monkeypatch, db_session):
    # Simulate account state rate limit with no cache

    class FakeCache:
        def get_account_state(self, *, read_only=True, require_fresh=False):
            return {"fetch_success": False, "rate_limited": True, "warnings": ["kis_rate_limited"]}

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisAccountStateCacheService.get_or_create",
        lambda client: FakeCache(),
    )

    _enable_runtime(db_session)
    service = _service()
    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert "kis_rate_limited" in result.get("block_reasons", []) or result.get("reason") == "kis_rate_limited"
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False


def test_rate_limited_with_recent_cache_allows_evaluation(monkeypatch, db_session):
    # Simulate rate limit but with recent cache available

    class FakeCache:
        def get_account_state(self, *, read_only=True, require_fresh=False):
            return {
                "source": "cache_after_rate_limit",
                "cache_age_seconds": 1.0,
                "fetch_success": True,
                "rate_limited": True,
                "warnings": ["kis_rate_limited"],
                "balance": {"cash": 1000000},
                "positions": [
                    {
                        "symbol": "005930",
                        "qty": 1,
                        "avg_entry_price": 100000,
                        "current_price": 96000,
                        "cost_basis": 100000,
                    }
                ],
                "open_orders": [],
            }

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisAccountStateCacheService.get_or_create",
        lambda client: FakeCache(),
    )

    # preflight should proceed with evaluation using cached account state
    service = _service()
    result = service.preflight_once(db_session)
    assert result.get("state_source") == "cache_after_rate_limit"
    assert result.get("rate_limited") is True
    assert result.get("cache_age_seconds") == 1.0
    assert result.get("state_meta", {}).get("source") == "cache_after_rate_limit"
    assert "kis_rate_limited" in result.get("state_meta", {}).get("warnings", [])


def test_stale_cache_exceeded_blocks_submission(monkeypatch, db_session):

    class FakeCache:
        def get_account_state(self, *, read_only=True, require_fresh=False):
            # Simulate stale cache beyond max stale TTL
            return {"fetch_success": False, "warnings": ["kis_rate_limited"], "rate_limited": True}

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisAccountStateCacheService.get_or_create",
        lambda client: FakeCache(),
    )

    _enable_runtime(db_session)
    service = _service()
    result = service.run_once(db_session)
    assert result["result"] == "blocked"
    assert (
        result.get("reason") == "kis_account_state_cache_expired"
        or result.get("reason") == "kis_rate_limited"
        or "kis_rate_limited" in result.get("block_reasons", [])
    )
    assert result["rate_limited"] is True or result.get("state_meta", {}).get("rate_limited") is True
    assert result["real_order_submitted"] is False
    assert result["broker_submit_called"] is False
    assert result["manual_submit_called"] is False


def test_run_once_prioritizes_stop_loss_when_take_profit_flag_also_present(
    monkeypatch,
    db_session,
):
    _enable_runtime(
        db_session,
        kis_limited_auto_sell_take_profit_enabled=True,
    )
    validation_calls = []
    manual_calls = []

    def fake_thresholds(position, **kwargs):
        return ["stop_loss_triggered", "take_profit_triggered"], {
            "cost_basis": 100_000,
            "current_value": 96_000,
            "unrealized_pl": -4_000,
            "unrealized_pl_pct": -0.04,
            "take_profit_threshold_pct": 3.0,
            "stop_loss_threshold_pct": 2.0,
            "exit_trigger_source": "cost_basis",
            "pl_input_warning": None,
        }

    def fake_validate(self, request, *, now=None):
        validation_calls.append(request)
        metadata = request.source_metadata
        assert metadata["source"] == "kis_limited_auto_stop_loss"
        assert metadata["source_type"] == "guarded_stop_loss_auto_sell"
        assert metadata["stop_loss_triggered"] is True
        assert metadata["take_profit_triggered"] is False
        assert metadata["take_profit_triggered_ignored"] is True
        return _FakeValidationResult(validated=True)

    def fake_submit_manual(self, db, request, *, now=None):
        manual_calls.append(request)
        return 200, {
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": 456,
            "order_log_id": 456,
            "broker_order_id": "STOPLOSS456",
            "kis_odno": "STOPLOSS456",
        }

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.position_exit_threshold_reasons",
        fake_thresholds,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        fake_validate,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.record_kis_order_validation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit_manual,
    )

    result = _service().run_once(db_session)

    assert len(validation_calls) == 1
    assert len(manual_calls) == 1
    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["source"] == "kis_limited_auto_stop_loss"
    assert result["source_type"] == "guarded_stop_loss_auto_sell"
    assert result["stop_loss_triggered"] is True
    assert result["take_profit_triggered"] is True
    assert result["real_order_submitted"] is True
    assert result["order_id"] == 456


def test_no_held_position_blocks_without_submit(monkeypatch, db_session):
    _enable_runtime(db_session)
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("no-position run must not submit"),
    )
    service = _service(client=_FakeClient(positions=[]))

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "no_held_position"
    assert result["primary_block_reason"] == "no_held_position"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False
    assert db_session.query(OrderLog).count() == 0


def test_duplicate_open_sell_order_blocks(db_session):
    _enable_runtime(db_session)
    service = _service(
        client=_FakeClient(open_orders=[{"symbol": "005930", "side": "sell"}])
    )

    result = service.run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "duplicate_open_sell_order"
    assert result["final_candidate"]["duplicate_open_sell_order"] is True
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 0


def test_daily_auto_sell_count_limit_blocks(db_session):
    _enable_runtime(db_session)
    _seed_limited_auto_sell_order(db_session)

    result = _service().run_once(db_session)

    assert result["result"] == "blocked"
    assert result["reason"] == "symbol_already_auto_sold_today"
    assert result["real_order_submitted"] is False
    assert db_session.query(OrderLog).count() == 1


def test_validation_failure_blocks_before_manual_submit(monkeypatch, db_session):
    _enable_runtime(db_session)
    validation_calls = []

    def fake_validate(self, request, *, now=None):
        validation_calls.append(request)
        return _FakeValidationResult(
            validated=False,
            block_reasons=["validation_failed_for_test"],
        )

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        fake_validate,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.record_kis_order_validation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("manual submit must not run after validation failure"),
    )

    result = _service().run_once(db_session)

    assert len(validation_calls) == 1
    assert validation_calls[0].source_metadata["source"] == "kis_limited_auto_stop_loss"
    assert validation_calls[0].source_metadata["source_type"] == "guarded_stop_loss_auto_sell"
    assert result["result"] == "blocked"
    assert result["action"] == "blocked_sell"
    assert result["reason"] == "validation_failed_for_test"
    assert result["validation_status"] == "blocked"
    assert result["real_order_submitted"] is False
    assert result["manual_submit_called"] is False
    assert result["broker_submit_called"] is False


def test_all_gates_true_submits_through_validation_and_manual_service(
    monkeypatch,
    db_session,
):
    _enable_runtime(db_session)
    validation_calls = []
    manual_calls = []

    def fake_validate(self, request, *, now=None):
        validation_calls.append(request)
        metadata = request.source_metadata
        assert metadata["source"] == "kis_limited_auto_stop_loss"
        assert metadata["source_type"] == "guarded_stop_loss_auto_sell"
        assert metadata["mode"] == "kis_limited_auto_stop_loss_run"
        assert metadata["trigger_source"] == "limited_auto_sell_run_once"
        assert metadata["symbol"] == "005930"
        assert metadata["quantity"] == 1
        assert metadata["stop_loss_triggered"] is True
        assert metadata["take_profit_triggered"] is False
        assert metadata["daily_limit"]["daily_limit_remaining"] == 1
        return _FakeValidationResult(validated=True)

    def fake_submit_manual(self, db, request, *, now=None):
        manual_calls.append(request)
        metadata = request.source_metadata
        assert request.side == "sell"
        assert request.dry_run is False
        assert request.confirm_live is True
        assert request.confirmation == "I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER"
        assert metadata["source"] == "kis_limited_auto_stop_loss"
        assert metadata["source_type"] == "guarded_stop_loss_auto_sell"
        assert metadata["real_order_submit_allowed"] is True
        return 200, {
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "order_id": 123,
            "order_log_id": 123,
            "broker_order_id": "AUTO123",
            "kis_odno": "AUTO123",
            "broker_status": "submitted",
        }

    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.KisOrderValidationService.validate",
        fake_validate,
    )
    monkeypatch.setattr(
        "app.services.kis_limited_auto_sell_service.record_kis_order_validation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        fake_submit_manual,
    )

    result = _service().run_once(db_session)

    assert len(validation_calls) == 1
    assert len(manual_calls) == 1
    assert result["result"] == "submitted"
    assert result["action"] == "sell"
    assert result["side"] == "sell"
    assert result["source"] == "kis_limited_auto_stop_loss"
    assert result["source_type"] == "guarded_stop_loss_auto_sell"
    assert result["mode"] == "kis_limited_auto_stop_loss_run"
    assert result["real_order_submitted"] is True
    assert result["broker_submit_called"] is True
    assert result["manual_submit_called"] is True
    assert result["order_id"] == 123
    assert result["broker_order_id"] == "AUTO123"
    assert result["kis_odno"] == "AUTO123"
    assert result["validation_status"] == "passed"
    assert result["source_metadata"]["real_order_submitted"] is True
    assert result["source_metadata"]["broker_submit_called"] is True
    assert result["source_metadata"]["manual_submit_called"] is True
    assert db_session.query(SignalLog).count() == 1
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == "kis_limited_auto_stop_loss_run").count() == 1


def test_scheduler_real_orders_and_live_auto_buy_remain_disabled(db_session):
    _enable_runtime(
        db_session,
        kis_live_auto_buy_enabled=True,
        kis_scheduler_allow_real_orders=True,
    )

    result = _service().status(db_session)

    assert result["live_auto_buy_enabled"] is False
    assert result["scheduler_real_orders_enabled"] is False
    assert result["take_profit_auto_sell_enabled"] is False
    assert "live_auto_buy_must_remain_disabled" in result["block_reasons"]
    assert "scheduler_real_orders_must_remain_disabled" not in result["block_reasons"]
    assert "scheduler_limited_auto_sell_must_remain_disabled" not in result["block_reasons"]


def test_scheduler_origin_sell_does_not_block_on_scheduler_configured_flags(
    db_session,
):
    _enable_runtime(
        db_session,
        kis_live_auto_buy_enabled=False,
        kis_limited_auto_sell_stop_loss_enabled=True,
        kis_limited_auto_sell_take_profit_enabled=False,
        kis_scheduler_allow_real_orders=True,
        kis_scheduler_configured_allow_real_orders=True,
        kis_scheduler_allow_limited_auto_sell=True,
        kis_scheduler_sell_enabled=True,
    )

    result = _service(allow_scheduler_guarded_sell=True).status(db_session)

    assert "scheduler_real_orders_must_remain_disabled" not in result["block_reasons"]
    assert "scheduler_limited_auto_sell_must_remain_disabled" not in result["block_reasons"]


def test_limited_auto_sell_service_has_no_direct_broker_submit_calls():
    source = inspect.getsource(KisLimitedAutoSellService)

    assert "submit_order" not in source
    assert "submit_domestic_cash_order" not in source
    assert "submit_market_sell" not in source
    assert "self.client.submit" not in source
    assert "self.broker.submit" not in source


def _service(client=None, *, allow_scheduler_guarded_sell=False):
    return KisLimitedAutoSellService(
        client or _FakeClient(),
        session_service=_OpenSessionService(),
        allow_scheduler_guarded_sell=allow_scheduler_guarded_sell,
    )


def _enable_runtime(db_session, **overrides):
    db_session.query(RuntimeSetting).delete()
    values = {
        "dry_run": False,
        "kill_switch": False,
        "kis_live_auto_buy_enabled": False,
        "kis_live_auto_sell_enabled": True,
        "kis_limited_auto_sell_stop_loss_enabled": True,
        "kis_limited_auto_sell_take_profit_enabled": False,
        "kis_limited_auto_sell_max_orders_per_day": 1,
        "kis_scheduler_allow_real_orders": False,
        "kis_scheduler_allow_limited_auto_sell": False,
    }
    values.update(overrides)
    db_session.add(RuntimeSetting(**values))
    db_session.commit()


class _FakeValidationResult:
    def __init__(self, *, validated, block_reasons=None):
        self.provider = "kis"
        self.market = "KR"
        self.environment = "prod"
        self.dry_run = True
        self.validated_for_submission = validated
        self.can_submit_later = validated
        self.symbol = "005930"
        self.side = "sell"
        self.qty = 1
        self.order_type = "market"
        self.current_price = 96_000
        self.estimated_amount = 96_000
        self.available_cash = None
        self.held_qty = 1
        self.warnings = []
        self.block_reasons = block_reasons or []
        self.market_session = {"is_market_open": True}
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
            "held_qty": self.held_qty,
            "warnings": self.warnings,
            "block_reasons": self.block_reasons,
            "market_session": self.market_session,
            "order_preview": self.order_preview,
            "primary_block_reason": self.primary_block_reason,
            "message": self.message,
            "detail": self.detail,
        }


def _stop_loss_position(**overrides):
    payload = {
        "symbol": "005930",
        "name": "Samsung Electronics",
        "qty": 1,
        "current_price": 96_000,
        "avg_entry_price": 100_000,
        "cost_basis": 100_000,
        "current_value": 96_000,
        "market_value": 96_000,
        "unrealized_pl": -4_000,
        "unrealized_plpc": -4.0,
    }
    payload.update(overrides)
    return payload


def _take_profit_position(**overrides):
    payload = _stop_loss_position(
        current_price=103_000,
        current_value=103_000,
        market_value=103_000,
        unrealized_pl=3_000,
        unrealized_plpc=3.0,
    )
    payload.update(overrides)
    return payload


def _missing_cost_basis_position():
    return _stop_loss_position(
        cost_basis=0,
        avg_entry_price=0,
        current_value=96_000,
        unrealized_pl=-4_000,
        unrealized_plpc=-5.0,
    )


def _seed_limited_auto_sell_order(db_session):
    row = OrderLog(
        broker="kis",
        market="KR",
        symbol="005930",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        internal_status=InternalOrderStatus.FILLED.value,
        broker_order_id="TODAY123",
        kis_odno="TODAY123",
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
        request_payload=json.dumps(
            {
                "mode": "manual_live",
                "source": "kis_limited_auto_stop_loss",
                "source_type": "limited_auto_sell_run",
            }
        ),
        response_payload=json.dumps(
            {
                "source": "kis_limited_auto_stop_loss",
                "source_type": "limited_auto_sell_run",
                "real_order_submitted": True,
            }
        ),
    )
    db_session.add(row)
    db_session.commit()
