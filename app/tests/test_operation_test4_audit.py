from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.kis_manual_order_service import (
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_audit import normalize_kis_order_source_metadata
from app.services.kis_order_sync_service import serialize_kis_order
from app.tests.test_operation_test4_entry import FakeClient, NOW


def test_operation_test4_entry_audit_is_not_manual_live_or_unknown_manual(db_session):
    service = KisManualOrderService(FakeClient())
    request = KisManualOrderSubmitRequest(
        market="KR",
        symbol="000001",
        side="buy",
        qty=5,
        order_type="market",
        dry_run=False,
        confirm_live=True,
        confirmation="I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER",
        source_context="operation_test4_run_once",
        source_metadata={
            "source": "operation_test4_auto_entry",
            "source_type": "operation_test4_auto_entry",
            "source_endpoint": "/app/operation-test4/entry/run-once",
            "order_source": "operation_test4_auto_entry",
            "audit_source_context": "operation_test4_run_once",
            "operation_test": "test4",
            "mode": "operation_test4_live",
        },
    )

    audit = service._build_audit_metadata(
        db_session,
        request=request,
        now_utc=NOW,
        normalized_market="KR",
        normalized_symbol="000001",
        normalized_side="buy",
        validation_for_audit=None,
        latest_validation=None,
        source_metadata=request.source_metadata,
        runtime={"dry_run": False, "kill_switch": False},
        market_session={"is_market_open": True, "is_entry_allowed_now": True},
        failed_checks=[],
        daily_count=0,
        max_daily_trades=1,
        estimated_amount=100_000,
        confirmation_matches=True,
        real_order_submitted=True,
        broker_submit_called=True,
        manual_submit_called=True,
    )

    assert audit["mode"] == "operation_test4_live"
    assert audit["operation_test"] == "test4"
    assert audit["order_source"] == "operation_test4_auto_entry"
    assert audit["audit_source_context"] == "operation_test4_run_once"
    assert audit["source_endpoint"] == "/app/operation-test4/entry/run-once"
    assert audit["source_context"] != "unknown_manual"


def test_operation_test4_exit_audit_source_is_preserved_and_secrets_are_removed():
    metadata = normalize_kis_order_source_metadata(
        {
            "source": "operation_test4_auto_stop_loss",
            "source_type": "operation_test4_auto_stop_loss",
            "source_endpoint": "/app/operation-test4/reconcile-once",
            "order_source": "operation_test4_auto_stop_loss",
            "audit_source_context": "operation_test4_position_management",
            "operation_test": "test4",
            "mode": "operation_test4_live",
            "appsecret": "must-not-appear",
            "access_token": "must-not-appear",
        }
    )

    assert metadata["source"] == "operation_test4_auto_stop_loss"
    assert metadata["order_source"] == "operation_test4_auto_stop_loss"
    assert metadata["audit_source_context"] == "operation_test4_position_management"
    assert metadata["source_endpoint"] == "/app/operation-test4/reconcile-once"
    assert metadata["mode"] == "operation_test4_live"
    assert "appsecret" not in metadata
    assert "access_token" not in metadata


def test_filled_internal_status_has_clean_display_even_when_raw_status_is_corrupt(db_session):
    order = OrderLog(
        broker="kis",
        market="KR",
        symbol="000001",
        side="sell",
        order_type="market",
        qty=1,
        requested_qty=1,
        filled_qty=1,
        remaining_qty=0,
        internal_status=InternalOrderStatus.FILLED.value,
        broker_status="\ufffd\ufffd\ufffd",
        broker_order_status="\ufffd\ufffd\ufffd",
        broker_order_id="KIS-TEST4-EXIT",
        response_payload=(
            '{"mode":"operation_test4_live",'
            '"operation_test":"test4",'
            '"order_source":"operation_test4_auto_take_profit"}'
        ),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    payload = serialize_kis_order(order)

    assert payload["internal_status"] == "FILLED"
    assert payload["broker_status_raw"] == "\ufffd\ufffd\ufffd"
    assert payload["broker_status_display"] == "Filled"
    assert payload["display_status"] == "Filled"
    assert payload["mode"] == "operation_test4_live"