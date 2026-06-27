from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from app.db.models import (
    KisOrderValidationLog,
    OrderLog,
    SignalLog,
    StrategyAutoBuyPromotion,
    StrategyLiveAutoBuyAttempt,
    TradeRunLog,
)
from app.core.enums import InternalOrderStatus
from app.schemas.strategy_live_auto_buy import ProfileAwareGuardedLiveAutoBuyRunRequest
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)


class FakeRuntimeSettings(RuntimeSettingService):
    def __init__(self, **overrides):
        super().__init__()
        self.settings = type(
            "Settings",
            (),
            {
                "dry_run": overrides.pop("global_dry_run", True),
                "default_symbol": "AAPL",
                "kis_enabled": overrides.pop("kis_enabled", True),
                "kis_real_order_enabled": overrides.pop("kis_real_order_enabled", True),
                "kis_env": "prod",
            },
        )()
        self.overrides = overrides

    def get_settings(self, db):
        values = super().get_settings(db)
        values.update(self.overrides)
        return values

    def get_settings_read_only(self, db):
        values = super().get_settings_read_only(db)
        values.update(self.overrides)
        return values


class FakeTargetRisk:
    def __init__(self, *, approved: bool = True, block_reason: str | None = None):
        self.approved = approved
        self.block_reason = block_reason
        self.calls: list[dict] = []

    def evaluate_entry(self, db, request, *, profile_name=None):
        self.calls.append({"request": dict(request), "profile_name": profile_name})
        return {
            "approved": self.approved,
            "action": "approve" if self.approved else "block",
            "active_profile": profile_name or "safe",
            "symbol": request["symbol"],
            "approved_notional_krw": 30_000 if self.approved else 0,
            "recommended_notional_krw": 30_000,
            "total_assets_krw": 1_000_000,
            "block_reason": self.block_reason,
            "risk_flags": [self.block_reason] if self.block_reason else [],
            "gating_notes": ["target-aware risk reran"],
            "profile_thresholds": {"max_order_notional_pct": 0.02},
        }


@dataclass(frozen=True)
class FakeValidationResult:
    provider: str = "kis"
    market: str = "KR"
    environment: str = "prod"
    dry_run: bool = True
    validated_for_submission: bool = True
    can_submit_later: bool = True
    block_reasons: list[str] | None = None
    primary_block_reason: str | None = None
    symbol: str = "005930"
    company_name: str = "Samsung Electronics"
    side: str = "buy"
    qty: int = 3
    order_type: str = "market"
    current_price: float = 10_000
    estimated_amount: float = 30_000
    available_cash: float = 1_000_000
    held_qty: float | None = None
    warnings: list[str] | None = None
    market_session: dict | None = None
    order_preview: dict | None = None
    source_metadata: dict | None = None
    message: str | None = None
    detail: dict | None = None

    def to_dict(self):
        payload = asdict(self)
        payload.update(
            {
                "can_submit_later": self.validated_for_submission,
                "warnings": self.warnings or [],
                "block_reasons": self.block_reasons or [],
                "market_session": self.market_session or {
                    "market": "KR",
                    "is_market_open": True,
                    "is_entry_allowed_now": True,
                    "is_near_close": False,
                },
                "order_preview": self.order_preview or {
                    "account_no_masked": "1234****",
                    "product_code": "01",
                    "symbol": self.symbol,
                    "side": self.side,
                    "qty": self.qty,
                    "order_type": self.order_type,
                    "kis_tr_id_preview": "TTTC0802U",
                    "payload_preview": {},
                },
            }
        )
        return payload


class FakeValidationService:
    def __init__(self, result: FakeValidationResult | None = None):
        self.result = result or FakeValidationResult()
        self.calls = []

    def validate(self, request):
        self.calls.append(request)
        return self.result


class FakeBroker:
    def __init__(self):
        self.calls: list[dict] = []

    def submit_market_buy(self, *, symbol: str, qty: int):
        self.calls.append({"symbol": symbol, "qty": qty})
        return {"order_id": "KIS-ORDER-1", "status": "accepted"}


class FakeOrderSyncService:
    def __init__(self):
        self.calls: list[int] = []

    def sync_order(self, db, order_id: int):
        self.calls.append(order_id)
        order = db.get(OrderLog, order_id)
        order.internal_status = InternalOrderStatus.FILLED.value
        order.broker_status = "filled"
        order.broker_order_status = "filled"
        order.broker_order_id = order.broker_order_id or "KIS-ORDER-1"
        return order


