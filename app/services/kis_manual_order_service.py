from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.brokers.factory import mask_account_no
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.core.enums import InternalOrderStatus
from app.db.models import KisOrderValidationLog, OrderLog
from app.services.market_profile_service import MarketProfileError, MarketProfileService
from app.services.market_session_service import MarketSessionError, MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService

KIS_MANUAL_CONFIRMATION_PHRASE = "I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER"
KIS_VALIDATION_MAX_AGE = timedelta(minutes=5)
KR_TZ = ZoneInfo("Asia/Seoul")

SUBMITTED_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}

STRUCTURAL_CHECKS = {
    "market_is_kr",
    "symbol_is_kr_6_digit",
    "side_is_supported",
    "qty_is_positive_integer",
    "order_type_is_market",
}


class KisManualOrderSubmitRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    market: str = Field(default="KR", examples=["KR"])
    symbol: str = Field(examples=["005930"])
    side: str = Field(examples=["buy"])
    qty: int = Field(examples=[1])
    order_type: str = Field(default="market", examples=["market"])
    dry_run: bool = Field(default=True)
    confirmation: str | None = Field(default=None, max_length=300)
    reason: str | None = Field(default=None, max_length=500)


class KisManualOrderService:
    def __init__(
        self,
        client: KisClient,
        *,
        broker: KisBroker | None = None,
        profile_service: MarketProfileService | None = None,
        session_service: MarketSessionService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
    ):
        self.client = client
        self.broker = broker or KisBroker(client)
        self.profile_service = profile_service or MarketProfileService()
        self.session_service = session_service or MarketSessionService()
        self.runtime_settings = runtime_settings or RuntimeSettingService()

    def submit_manual(
        self,
        db: Session,
        request: KisManualOrderSubmitRequest,
        *,
        now: datetime | None = None,
    ) -> tuple[int, dict[str, Any]]:
        now_utc = _utc_now(now)
        normalized_market = str(request.market or "").strip().upper()
        normalized_side = str(request.side or "").strip().lower()
        normalized_order_type = str(request.order_type or "").strip().lower()
        raw_symbol = str(request.symbol or "").strip()
        normalized_symbol = raw_symbol

        checks: dict[str, dict[str, Any]] = {}

        def check(name: str, passed: bool, reason: str, detail: Any = None):
            item = {"passed": bool(passed), "reason": None if passed else reason}
            if detail is not None:
                item["detail"] = detail
            checks[name] = item

        check(
            "market_is_kr",
            normalized_market == "KR",
            "market_must_be_KR",
            normalized_market or None,
        )

        symbol_valid = bool(re.fullmatch(r"\d{6}", raw_symbol))
        if symbol_valid:
            try:
                normalized_symbol = self.profile_service.normalize_symbol(raw_symbol, "KR")
            except MarketProfileError as exc:
                symbol_valid = False
                check("symbol_is_kr_6_digit", False, "invalid_kr_symbol", str(exc))
            else:
                check("symbol_is_kr_6_digit", True, "invalid_kr_symbol")
        else:
            check("symbol_is_kr_6_digit", False, "symbol_must_be_6_digit_kr_code")

        check(
            "side_is_supported",
            normalized_side in {"buy", "sell"},
            "side_must_be_buy_or_sell",
            normalized_side or None,
        )
        check(
            "qty_is_positive_integer",
            isinstance(request.qty, int) and request.qty > 0,
            "qty_must_be_positive_integer",
            request.qty,
        )
        check(
            "order_type_is_market",
            normalized_order_type == "market",
            "order_type_must_be_market",
            normalized_order_type or None,
        )

        settings = self.client.settings
        runtime = self.runtime_settings.get_settings(db)

        check(
            "kis_enabled",
            bool(getattr(settings, "kis_enabled", False)),
            "kis_enabled_false",
        )
        check(
            "kis_real_order_enabled",
            bool(getattr(settings, "kis_real_order_enabled", False)),
            "kis_real_order_enabled_false",
        )
        check(
            "dry_run_false",
            request.dry_run is False and bool(runtime.get("dry_run", True)) is False,
            "dry_run_must_be_false",
            {
                "request_dry_run": request.dry_run,
                "runtime_dry_run": runtime.get("dry_run", True),
            },
        )
        check(
            "kill_switch_false",
            bool(runtime.get("kill_switch", False)) is False,
            "kill_switch_enabled",
        )

        try:
            profile = self.profile_service.get_profile("KR")
            profile_enabled = bool(profile.enabled_for_trading)
            profile_detail = profile.to_dict()
        except MarketProfileError as exc:
            profile_enabled = False
            profile_detail = str(exc)
        check(
            "kr_trading_profile_enabled",
            profile_enabled,
            "kr_trading_profile_disabled",
            profile_detail,
        )

        try:
            market_session = self.session_service.get_session_status("KR", now=now_utc)
        except MarketSessionError as exc:
            market_session = {}
            check("kr_market_open", False, "market_session_unavailable", str(exc))
            check("buy_entry_allowed_now", False, "market_session_unavailable")
            check("today_not_holiday", False, "market_session_unavailable")
        else:
            check(
                "kr_market_open",
                market_session.get("is_market_open") is True,
                "market_closed",
                _public_market_session(market_session),
            )
            if normalized_side == "buy":
                entry_allowed = market_session.get("is_entry_allowed_now") is True
            else:
                entry_allowed = True
            check(
                "buy_entry_allowed_now",
                entry_allowed,
                "buy_entry_not_allowed_now",
                _public_market_session(market_session),
            )
            is_holiday = bool(market_session.get("is_holiday"))
            closure_reason = str(market_session.get("closure_reason") or "")
            if closure_reason.startswith("holiday_"):
                is_holiday = True
            check(
                "today_not_holiday",
                not is_holiday,
                "today_is_holiday",
                _public_market_session(market_session),
            )

        latest_validation = None
        if (
            checks["market_is_kr"]["passed"]
            and checks["symbol_is_kr_6_digit"]["passed"]
            and checks["side_is_supported"]["passed"]
            and checks["qty_is_positive_integer"]["passed"]
            and checks["order_type_is_market"]["passed"]
        ):
            latest_validation = self._latest_recent_validation(
                db,
                market=normalized_market,
                symbol=normalized_symbol,
                side=normalized_side,
                qty=request.qty,
                order_type=normalized_order_type,
                now_utc=now_utc,
            )
        check(
            "recent_dry_run_validation_passed",
            latest_validation is not None,
            "recent_dry_run_validation_missing",
            {"max_age_seconds": int(KIS_VALIDATION_MAX_AGE.total_seconds())},
        )

        max_qty = int(getattr(settings, "kis_max_manual_order_qty", 1))
        qty_cap_disabled = max_qty <= 0
        qty_cap_passed = checks["qty_is_positive_integer"]["passed"] and (
            qty_cap_disabled or request.qty <= max_qty
        )
        qty_cap_detail = {"qty": request.qty, "cap_disabled": qty_cap_disabled}
        if not qty_cap_disabled:
            qty_cap_detail["max_qty"] = max_qty

        check(
            "max_order_qty_cap",
            qty_cap_passed,
            "qty_exceeds_manual_cap",
            qty_cap_detail,
        )

        estimated_amount = (
            float(latest_validation.estimated_amount)
            if latest_validation is not None and latest_validation.estimated_amount is not None
            else None
        )
        max_amount = float(getattr(settings, "kis_max_manual_order_amount_krw", 100000))
        cap_disabled = max_amount <= 0
        amount_cap_passed = cap_disabled or (
            estimated_amount is not None and estimated_amount <= max_amount
        )
        amount_cap_detail = {
            "estimated_amount": estimated_amount,
            "cap_disabled": cap_disabled,
        }
        if not cap_disabled:
            amount_cap_detail["max_amount_krw"] = max_amount

        check(
            "max_order_amount_cap",
            amount_cap_passed,
            "amount_exceeds_manual_cap" if estimated_amount is not None else "amount_unavailable",
            amount_cap_detail,
        )

        max_daily_trades = max(0, int(runtime.get("max_trades_per_day", 0)))
        daily_count = self._daily_kis_trade_count(db, now_utc=now_utc)
        check(
            "daily_trade_limit",
            daily_count < max_daily_trades,
            "daily_trade_limit_reached",
            {"daily_count": daily_count, "max_trades_per_day": max_daily_trades},
        )

        confirmation_phrase = str(
            getattr(settings, "kis_confirmation_phrase", KIS_MANUAL_CONFIRMATION_PHRASE)
            or KIS_MANUAL_CONFIRMATION_PHRASE
        )
        confirmation_required = bool(getattr(settings, "kis_require_confirmation", True))
        confirmation_matches = request.confirmation == confirmation_phrase
        check(
            "manual_confirmation_matches",
            confirmation_required and confirmation_matches,
            (
                "manual_confirmation_missing_or_invalid"
                if confirmation_required
                else "manual_confirmation_requirement_disabled"
            ),
            {"confirmation_required": confirmation_required},
        )

        failed_checks = [
            name for name, item in checks.items() if item.get("passed") is not True
        ]
        if failed_checks:
            status_code = 400 if STRUCTURAL_CHECKS.intersection(failed_checks) else 409
            response = self._base_response(
                request=request,
                normalized_market=normalized_market or request.market,
                normalized_symbol=normalized_symbol,
                normalized_side=normalized_side,
                normalized_order_type=normalized_order_type,
                real_order_submitted=False,
                internal_status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
                safety_checks=checks,
                failed_checks=failed_checks,
                broker_order_id=None,
                broker_status=None,
            )
            order = self._create_order_log(
                db,
                request=request,
                symbol=normalized_symbol,
                side=normalized_side,
                order_type=normalized_order_type,
                notional=estimated_amount,
                internal_status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
                response_payload=response,
            )
            response["order_log_id"] = order.id
            order.response_payload = json.dumps(response, ensure_ascii=False, default=str)
            db.commit()
            return status_code, response

        order = self._create_order_log(
            db,
            request=request,
            symbol=normalized_symbol,
            side=normalized_side,
            order_type=normalized_order_type,
            notional=estimated_amount,
            internal_status=InternalOrderStatus.REQUESTED.value,
            response_payload=None,
        )

        try:
            if normalized_side == "buy":
                broker_response = self.broker.submit_market_buy(
                    symbol=normalized_symbol,
                    qty=request.qty,
                )
            else:
                broker_response = self.broker.submit_market_sell(
                    symbol=normalized_symbol,
                    qty=request.qty,
                )
        except Exception as exc:
            response = self._base_response(
                request=request,
                normalized_market=normalized_market,
                normalized_symbol=normalized_symbol,
                normalized_side=normalized_side,
                normalized_order_type=normalized_order_type,
                real_order_submitted=False,
                internal_status=InternalOrderStatus.FAILED.value,
                safety_checks=checks,
                failed_checks=[],
                broker_order_id=None,
                broker_status="failed",
            )
            response["error"] = _safe_error(exc)
            response["order_log_id"] = order.id
            order.internal_status = InternalOrderStatus.FAILED.value
            order.broker_status = "failed"
            order.error_message = _safe_error(exc)
            order.response_payload = json.dumps(response, ensure_ascii=False, default=str)
            db.commit()
            return 502, response

        broker_order_id = _extract_broker_order_id(broker_response)
        broker_status = _extract_broker_status(broker_response)
        response = self._base_response(
            request=request,
            normalized_market=normalized_market,
            normalized_symbol=normalized_symbol,
            normalized_side=normalized_side,
            normalized_order_type=normalized_order_type,
            real_order_submitted=True,
            internal_status=InternalOrderStatus.SUBMITTED.value,
            safety_checks=checks,
            failed_checks=[],
            broker_order_id=broker_order_id,
            broker_status=broker_status,
        )
        response["order_log_id"] = order.id
        order.internal_status = InternalOrderStatus.SUBMITTED.value
        order.broker_status = broker_status
        order.broker_order_id = broker_order_id
        order.submitted_at = datetime.now(UTC)
        order.response_payload = json.dumps(
            {
                **response,
                "kis_response": _sanitize_payload(broker_response),
            },
            ensure_ascii=False,
            default=str,
        )
        db.commit()
        return 200, response

    def _latest_recent_validation(
        self,
        db: Session,
        *,
        market: str,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        now_utc: datetime,
    ) -> KisOrderValidationLog | None:
        cutoff = _naive_utc(now_utc - KIS_VALIDATION_MAX_AGE)
        return (
            db.query(KisOrderValidationLog)
            .filter(KisOrderValidationLog.market == market)
            .filter(KisOrderValidationLog.symbol == symbol)
            .filter(KisOrderValidationLog.side == side)
            .filter(KisOrderValidationLog.qty == qty)
            .filter(KisOrderValidationLog.order_type == order_type)
            .filter(KisOrderValidationLog.validated_for_submission.is_(True))
            .filter(KisOrderValidationLog.created_at >= cutoff)
            .order_by(KisOrderValidationLog.created_at.desc(), KisOrderValidationLog.id.desc())
            .first()
        )

    def _daily_kis_trade_count(self, db: Session, *, now_utc: datetime) -> int:
        local_now = now_utc.astimezone(KR_TZ)
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = _naive_utc(start_local.astimezone(UTC))
        end_utc = _naive_utc(end_local.astimezone(UTC))
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == "kis")
            .filter(OrderLog.created_at >= start_utc)
            .filter(OrderLog.created_at < end_utc)
            .filter(OrderLog.internal_status.in_(sorted(SUBMITTED_STATUSES)))
            .count()
        )

    def _create_order_log(
        self,
        db: Session,
        *,
        request: KisManualOrderSubmitRequest,
        symbol: str,
        side: str,
        order_type: str,
        notional: float | None,
        internal_status: str,
        response_payload: dict[str, Any] | None,
    ) -> OrderLog:
        order_payload_preview = None
        if re.fullmatch(r"\d{6}", symbol or "") and side in {"buy", "sell"}:
            try:
                payload = self.client.build_domestic_order_payload(
                    symbol=symbol,
                    side=side,
                    qty=request.qty,
                    order_type=order_type,
                )
                order_payload_preview = _sanitize_payload(payload)
            except Exception:
                order_payload_preview = None

        row = OrderLog(
            broker="kis",
            symbol=symbol or str(request.symbol or ""),
            side=side or str(request.side or ""),
            order_type=order_type or str(request.order_type or ""),
            time_in_force="day",
            qty=float(request.qty) if isinstance(request.qty, int) else None,
            notional=notional,
            limit_price=None,
            extended_hours=False,
            internal_status=internal_status,
            request_payload=json.dumps(
                {
                    "market": request.market,
                    "symbol": request.symbol,
                    "side": request.side,
                    "qty": request.qty,
                    "order_type": request.order_type,
                    "dry_run": request.dry_run,
                    "reason": request.reason,
                    "confirmation_provided": bool(request.confirmation),
                    "order_payload_preview": order_payload_preview,
                },
                ensure_ascii=False,
                default=str,
            ),
            response_payload=(
                json.dumps(response_payload, ensure_ascii=False, default=str)
                if response_payload
                else None
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _base_response(
        *,
        request: KisManualOrderSubmitRequest,
        normalized_market: str,
        normalized_symbol: str,
        normalized_side: str,
        normalized_order_type: str,
        real_order_submitted: bool,
        internal_status: str,
        safety_checks: dict[str, dict[str, Any]],
        failed_checks: list[str],
        broker_order_id: str | None,
        broker_status: str | None,
    ) -> dict[str, Any]:
        return {
            "provider": "kis",
            "market": normalized_market,
            "real_order_submitted": real_order_submitted,
            "symbol": normalized_symbol or request.symbol,
            "side": normalized_side or request.side,
            "qty": request.qty,
            "order_type": normalized_order_type or request.order_type,
            "broker_order_id": broker_order_id,
            "broker_status": broker_status,
            "internal_status": internal_status,
            "safety_checks": safety_checks,
            "failed_checks": failed_checks,
            "block_reasons": [
                str(safety_checks[name].get("reason"))
                for name in failed_checks
                if safety_checks[name].get("reason")
            ],
        }


def _public_market_session(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "is_holiday",
        "regular_open",
        "regular_close",
        "effective_close",
        "no_new_entry_after",
    ]
    return {key: market_session.get(key) for key in keys}


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}"


def _extract_broker_order_id(response: dict[str, Any]) -> str | None:
    output = response.get("output")
    if isinstance(output, list) and output:
        output = output[0]
    if not isinstance(output, dict):
        output = response
    value = (
        output.get("ODNO")
        or output.get("odno")
        or output.get("order_id")
        or output.get("ORD_NO")
        or output.get("ord_no")
    )
    return str(value) if value is not None and str(value).strip() else None


def _extract_broker_status(response: dict[str, Any]) -> str:
    rt_cd = str(response.get("rt_cd", "0"))
    if rt_cd in {"0", ""}:
        return "submitted"
    return str(response.get("msg_cd") or rt_cd)


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(token in normalized_key for token in ("secret", "token", "approval")):
                sanitized[key] = "***"
            elif key == "CANO" or "account" in normalized_key:
                sanitized[key] = mask_account_no(str(item)) if item is not None else None
            elif key == "authorization":
                sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value
