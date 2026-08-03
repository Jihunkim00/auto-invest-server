from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import OrderLog, PositionLifecycle, TradeRunLog
from app.main import app
from app.routes.app_facade import get_operator_forced_one_share_buy_service
from app.schemas.operation_test import OperatorForcedOneShareBuyRequest
from app.services.kis_manual_order_service import KIS_MANUAL_CONFIRMATION_PHRASE
from app.services.operator_forced_one_share_buy_service import (
    MAX_NOTIONAL_KRW,
    MODE,
    OPERATOR_CONFIRMATION_PHRASE,
    OperatorForcedOneShareBuyService,
)
from app.services.runtime_setting_service import RuntimeSettingService


NOW = datetime(2026, 8, 3, 1, 0, tzinfo=UTC)


class _AuthManager:
    def require_configured(self):
        return None


class _FakeKisClient:
    def __init__(
        self,
        *,
        current_price: float = 52_000,
        positions: list[dict] | None = None,
        open_orders: list[dict] | None = None,
    ) -> None:
        self.settings = SimpleNamespace(
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_env="prod",
            kis_account_no="12345678",
            kis_account_product_code="01",
            kis_confirmation_phrase=KIS_MANUAL_CONFIRMATION_PHRASE,
            kis_require_confirmation=True,
            kis_max_manual_order_qty=1,
            kis_max_manual_order_amount_krw=MAX_NOTIONAL_KRW,
            kis_scheduler_allow_real_orders=False,
            kr_scheduler_allow_real_orders=False,
        )
        self.auth_manager = _AuthManager()
        self.current_price = current_price
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.submit_calls: list[dict] = []
        self.inquiry_calls: list[dict] = []

    def get_account_balance(self):
        return {"cash": 3_000_000, "total_asset_value": 10_000_000}

    def list_positions(self):
        return self.positions

    def list_open_orders(self):
        return self.open_orders

    def get_domestic_stock_price(self, symbol):
        return {
            "symbol": symbol,
            "current_price": self.current_price,
            "company_name": "Samsung Electronics",
        }

    def build_domestic_order_payload(self, **kwargs):
        return {"CANO": "12345678", "ACNT_PRDT_CD": "01", **kwargs}

    def domestic_cash_order_tr_id(self, side):
        return "TTTC0802U" if side == "buy" else "TTTC0801U"

    def submit_domestic_cash_order(self, **kwargs):
        self.submit_calls.append(kwargs)
        return {"rt_cd": "0", "output": {"ODNO": "0001234567"}}

    def inquire_daily_order_executions(self, **kwargs):
        self.inquiry_calls.append(kwargs)
        return {
            "orders": [
                {
                    "ODNO": "0001234567",
                    "ord_qty": "1",
                    "tot_ccld_qty": "1",
                    "rmn_qty": "0",
                    "avg_prvs": str(int(self.current_price)),
                }
            ]
        }


class _FakePreviewService:
    def __init__(self, candidates: list[dict] | None = None) -> None:
        self.candidates = candidates or []
        self.calls: list[dict] = []

    def run_preview(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "trigger_source": kwargs.get("trigger_source"),
            "top_quant_candidates": self.candidates,
            "final_ranked_candidates": self.candidates,
            "quant_candidates_count": len(self.candidates),
        }


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
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
            "no_new_entry_after": "14:50",
        }