def live_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    risk: FakeTargetRisk | None = None,
    validation: FakeValidationService | None = None,
    broker: FakeBroker | None = None,
    order_sync_service: FakeOrderSyncService | None = None,
    positions=None,
    balance=None,
    open_orders=None,
):
    return ProfileAwareGuardedLiveAutoBuyService(
        runtime_settings=runtime or FakeRuntimeSettings(),
        target_risk_service=risk or FakeTargetRisk(),
        validation_service=validation or FakeValidationService(),
        broker=broker or FakeBroker(),
        order_sync_service=order_sync_service,
        positions_loader=lambda db: list(positions if positions is not None else []),
        balance_loader=lambda db: dict(balance or {"cash": 1_000_000}),
        open_orders_loader=lambda db: list(open_orders if open_orders is not None else []),
    )


def enable_live_settings(db_session):
    RuntimeSettingService().update_settings(
        db_session,
        {
            "dry_run": False,
            "kill_switch": False,
            "strategy_live_auto_buy_enabled": True,
            "strategy_live_auto_buy_max_orders_per_day": 1,
            "strategy_live_auto_buy_max_notional_krw": 50_000,
            "strategy_live_auto_buy_max_notional_pct": 0.03,
            "strategy_live_auto_buy_scheduler_enabled": False,
        },
    )


def add_dry_run(
    db_session,
    *,
    action: str = "would_buy",
    created_at: datetime | None = None,
    symbol: str = "005930",
) -> TradeRunLog:
    payload = {
        "provider": "kis",
        "market": "KR",
        "action": action,
        "active_profile": "safe",
        "selected_symbol": symbol,
        "selected_symbol_name": "Samsung Electronics",
        "buy_score": 80,
        "sell_score": 20,
        "final_score": 80,
        "confidence": 0.8,
        "recommended_notional_krw": 30_000,
        "simulated_price": 10_000,
        "simulated_quantity": 3,
        "signal_id": 123,
        "target_risk_result": {"approved": True},
    }
    row = TradeRunLog(
        run_key=f"dry-run-{symbol}-{datetime.now(UTC).timestamp()}",
        trigger_source="profile_aware_dry_run_auto_buy",
        symbol=symbol,
        mode="strategy_dry_run_auto_buy",
        stage="done",
        result=action,
        reason=action,
        response_payload=json.dumps(payload),
        created_at=created_at or datetime.now(UTC),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def live_request(**overrides) -> ProfileAwareGuardedLiveAutoBuyRunRequest:
    values = {
        "provider": "kis",
        "market": "KR",
        "confirm_operator_ack": True,
        "trigger_source": "pytest",
    }
    values.update(overrides)
    return ProfileAwareGuardedLiveAutoBuyRunRequest(**values)


def add_promotion_for_dry_run(
    db_session,
    dry_run: TradeRunLog,
    *,
    now: datetime | None = None,
    ttl_minutes: int = 45,
) -> dict:
    payload = json.loads(dry_run.response_payload)
    payload["trade_run_id"] = dry_run.id
    payload["signal_id"] = payload.get("signal_id") or 123
    return StrategyAutoBuyPromotionService().create_from_dry_run(
        db_session,
        dry_run_result=payload,
        request_payload={"source": "pytest"},
        now=now or datetime.now(UTC),
        ttl_minutes=ttl_minutes,
    )


def test_default_readiness_is_blocked_read_only_and_does_not_validate_or_submit(db_session):
    validation = FakeValidationService()
    broker = FakeBroker()
    result = live_service(validation=validation, broker=broker).readiness(db_session)

    assert result["ready"] is False
    assert result["enabled"] is False
    assert result["primary_block_reason"] == "strategy_live_auto_buy_disabled"
    assert result["safety"]["read_only"] is True
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["broker_submit_called"] is False
    assert validation.calls == []
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 0
    assert db_session.query(OrderLog).count() == 0


def test_run_once_blocks_when_recent_dry_run_is_missing_without_validation_or_submit(db_session):
    enable_live_settings(db_session)
    validation = FakeValidationService()
    broker = FakeBroker()

    result = live_service(validation=validation, broker=broker).run_once(
        db_session,
        live_request(),
    )

    assert result["status"] == "blocked"
    assert result["block_reason"] == "recent_dry_run_missing"
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["broker_submit_called"] is False
    assert validation.calls == []
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoBuyAttempt).one().block_reason == "recent_dry_run_missing"


