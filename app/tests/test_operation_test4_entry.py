from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.kis_position_lifecycle_service import KisPositionLifecycleService
from app.services.operation_test4_service import (
    ENABLE_CONFIRMATION,
    ENTRY_CONFIRMATION,
    OperationTest4Service,
)
from app.services.runtime_setting_service import RuntimeSettingService


NOW = datetime(2026, 8, 7, 2, 0, tzinfo=UTC)


class FakeMarketSession:
    def get_session_status(self, market, *, now=None):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_holiday": False,
            "closure_reason": None,
            "regular_open": "09:00",
            "regular_close": "15:30",
            "no_new_entry_after": "14:00",
        }


class FakeClient:
    def __init__(self):
        self.settings = SimpleNamespace(
            kis_env="prod",
            kis_enabled=True,
            kis_real_order_enabled=True,
            kis_confirmation_phrase="I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER",
        )

    def get_account_balance(self):
        return {
            "total_asset_value": 1_000_000,
            "orderable_cash": 1_000_000,
        }

    def list_positions(self):
        return []

    def list_open_orders(self):
        return []


class FakeValidation:
    provider = "kis"
    validated_for_submission = True
    market = "KR"
    environment = "prod"
    dry_run = True
    can_submit_later = True
    symbol = "000001"
    company_name = "Test"
    side = "buy"
    qty = 5
    order_type = "market"
    current_price = 20_000.0
    estimated_amount = 100_000.0
    available_cash = 1_000_000.0
    held_qty = 0.0
    warnings = []
    block_reasons = []
    market_session = {}
    order_preview = {}
    source_metadata = {}
    primary_block_reason = None
    message = None
    detail = None

    def to_dict(self):
        return {
            "validated_for_submission": True,
            "market": self.market,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "current_price": self.current_price,
            "estimated_amount": self.estimated_amount,
            "provider": self.provider,
            "environment": self.environment,
            "validated_for_submission": self.validated_for_submission,
            "block_reasons": [],
        }


class FakeValidationService:
    def validate(self, request, *, now=None):
        result = FakeValidation()
        result.symbol = request.symbol
        result.qty = request.qty
        result.estimated_amount = request.qty * 20_000.0
        return result