def test_operator_forced_one_share_buy_submits_one_share_and_enables_position_management(
    db_session,
):
    _enable_operation_test_runtime(db_session)
    client = _FakeKisClient(current_price=52_000)
    preview = _FakePreviewService([_candidate(final_score=12, confidence=0.1)])
    service = _service(client, preview)

    result = service.run(db_session, _request(), now=NOW)

    assert result["result"] == "submitted"
    assert result["forced_test_entry"] is True
    assert result["qty"] == 1
    assert result["max_notional_krw"] == 55_000
    assert result["estimated_notional"] == 52_000
    assert result["technical_filter_passed"] is True
    assert result["manual_submit_called"] is True
    assert result["validation_called"] is True
    assert result["real_order_submitted"] is True
    assert result["auto_buy_disabled_after_submit"] is True
    assert result["position_management_only_enabled"] is True
    assert result["scheduler_auto_call_enabled"] is False

    assert preview.calls and preview.calls[0]["record_run"] is False
    assert len(client.submit_calls) == 1
    assert client.submit_calls[0]["qty"] == 1
    assert client.submit_calls[0]["side"] == "buy"

    order = db_session.query(OrderLog).one()
    assert order.symbol == "005930"
    assert order.side == "buy"
    assert order.requested_qty == 1
    assert order.filled_qty == 1
    assert order.avg_fill_price == 52_000
    assert order.internal_status == InternalOrderStatus.FILLED.value

    request_payload = _json(order.request_payload)
    response_payload = _json(order.response_payload)
    sync_payload = _json(order.last_sync_payload)
    assert request_payload["forced_test_entry"] is True
    assert request_payload["audit_metadata"]["forced_test_entry"] is True
    assert response_payload["audit_metadata"]["forced_test_entry"] is True
    assert sync_payload["forced_test_entry"] is True

    lifecycle = db_session.query(PositionLifecycle).one()
    assert lifecycle.entry_order_id == order.id
    assert lifecycle.symbol == "005930"
    assert lifecycle.quantity == 1
    assert lifecycle.entry_price == 52_000

    run = db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).one()
    run_payload = _json(run.response_payload)
    assert run.result == "submitted"
    assert run_payload["forced_test_entry"] is True
    assert run_payload["order_id"] == order.id

    settings = RuntimeSettingService().get_settings(db_session)
    assert settings["scheduler_enabled"] is False
    assert settings["kis_scheduler_enabled"] is False
    assert settings["kis_scheduler_buy_enabled"] is False
    assert settings["kis_live_auto_buy_enabled"] is False
    assert settings["kis_limited_auto_buy_enabled"] is False
    assert settings["strategy_live_auto_buy_enabled"] is False
    assert settings["kis_live_auto_sell_enabled"] is True
    assert settings["kis_limited_auto_sell_enabled"] is True
    assert settings["kis_limited_auto_stop_loss_enabled"] is True
    assert settings["kis_position_lifecycle_scheduler_enabled"] is False


def test_confirmation_must_match_exact_operator_phrase_before_preview_or_submit(
    db_session,
):
    client = _FakeKisClient()
    preview = _FakePreviewService([_candidate()])
    service = _service(client, preview)

    result = service.run(
        db_session,
        _request(confirmation="TEST3 LIVE BUY 1SHARE"),
        now=NOW,
    )

    assert result["result"] == "blocked"
    assert result["reason"] == "confirmation_mismatch"
    assert result["forced_test_entry"] is True
    assert result["validation_called"] is False
    assert result["manual_submit_called"] is False
    assert preview.calls == []
    assert client.submit_calls == []
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == MODE).count() == 1


def test_blocks_when_requested_symbol_is_not_technical_filter_candidate(db_session):
    _enable_operation_test_runtime(db_session)
    client = _FakeKisClient()
    preview = _FakePreviewService([_candidate(indicator_status="price_only", indicators={})])
    service = _service(client, preview)

    result = service.run(db_session, _request(), now=NOW)

    assert result["result"] == "blocked"
    assert "technical_indicator_status_not_ok" in result["block_reasons"]
    assert "technical_indicator_payload_not_ready" in result["block_reasons"]
    assert result["validation_called"] is False
    assert result["manual_submit_called"] is False
    assert client.submit_calls == []
    assert db_session.query(OrderLog).count() == 0


def test_blocks_candidate_above_55000_krw_before_validation(db_session):
    _enable_operation_test_runtime(db_session)
    client = _FakeKisClient(current_price=56_000)
    preview = _FakePreviewService([_candidate(price=56_000)])
    service = _service(client, preview)

    result = service.run(db_session, _request(), now=NOW)

    assert result["result"] == "blocked"
    assert result["reason"] == "max_notional_krw_exceeded"
    assert result["validation_called"] is False
    assert result["manual_submit_called"] is False
    assert client.submit_calls == []


@pytest.mark.parametrize(
    ("client_kwargs", "reason"),
    [
        ({"positions": [{"symbol": "005930", "qty": 1}]}, "current_position_not_zero"),
        ({"open_orders": [{"symbol": "005930", "remaining_qty": 1}]}, "open_order_not_zero"),
    ],
)
def test_blocks_when_current_position_or_open_order_exists(
    db_session,
    client_kwargs,
    reason,
):
    _enable_operation_test_runtime(db_session)
    client = _FakeKisClient(**client_kwargs)
    preview = _FakePreviewService([_candidate()])
    service = _service(client, preview)

    result = service.run(db_session, _request(), now=NOW)

    assert result["result"] == "blocked"
    assert reason in result["block_reasons"]
    assert preview.calls == []
    assert client.submit_calls == []