def test_run_once_blocks_when_recent_dry_run_is_stale(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session, created_at=datetime.now(UTC) - timedelta(minutes=45))

    result = live_service().run_once(db_session, live_request())

    assert result["status"] == "blocked"
    assert result["block_reason"] == "recent_dry_run_expired"
    assert db_session.query(OrderLog).count() == 0


def test_run_once_revalidates_target_risk_validates_kis_and_submits_once(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    risk = FakeTargetRisk()
    validation = FakeValidationService()
    broker = FakeBroker()

    result = live_service(risk=risk, validation=validation, broker=broker).run_once(
        db_session,
        live_request(source_dry_run_id=dry_run.id, client_request_id="once-1"),
    )

    assert result["status"] == "submitted"
    assert result["submitted"] is True
    assert result["source_dry_run_id"] == dry_run.id
    assert result["target_risk_approved"] is True
    assert result["validation_approved"] is True
    assert result["broker_order_id"] == "KIS-ORDER-1"
    assert result["safety"]["validation_called"] is True
    assert result["safety"]["broker_submit_called"] is True
    assert result["safety"]["manual_submit_called"] is False
    assert result["safety"]["scheduler_changed"] is False
    assert risk.calls[0]["request"]["dry_run"] is False
    assert validation.calls[0].dry_run is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(StrategyLiveAutoBuyAttempt).one().status == "submitted"
    assert db_session.query(OrderLog).one().internal_status == "SUBMITTED"
    assert db_session.query(SignalLog).one().trigger_source == "profile_aware_guarded_live_auto_buy"
    assert db_session.query(TradeRunLog).filter(TradeRunLog.mode == "strategy_live_auto_buy").count() == 1
    assert db_session.query(KisOrderValidationLog).count() == 1


def test_run_once_with_pending_promotion_links_attempt_order_and_payloads(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    broker = FakeBroker()

    result = live_service(broker=broker).run_once(
        db_session,
        live_request(
            promotion_id=promotion["id"],
            source_dry_run_id=dry_run.id,
            client_request_id="promotion-once",
        ),
    )

    assert result["status"] == "submitted"
    assert result["promotion_id"] == promotion["id"]
    assert result["promotion_trace"]["promotion_id"] == promotion["id"]
    assert result["promotion_trace"]["source_dry_run_id"] == dry_run.id
    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert row.status == "live_order_created"
    assert row.converted_live_attempt_id == result["attempt_id"]
    assert row.converted_order_id == result["related_order_id"]
    assert row.conversion_status == "live_order_created"
    attempt_payload = json.loads(
        db_session.query(StrategyLiveAutoBuyAttempt).one().request_payload
    )
    order = db_session.query(OrderLog).one()
    order_payload = json.loads(order.request_payload)
    order_response = json.loads(order.response_payload)
    assert attempt_payload["promotion_trace"]["promotion_id"] == promotion["id"]
    assert order_payload["promotion_trace"]["promotion_id"] == promotion["id"]
    assert order_response["promotion_trace"]["converted_order_id"] == result["related_order_id"]


def test_reviewed_promotion_still_requires_final_operator_confirmation(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    promotion_service = StrategyAutoBuyPromotionService()
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    promotion_service.mark_reviewed(db_session, promotion["id"])
    validation = FakeValidationService()
    broker = FakeBroker()

    result = live_service(validation=validation, broker=broker).run_once(
        db_session,
        live_request(
            promotion_id=promotion["id"],
            source_dry_run_id=dry_run.id,
            confirm_operator_ack=False,
        ),
    )

    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert result["status"] == "blocked"
    assert result["block_reason"] == "confirm_operator_ack_required"
    assert row.status == "reviewed"
    assert validation.calls == []
    assert broker.calls == []
    assert db_session.query(OrderLog).count() == 0


def test_dismissed_expired_and_converted_promotions_block_before_validation_or_submit(db_session):
    enable_live_settings(db_session)
    service = StrategyAutoBuyPromotionService()

    dismissed_dry_run = add_dry_run(db_session, symbol="005930")
    dismissed = add_promotion_for_dry_run(db_session, dismissed_dry_run)
    service.dismiss(db_session, dismissed["id"])
    dismissed_validation = FakeValidationService()
    dismissed_broker = FakeBroker()
    dismissed_result = live_service(
        validation=dismissed_validation,
        broker=dismissed_broker,
    ).run_once(
        db_session,
        live_request(
            promotion_id=dismissed["id"],
            source_dry_run_id=dismissed_dry_run.id,
        ),
    )
    assert dismissed_result["block_reason"] == "promotion_dismissed"
    assert dismissed_validation.calls == []
    assert dismissed_broker.calls == []

    expired_dry_run = add_dry_run(db_session, symbol="000660")
    expired = add_promotion_for_dry_run(
        db_session,
        expired_dry_run,
        now=datetime.now(UTC) - timedelta(minutes=10),
        ttl_minutes=1,
    )
    expired_validation = FakeValidationService()
    expired_broker = FakeBroker()
    expired_result = live_service(
        validation=expired_validation,
        broker=expired_broker,
    ).run_once(
        db_session,
        live_request(
            promotion_id=expired["id"],
            source_dry_run_id=expired_dry_run.id,
        ),
    )
    assert expired_result["block_reason"] == "promotion_expired"
    assert db_session.get(StrategyAutoBuyPromotion, expired["id"]).status == "expired"
    assert expired_validation.calls == []
    assert expired_broker.calls == []

    converted_dry_run = add_dry_run(db_session, symbol="035420")
    converted = add_promotion_for_dry_run(db_session, converted_dry_run)
    service.mark_converted(
        db_session,
        converted["id"],
        promoted_to_live_attempt_id=999,
        related_live_order_id=1000,
    )
    converted_validation = FakeValidationService()
    converted_broker = FakeBroker()
    converted_result = live_service(
        validation=converted_validation,
        broker=converted_broker,
    ).run_once(
        db_session,
        live_request(
            promotion_id=converted["id"],
            source_dry_run_id=converted_dry_run.id,
        ),
    )
    assert converted_result["block_reason"] == "promotion_already_converted"
    assert converted_validation.calls == []
    assert converted_broker.calls == []


def test_client_request_id_is_idempotent_and_does_not_submit_again(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session)
    broker = FakeBroker()
    service = live_service(broker=broker)

    first = service.run_once(db_session, live_request(client_request_id="same-request"))
    second = service.run_once(db_session, live_request(client_request_id="same-request"))

    assert first["attempt_id"] == second["attempt_id"]
    assert second["safety"]["idempotent_replay"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(StrategyLiveAutoBuyAttempt).count() == 1


def test_validation_failure_blocks_before_broker_submit(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session)
    validation = FakeValidationService(
        FakeValidationResult(
            validated_for_submission=False,
            block_reasons=["market_closed"],
            primary_block_reason="market_closed",
        )
    )
    broker = FakeBroker()

    result = live_service(validation=validation, broker=broker).run_once(
        db_session,
        live_request(),
    )

    assert result["status"] == "validation_failed"
    assert result["block_reason"] == "market_closed"
    assert result["safety"]["validation_called"] is True
    assert result["safety"]["broker_submit_called"] is False
    assert broker.calls == []
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(KisOrderValidationLog).count() == 1


def test_sync_attempt_updates_status_without_new_submit(db_session):
    enable_live_settings(db_session)
    add_dry_run(db_session)
    broker = FakeBroker()
    sync = FakeOrderSyncService()
    service = live_service(broker=broker, order_sync_service=sync)
    submitted = service.run_once(db_session, live_request(client_request_id="sync-1"))

    synced = service.sync_attempt(db_session, submitted["attempt_id"])

    assert synced["status"] == "filled"
    assert synced["safety"]["read_only"] is True
    assert synced["safety"]["sync_only"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert sync.calls == [submitted["related_order_id"]]
    assert db_session.query(StrategyLiveAutoBuyAttempt).one().status == "filled"


def test_sync_attempt_updates_promotion_trace(db_session):
    enable_live_settings(db_session)
    dry_run = add_dry_run(db_session)
    promotion = add_promotion_for_dry_run(db_session, dry_run)
    broker = FakeBroker()
    sync = FakeOrderSyncService()
    service = live_service(broker=broker, order_sync_service=sync)
    submitted = service.run_once(
        db_session,
        live_request(
            promotion_id=promotion["id"],
            source_dry_run_id=dry_run.id,
            client_request_id="promotion-sync",
        ),
    )

    synced = service.sync_attempt(db_session, submitted["attempt_id"])

    row = db_session.get(StrategyAutoBuyPromotion, promotion["id"])
    assert synced["status"] == "filled"
    assert row.status == "live_order_filled"
    assert row.last_sync_status == "filled"
    assert json.loads(row.trace_payload_json)["last_sync_status"] == "filled"
