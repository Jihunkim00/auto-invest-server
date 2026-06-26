from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.enums import InternalOrderStatus
from app.db.models import (
    OrderLog,
    StrategyLiveAutoExitAttempt,
)
from app.schemas.strategy_live_auto_exit import ProfileAwareGuardedLiveAutoExitRunRequest
from app.services.profile_aware_guarded_live_auto_exit_service import (
    ProfileAwareGuardedLiveAutoExitService,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.tests.test_strategy_live_auto_buy_service import FakeRuntimeSettings


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
    side: str = "sell"
    qty: int = 3
    order_type: str = "market"
    current_price: float = 9000
    estimated_amount: float = 27000
    available_cash: float = 1000000
    held_qty: float | None = 3
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
                "market_session": self.market_session
                or {
                    "market": "KR",
                    "is_market_open": True,
                    "is_entry_allowed_now": True,
                    "is_near_close": False,
                },
                "order_preview": self.order_preview
                or {
                    "account_no_masked": "1234****",
                    "product_code": "01",
                    "symbol": self.symbol,
                    "side": self.side,
                    "qty": self.qty,
                    "order_type": self.order_type,
                    "kis_tr_id_preview": "TTTC0801U",
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

    def submit_market_sell(self, *, symbol: str, qty: int):
        self.calls.append({"symbol": symbol, "qty": qty})
        return {"order_id": "KIS-SELL-1", "status": "accepted"}


class FakeOrderSyncService:
    def __init__(self):
        self.calls: list[int] = []

    def sync_order(self, db, order_id: int):
        self.calls.append(order_id)
        order = db.get(OrderLog, order_id)
        order.internal_status = InternalOrderStatus.FILLED.value
        order.broker_status = "filled"
        order.broker_order_status = "filled"
        order.broker_order_id = order.broker_order_id or "KIS-SELL-1"
        return order


def stop_loss_position(**overrides):
    values = {
        "symbol": "005930",
        "symbol_name": "Samsung Electronics",
        "quantity": 3,
        "current_price": 9000,
        "avg_entry_price": 10000,
        "current_value": 27000,
    }
    values.update(overrides)
    return values


def live_exit_service(
    *,
    runtime: FakeRuntimeSettings | None = None,
    validation: FakeValidationService | None = None,
    broker: FakeBroker | None = None,
    order_sync_service: FakeOrderSyncService | None = None,
    positions=None,
    open_orders=None,
):
    return ProfileAwareGuardedLiveAutoExitService(
        runtime_settings=runtime or FakeRuntimeSettings(),
        validation_service=validation or FakeValidationService(),
        broker=broker or FakeBroker(),
        order_sync_service=order_sync_service,
        positions_loader=lambda db: list(positions if positions is not None else []),
        open_orders_loader=lambda db: list(open_orders if open_orders is not None else []),
    )


def enable_live_exit_settings(db_session, **overrides):
    values = {
        "dry_run": False,
        "kill_switch": False,
        "strategy_live_auto_exit_enabled": True,
        "strategy_live_auto_exit_requires_operator_confirm": True,
        "strategy_live_auto_exit_max_orders_per_day": 1,
        "strategy_live_auto_exit_max_notional_krw": 50000,
        "strategy_live_auto_exit_max_position_pct": 1.0,
        "strategy_live_auto_exit_allow_stop_loss": True,
        "strategy_live_auto_exit_allow_take_profit": False,
        "strategy_live_auto_exit_allow_max_holding_days": False,
        "strategy_live_auto_exit_allow_monthly_loss_exit": True,
        "strategy_live_auto_exit_allow_target_hit_reduce": False,
        "strategy_live_auto_exit_scheduler_enabled": False,
        "strategy_live_auto_exit_requires_cost_basis": True,
        "strategy_live_auto_exit_min_quantity": 1,
    }
    values.update(overrides)
    RuntimeSettingService().update_settings(db_session, values)


def live_exit_request(**overrides) -> ProfileAwareGuardedLiveAutoExitRunRequest:
    values = {
        "provider": "kis",
        "market": "KR",
        "confirm_operator_ack": True,
        "trigger_source": "pytest",
    }
    values.update(overrides)
    return ProfileAwareGuardedLiveAutoExitRunRequest(**values)


def test_default_readiness_is_blocked_read_only_and_does_not_validate_or_submit(db_session):
    validation = FakeValidationService()
    broker = FakeBroker()
    result = live_exit_service(
        validation=validation,
        broker=broker,
        positions=[stop_loss_position()],
    ).readiness(db_session)

    assert result["ready"] is False
    assert result["enabled"] is False
    assert result["primary_block_reason"] == "strategy_live_auto_exit_disabled"
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["trigger"] == "stop_loss"
    assert result["safety"]["read_only"] is True
    assert result["safety"]["validation_called"] is False
    assert result["safety"]["broker_submit_called"] is False
    assert validation.calls == []
    assert broker.calls == []
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 0


def test_missing_cost_basis_blocks_before_validation(db_session):
    enable_live_exit_settings(db_session)
    validation = FakeValidationService()
    broker = FakeBroker()
    service = live_exit_service(
        validation=validation,
        broker=broker,
        positions=[stop_loss_position(avg_entry_price=None, current_value=27000)],
    )

    result = service.run_once(db_session, live_exit_request())

    assert result["status"] == "blocked"
    assert result["block_reason"] == "cost_basis_unavailable"
    assert result["safety"]["validation_called"] is False
    assert validation.calls == []
    assert broker.calls == []


def test_stop_loss_candidate_submits_after_validation(db_session):
    enable_live_exit_settings(db_session)
    validation = FakeValidationService()
    broker = FakeBroker()
    service = live_exit_service(
        validation=validation,
        broker=broker,
        positions=[stop_loss_position()],
    )

    result = service.run_once(db_session, live_exit_request(client_request_id="exit-1"))

    assert result["status"] == "submitted"
    assert result["submitted"] is True
    assert result["exit_trigger"] == "stop_loss"
    assert result["quantity"] == 3
    assert validation.calls
    assert validation.calls[0].side == "sell"
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
    assert db_session.query(StrategyLiveAutoExitAttempt).count() == 1


def test_take_profit_is_blocked_when_disabled_by_default(db_session):
    enable_live_exit_settings(db_session)
    validation = FakeValidationService()
    broker = FakeBroker()
    service = live_exit_service(
        validation=validation,
        broker=broker,
        positions=[stop_loss_position(current_price=10500, current_value=31500)],
    )

    result = service.run_once(db_session, live_exit_request())

    assert result["status"] == "blocked"
    assert result["block_reason"] == "take_profit_disabled"
    assert validation.calls == []
    assert broker.calls == []


def test_client_request_id_replays_without_second_submit(db_session):
    enable_live_exit_settings(db_session)
    validation = FakeValidationService()
    broker = FakeBroker()
    service = live_exit_service(
        validation=validation,
        broker=broker,
        positions=[stop_loss_position()],
    )

    first = service.run_once(db_session, live_exit_request(client_request_id="same-exit"))
    second = service.run_once(db_session, live_exit_request(client_request_id="same-exit"))

    assert first["status"] == "submitted"
    assert second["attempt_id"] == first["attempt_id"]
    assert second["safety"]["idempotent_replay"] is True
    assert broker.calls == [{"symbol": "005930", "qty": 3}]