class FakeManualOrderService:
    def __init__(self, *, status=InternalOrderStatus.PENDING.value, raise_error=None):
        self.status = status
        self.raise_error = raise_error
        self.calls = []

    def submit_manual(self, db, request, *, now=None):
        self.calls.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        filled = self.status == InternalOrderStatus.FILLED.value
        row = OrderLog(
            broker="kis",
            market="KR",
            symbol=request.symbol,
            side=request.side,
            order_type="market",
            qty=request.qty,
            requested_qty=request.qty,
            filled_qty=request.qty if filled else 0,
            remaining_qty=0 if filled else request.qty,
            avg_fill_price=20_000 if filled else None,
            filled_avg_price=20_000 if filled else None,
            notional=request.qty * 20_000,
            internal_status=self.status,
            broker_status="FILLED" if filled else "SUBMITTED",
            broker_order_status="FILLED" if filled else "SUBMITTED",
            broker_order_id="KIS-TEST4-ENTRY",
            kis_odno="KIS-TEST4-ENTRY",
            request_payload=json.dumps(
                {
                    "mode": request.source_metadata.get("mode"),
                    "source_metadata": request.source_metadata,
                    "source_endpoint": request.source_metadata.get("source_endpoint"),
                    "order_source": request.source_metadata.get("order_source"),
                    "operation_test": request.source_metadata.get("operation_test"),
                }
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return 200, {
            "order_id": row.id,
            "order_log_id": row.id,
            "broker_order_id": row.broker_order_id,
            "kis_odno": row.kis_odno,
            "real_order_submitted": True,
            "broker_submit_called": True,
            "manual_submit_called": True,
            "internal_status": self.status,
        }


def make_watchlist(path: Path, count: int = 50) -> Path:
    rows = "\n".join(
        f"- symbol: '{index:06d}'\n  name: Name {index}\n  market: KOSPI"
        for index in range(1, count + 1)
    )
    path.write_text(f"market: KR\nsymbols:\n{rows}\n", encoding="utf-8")
    return path


def candidate_provider(*, score=90, price=20_000):
    return {
        "final_ranked_candidates": [
            {
                "symbol": "000001",
                "name": "Test",
                "current_price": price,
                "final_buy_score": score,
                "final_entry_score": score,
                "block_reasons": [],
                "risk_flags": [],
            }
        ],
        "final_score_gap": 10,
        "watchlist": [{"symbol": f"{index:06d}", "current_price": 20_000} for index in range(1, 51)],
    }


def make_service(
    tmp_path,
    *,
    manual_service=None,
    candidate=None,
    account_state=None,
    lifecycle_service=None,
):
    client = FakeClient()
    state = account_state or {
        "fetch_success": True,
        "equity": 1_000_000,
        "orderable_cash": 1_000_000,
        "positions": [],
        "open_orders": [],
    }

    def account_provider():
        return state

    service = OperationTest4Service(
        client,
        session_service=FakeMarketSession(),
        watchlist_path=make_watchlist(tmp_path / "watchlist.yaml"),
        candidate_provider=candidate or (lambda **kwargs: candidate_provider()),
        account_state_provider=account_provider,
        manual_order_service=manual_service or FakeManualOrderService(),
        validation_service=FakeValidationService(),
        lifecycle_service=lifecycle_service,
        now_provider=lambda: NOW,
    )
    return service, client, state


def arm_for_entry(db_session, service):
    result = service.enable_live(
        db_session,
        confirm_live=True,
        confirmation=ENABLE_CONFIRMATION,
        now=NOW,
    )
    assert result["status"] == "live_enabled"
    RuntimeSettingService().update_settings(
        db_session,
        {"dry_run": False, "kill_switch": False},
    )


def test_entry_holds_when_score_gate_is_not_met(db_session, tmp_path):
    service, _, _ = make_service(
        tmp_path,
        candidate=lambda **kwargs: candidate_provider(score=64),
    )
    arm_for_entry(db_session, service)

    manual = service.manual_order_service
    result = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )

    assert result["reason"] == "candidate_gate_blocked"
    assert manual.calls == []


def test_first_valid_entry_submits_once_and_second_call_is_blocked(db_session, tmp_path):
    manual = FakeManualOrderService()
    service, _, _ = make_service(tmp_path, manual_service=manual)
    arm_for_entry(db_session, service)

    first = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )
    second = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )

    assert first["reason"] == "entry_submitted"
    assert second["reason"] in {"active_cycle_exists", "readiness_not_ready"}
    assert len(manual.calls) == 1


def test_submit_exception_is_not_retried_and_disarms(db_session, tmp_path):
    manual = FakeManualOrderService(raise_error=TimeoutError("submit timeout"))
    service, _, _ = make_service(tmp_path, manual_service=manual)
    arm_for_entry(db_session, service)

    result = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )
    settings = RuntimeSettingService().get_settings(db_session)

    assert result["reason"] == "entry_submit_exception"
    assert len(manual.calls) == 1
    assert settings["dry_run"] is True
    assert settings["kill_switch"] is True
    assert settings["operation_test4_enabled"] is False


def test_entry_is_blocked_when_position_or_open_order_exists(db_session, tmp_path):
    service, _, state = make_service(tmp_path)
    arm_for_entry(db_session, service)
    state["positions"] = [{"symbol": "005930", "qty": 1, "current_price": 20_000}]

    result = service.entry_run_once(
        db_session,
        confirm_live=True,
        confirmation=ENTRY_CONFIRMATION,
        now=NOW,
    )

    assert result["reason"] == "position_exists"
    assert service.manual_order_service.calls == []