def test_forced_path_allows_only_one_buy_per_day(db_session):
    _enable_operation_test_runtime(db_session)
    db_session.add(
        OrderLog(
            broker="kis",
            market="KR",
            symbol="000660",
            side="buy",
            order_type="market",
            qty=1,
            internal_status=InternalOrderStatus.FILLED.value,
            broker_order_id="prev-order",
            kis_odno="prev-order",
            created_at=NOW.replace(tzinfo=None),
        )
    )
    db_session.commit()
    client = _FakeKisClient()
    preview = _FakePreviewService([_candidate()])
    service = _service(client, preview)

    result = service.run(db_session, _request(), now=NOW)

    assert result["result"] == "blocked"
    assert result["reason"] == "forced_daily_buy_limit_reached"
    assert preview.calls == []
    assert client.submit_calls == []


def test_operation_test3_route_uses_overridable_forced_service(db_session):
    class _RouteService:
        def run(self, db, payload):
            assert db is db_session
            assert payload.symbol == "005930"
            return {
                "status": "blocked",
                "provider": "kis",
                "market": "KR",
                "mode": MODE,
                "source": "kis_operator_forced_test_entry",
                "source_type": "operator_forced_one_share_buy",
                "result": "blocked",
                "action": "blocked_buy",
                "reason": "confirmation_mismatch",
                "primary_block_reason": "confirmation_mismatch",
                "block_reasons": ["confirmation_mismatch"],
                "forced_test_entry": True,
                "operation_test": "test3",
                "symbol": payload.symbol,
                "qty": 1,
                "max_notional_krw": MAX_NOTIONAL_KRW,
                "real_order_submitted": False,
                "manual_submit_called": False,
                "validation_called": False,
                "audit_metadata": {"forced_test_entry": True},
            }

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_operator_forced_one_share_buy_service] = (
        lambda: _RouteService()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/app/operation-test3/operator-forced-one-share-buy",
                json={
                    "symbol": "005930",
                    "operator": "ops",
                    "confirm_live": True,
                    "confirmation": "wrong",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    body = response.json()
    assert body["forced_test_entry"] is True
    assert body["reason"] == "confirmation_mismatch"


def _service(
    client: _FakeKisClient,
    preview: _FakePreviewService,
) -> OperatorForcedOneShareBuyService:
    return OperatorForcedOneShareBuyService(
        client,
        preview_service=preview,
        session_service=_OpenSessionService(),
    )


def _request(**overrides) -> OperatorForcedOneShareBuyRequest:
    values = {
        "symbol": "005930",
        "operator": "ops",
        "confirm_live": True,
        "confirmation": OPERATOR_CONFIRMATION_PHRASE,
        "reason": "operation test3",
    }
    values.update(overrides)
    return OperatorForcedOneShareBuyRequest(**values)


def _candidate(
    *,
    symbol: str = "005930",
    price: float = 52_000,
    final_score: float = 12,
    confidence: float = 0.1,
    indicator_status: str = "ok",
    indicators: dict | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "company_name": "Samsung Electronics",
        "current_price": price,
        "final_score": final_score,
        "quant_score": final_score,
        "gpt_buy_score": final_score,
        "confidence": confidence,
        "indicator_status": indicator_status,
        "indicator_payload": indicators if indicators is not None else _indicators(price),
    }


def _indicators(price: float) -> dict:
    return {
        "price": price,
        "ema20": price - 100,
        "ema50": price - 300,
        "rsi": 55,
        "vwap": price - 50,
        "atr": 900,
        "volume_ratio": 1.2,
        "short_momentum": 0.015,
        "day_open": price - 200,
        "previous_high": price + 500,
        "previous_low": price - 700,
    }


def _enable_operation_test_runtime(db_session) -> None:
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": False,
            "max_trades_per_day": 10,
            "scheduler_enabled": True,
            "kis_scheduler_enabled": True,
            "kis_scheduler_buy_enabled": True,
            "kis_scheduler_allow_limited_auto_buy": True,
            "kis_live_auto_buy_enabled": True,
            "kis_limited_auto_buy_enabled": True,
            "strategy_live_auto_buy_enabled": True,
            "strategy_live_auto_buy_scheduler_enabled": True,
            "kis_live_auto_sell_enabled": False,
            "kis_limited_auto_sell_enabled": False,
            "kis_limited_auto_stop_loss_enabled": False,
            "kis_position_lifecycle_scheduler_enabled": True,
        },
    )


def _json(value: str | None) -> dict:
    return json.loads(value or "{}")
