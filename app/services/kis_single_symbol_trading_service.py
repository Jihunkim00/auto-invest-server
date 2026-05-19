from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import SignalLog, TradeRunLog
from app.services.entry_readiness_service import evaluate_entry_readiness
from app.services.kis_manual_order_service import (
    KIS_MANUAL_CONFIRMATION_PHRASE,
    KisManualOrderService,
    KisManualOrderSubmitRequest,
)
from app.services.kis_order_validation_service import (
    KisOrderValidationRequest,
    KisOrderValidationService,
    record_kis_order_validation,
)
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import KisWatchlistPreviewService
from app.services.market_profile_service import MarketProfileService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "kis_single_symbol_analyze_buy"
SOURCE = "kis_single_symbol_analyze_buy"
SOURCE_TYPE = "manual_guarded_single_symbol_buy"
TRIGGER_SOURCE = "manual_kis_single_symbol"
PROVIDER = "kis"
MARKET = "KR"


class KisSingleSymbolTradingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(min_length=1, examples=["005930"])
    gate_level: int | None = Field(default=None, ge=1, le=4)
    quantity: int | None = Field(default=None, gt=0)
    amount: float | None = Field(default=None, gt=0)
    confirm_live: bool = Field(default=False)
    trigger_source: str | None = Field(default=TRIGGER_SOURCE)
    mode: str | None = Field(default=MODE)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        symbol = str(value or "").strip().upper()
        if not re.fullmatch(r"\d{1,6}", symbol):
            raise ValueError("KIS symbol must be numeric.")
        return symbol.zfill(6)

    @model_validator(mode="after")
    def validate_size(self) -> "KisSingleSymbolTradingRequest":
        if self.quantity is None and self.amount is None:
            raise ValueError("quantity or amount is required for KIS Analyze & Buy.")
        return self


class KisSingleSymbolTradingService:
    """Manual one-shot KIS single-symbol analyze and conditional buy flow."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        profile_service: MarketProfileService | None = None,
        preview_service: KisWatchlistPreviewService | None = None,
        validation_service: KisOrderValidationService | None = None,
        manual_order_service: KisManualOrderService | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.profile_service = profile_service or MarketProfileService()
        self.preview_service = preview_service or KisWatchlistPreviewService(
            client,
            profile_service=self.profile_service,
            session_service=self.session_service,
        )
        self.validation_service = validation_service or KisOrderValidationService(
            client,
            profile_service=self.profile_service,
            session_service=self.session_service,
        )
        self.manual_order_service = manual_order_service or KisManualOrderService(
            client,
            profile_service=self.profile_service,
            session_service=self.session_service,
            runtime_settings=self.runtime_settings,
        )

    def run_once(
        self,
        db: Session,
        request: KisSingleSymbolTradingRequest,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        created_at = now_utc.isoformat()
        runtime = self.runtime_settings.get_settings(db)
        settings = get_settings()
        gate_level = int(
            request.gate_level
            or runtime.get("default_gate_level")
            or DEFAULT_GATE_LEVEL
        )
        requested_symbol = self.profile_service.normalize_symbol(request.symbol, MARKET)
        market_session = self._market_session(now_utc)
        analysis = self._analyze_symbol(
            db,
            symbol=requested_symbol,
            gate_level=gate_level,
            market_session=market_session,
        )
        analyzed_symbol = _symbol(analysis) or requested_symbol
        symbol_match = analyzed_symbol == requested_symbol
        quantity = self._quantity_from_request(request, analysis)
        validation_payload: dict[str, Any] | None = None
        validation_error: str | None = None
        if quantity is not None and quantity > 0:
            validation_payload, validation_error = self._validate_order(
                db,
                symbol=requested_symbol,
                quantity=quantity,
                gate_level=gate_level,
                confirm_live=request.confirm_live,
                runtime=runtime,
                analysis=analysis,
                now=now_utc,
            )

        readiness = self._entry_readiness(
            analysis,
            gate_level=gate_level,
            settings=settings,
        )
        safety = _safety_summary(
            runtime=runtime,
            settings=settings,
            market_session=market_session,
            confirm_live=request.confirm_live,
            quantity=quantity,
            validation=validation_payload,
        )
        block_reason = self._block_reason(
            request=request,
            runtime=runtime,
            settings=settings,
            market_session=market_session,
            symbol_match=symbol_match,
            quantity=quantity,
            readiness=readiness,
            validation=validation_payload,
            validation_error=validation_error,
        )
        action = "buy" if readiness.get("entry_ready") and block_reason is None else "hold"
        result = "blocked" if block_reason else "skipped"
        reason = block_reason or str(readiness.get("block_reason") or "hold_signal")
        order_result: dict[str, Any] | None = None

        if block_reason is None:
            if bool(runtime.get("dry_run", True)):
                result = "dry_run"
                action = "buy"
                reason = "dry_run_mode"
            else:
                status_code, order_result = self._submit_manual(
                    db,
                    symbol=requested_symbol,
                    quantity=quantity or 0,
                    gate_level=gate_level,
                    confirm_live=request.confirm_live,
                    runtime=runtime,
                    analysis=analysis,
                )
                if status_code == 200 and order_result.get("real_order_submitted"):
                    result = "executed"
                    action = "buy"
                    reason = "submitted"
                else:
                    result = "rejected"
                    action = "buy"
                    reason = str(
                        order_result.get("primary_block_reason")
                        or order_result.get("reason")
                        or order_result.get("message")
                        or "manual_submit_rejected"
                    )

        payload = self._payload(
            request=request,
            gate_level=gate_level,
            requested_symbol=requested_symbol,
            analyzed_symbol=analyzed_symbol,
            symbol_match=symbol_match,
            quantity=quantity,
            action=action,
            result=result,
            reason=reason,
            analysis=analysis,
            readiness=readiness,
            safety=safety,
            validation=validation_payload,
            validation_error=validation_error,
            order_result=order_result,
            runtime=runtime,
            market_session=market_session,
            created_at=created_at,
        )
        signal = self._create_signal(
            db,
            payload=payload,
            analysis=analysis,
            readiness=readiness,
            gate_level=gate_level,
        )
        run = self._create_run(
            db,
            payload={**payload, "signal_id": signal.id},
            gate_level=gate_level,
            signal_id=signal.id,
            order_id=_order_id(payload),
        )
        signal.related_order_id = _order_id(payload)
        payload["signal_id"] = signal.id
        payload["run"] = _serialize_run(run)
        db.commit()
        return sanitize_kis_payload(payload)

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "timezone": "Asia/Seoul",
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _analyze_symbol(
        self,
        db: Session,
        *,
        symbol: str,
        gate_level: int,
        market_session: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            references = self.profile_service.load_reference_sites(MARKET)
            reference_sources = references.get("sources") or []
        except Exception:
            reference_sources = []
        try:
            warnings = self.preview_service._session_warnings(market_session)
        except Exception:
            warnings = []
        raw = {"symbol": symbol, "market": MARKET}
        try:
            analysis = self.preview_service._preview_symbol(
                raw,
                gate_level=gate_level,
                market_session=market_session,
                session_warnings=warnings,
                reference_sources=reference_sources,
                include_gpt=True,
                db=db,
            )
        except Exception as exc:
            analysis = {
                "symbol": symbol,
                "market": MARKET,
                "provider": PROVIDER,
                "action": "hold",
                "reason": "analysis_unavailable",
                "block_reason": "analysis_unavailable",
                "risk_flags": ["analysis_unavailable"],
                "gating_notes": [_safe_error(exc)],
                "entry_ready": False,
                "trade_allowed": False,
            }
        return self._normalize_analysis(analysis, requested_symbol=symbol)

    def _normalize_analysis(
        self,
        analysis: dict[str, Any],
        *,
        requested_symbol: str,
    ) -> dict[str, Any]:
        payload = dict(analysis or {})
        payload["requested_symbol"] = requested_symbol
        payload["analyzed_symbol"] = _symbol(payload) or requested_symbol
        payload["provider"] = PROVIDER
        payload["market"] = MARKET
        payload["preview_only"] = False
        payload["trading_enabled"] = True
        payload["dry_run"] = False
        payload["risk_flags"] = [
            item
            for item in _string_list(payload.get("risk_flags"))
            if item not in {"kr_trading_disabled", "preview_only"}
        ]
        payload["gating_notes"] = [
            item
            for item in _string_list(payload.get("gating_notes"))
            if "preview" not in item.lower()
            and "trading is disabled" not in item.lower()
            and "No real KIS order submitted." not in item
        ]
        payload["gating_notes"].append(
            "Single-symbol KIS analysis used the operator-selected symbol only."
        )
        return sanitize_kis_payload(payload)

    def _entry_readiness(
        self,
        analysis: dict[str, Any],
        *,
        gate_level: int,
        settings: Any,
    ) -> dict[str, Any]:
        final_buy = _score(analysis, "final_buy_score", "final_entry_score", "score")
        final_sell = _score(analysis, "final_sell_score", "quant_sell_score")
        buy_score = _score(analysis, "quant_buy_score", "quant_score", "score")
        sell_score = _score(analysis, "quant_sell_score")
        has_indicators = final_buy is not None or buy_score is not None
        return evaluate_entry_readiness(
            has_indicators=has_indicators,
            hard_blocked=_bool(analysis.get("hard_blocked")),
            entry_score=final_buy or 0,
            buy_score=buy_score or final_buy or 0,
            sell_score=sell_score or final_sell or 0,
            gate_level=gate_level,
            min_entry_score=float(getattr(settings, "watchlist_min_entry_score", 65)),
            max_sell_score=float(getattr(settings, "watchlist_max_sell_score", 25)),
            gating_notes=_string_list(analysis.get("gating_notes")),
            risk_flags=_string_list(analysis.get("risk_flags")),
            # KIS preview analysis is read-only and reports action=hold by design.
            # This manual endpoint lets the score/risk gate decide entry readiness.
            action=None,
            use_min_entry_score_floor=False,
        )

    def _quantity_from_request(
        self,
        request: KisSingleSymbolTradingRequest,
        analysis: dict[str, Any],
    ) -> int | None:
        if request.quantity is not None:
            return int(request.quantity)
        if request.amount is None:
            return None
        price = _score(analysis, "current_price", "price")
        if price is None or price <= 0:
            return None
        qty = int(float(request.amount) // price)
        return qty if qty > 0 else None

    def _validate_order(
        self,
        db: Session,
        *,
        symbol: str,
        quantity: int,
        gate_level: int,
        confirm_live: bool,
        runtime: dict[str, Any],
        analysis: dict[str, Any],
        now: datetime,
    ) -> tuple[dict[str, Any] | None, str | None]:
        metadata = _audit_metadata(
            symbol=symbol,
            quantity=quantity,
            gate_level=gate_level,
            confirm_live=confirm_live,
            runtime=runtime,
            analysis=analysis,
            submitted=False,
        )
        request = KisOrderValidationRequest(
            market=MARKET,
            symbol=symbol,
            side="buy",
            qty=quantity,
            order_type="market",
            dry_run=True,
            reason="KIS single-symbol Analyze & Buy validation",
            source_metadata=metadata,
        )
        try:
            result = self.validation_service.validate(request, now=now)
            record_kis_order_validation(db, request=request, result=result)
            return sanitize_kis_payload(result.to_dict()), None
        except Exception as exc:
            return None, _safe_error(exc)

    def _block_reason(
        self,
        *,
        request: KisSingleSymbolTradingRequest,
        runtime: dict[str, Any],
        settings: Any,
        market_session: dict[str, Any],
        symbol_match: bool,
        quantity: int | None,
        readiness: dict[str, Any],
        validation: dict[str, Any] | None,
        validation_error: str | None,
    ) -> str | None:
        if not symbol_match:
            return "symbol_mismatch"
        if quantity is None or quantity <= 0:
            return "quantity_or_amount_required"
        if bool(runtime.get("kill_switch", False)):
            return "kill_switch_enabled"
        if not bool(getattr(settings, "kis_enabled", False)):
            return "kis_disabled"
        if not bool(getattr(settings, "kis_real_order_enabled", False)):
            return "kis_real_order_disabled"
        if market_session.get("is_market_open") is not True:
            return "market_closed"
        if market_session.get("is_entry_allowed_now") is not True:
            return "buy_entry_not_allowed_now"
        if readiness.get("entry_ready") is not True:
            return str(readiness.get("block_reason") or "backend_risk_gate_blocked")
        if validation_error:
            return "order_validation_failed"
        if validation and validation.get("validated_for_submission") is not True:
            reasons = _string_list(validation.get("block_reasons"))
            return reasons[0] if reasons else "order_validation_failed"
        if bool(runtime.get("dry_run", True)):
            return None
        if request.confirm_live is not True:
            return "confirm_live_required"
        return None

    def _submit_manual(
        self,
        db: Session,
        *,
        symbol: str,
        quantity: int,
        gate_level: int,
        confirm_live: bool,
        runtime: dict[str, Any],
        analysis: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        settings = get_settings()
        confirmation = str(
            getattr(settings, "kis_confirmation_phrase", KIS_MANUAL_CONFIRMATION_PHRASE)
            or KIS_MANUAL_CONFIRMATION_PHRASE
        )
        payload = KisManualOrderSubmitRequest(
            market=MARKET,
            symbol=symbol,
            side="buy",
            qty=quantity,
            order_type="market",
            dry_run=False,
            confirm_live=confirm_live,
            confirmation=confirmation if confirm_live else None,
            reason="KIS single-symbol Analyze & Buy",
            source_metadata=_audit_metadata(
                symbol=symbol,
                quantity=quantity,
                gate_level=gate_level,
                confirm_live=confirm_live,
                runtime=runtime,
                analysis=analysis,
                submitted=True,
            ),
        )
        status_code, body = self.manual_order_service.submit_manual(db, payload)
        return status_code, sanitize_kis_payload(body)

    def _payload(
        self,
        *,
        request: KisSingleSymbolTradingRequest,
        gate_level: int,
        requested_symbol: str,
        analyzed_symbol: str,
        symbol_match: bool,
        quantity: int | None,
        action: str,
        result: str,
        reason: str,
        analysis: dict[str, Any],
        readiness: dict[str, Any],
        safety: dict[str, Any],
        validation: dict[str, Any] | None,
        validation_error: str | None,
        order_result: dict[str, Any] | None,
        runtime: dict[str, Any],
        market_session: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        order = order_result or {}
        real_order_submitted = order.get("real_order_submitted") is True
        broker_submit_called = order.get("broker_submit_called") is True
        manual_submit_called = order_result is not None or order.get("manual_submit_called") is True
        safety_payload = {
            **safety,
            "real_order_submitted": real_order_submitted,
            "broker_submit_called": broker_submit_called,
            "manual_submit_called": manual_submit_called,
        }
        risk_flags = _dedupe(
            _string_list(analysis.get("risk_flags"))
            + ([reason] if reason else [])
            + (["dry_run"] if result == "dry_run" else [])
        )
        gating_notes = _dedupe(
            _string_list(analysis.get("gating_notes"))
            + _string_list(order.get("failed_checks"))
            + ([validation_error] if validation_error else [])
        )
        payload = {
            "status": "ok",
            "provider": PROVIDER,
            "market": MARKET,
            "mode": MODE,
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "trigger_source": TRIGGER_SOURCE,
            "requested_symbol": requested_symbol,
            "analyzed_symbol": analyzed_symbol,
            "returned_symbol": analyzed_symbol,
            "symbol": requested_symbol,
            "symbol_match": symbol_match,
            "action": action,
            "result": result,
            "reason": reason,
            "message": _message(reason, result=result),
            "quantity": quantity,
            "qty": quantity,
            "amount": request.amount,
            "notional": order.get("notional")
            or (validation or {}).get("estimated_amount")
            or _notional(quantity, _score(analysis, "current_price")),
            "current_price": _score(analysis, "current_price"),
            "primary_score": _score(analysis, "final_buy_score", "final_entry_score", "score"),
            "final_entry_score": _score(analysis, "final_entry_score", "score"),
            "final_buy_score": _score(analysis, "final_buy_score"),
            "final_sell_score": _score(analysis, "final_sell_score"),
            "quant_buy_score": _score(analysis, "quant_buy_score", "quant_score"),
            "quant_sell_score": _score(analysis, "quant_sell_score"),
            "ai_buy_score": _score(analysis, "ai_buy_score"),
            "ai_sell_score": _score(analysis, "ai_sell_score"),
            "gpt_buy_score": _score(analysis, "gpt_buy_score", "ai_buy_score"),
            "gpt_sell_score": _score(analysis, "gpt_sell_score", "ai_sell_score"),
            "confidence": _score(analysis, "confidence"),
            "gpt_reason": analysis.get("gpt_reason"),
            "gpt_context": analysis.get("gpt_context") or {},
            "risk_flags": risk_flags,
            "gating_notes": gating_notes,
            "block_reason": reason if result in {"blocked", "skipped"} else None,
            "no_order_reason": None if result == "executed" else reason,
            "entry_ready": readiness.get("entry_ready") is True,
            "trade_allowed": result == "executed",
            "real_order_submitted": real_order_submitted,
            "broker_submit_called": broker_submit_called,
            "manual_submit_called": manual_submit_called,
            "dry_run": bool(runtime.get("dry_run", True)),
            "order_id": order.get("order_id") or order.get("order_log_id"),
            "broker_order_id": order.get("broker_order_id"),
            "kis_odno": order.get("kis_odno"),
            "order_status": _order_status(order, result=result),
            "rejection_reason": order.get("message") if result == "rejected" else None,
            "safety_summary": safety_payload,
            "safety": safety_payload,
            "checks": {
                "symbol_match": symbol_match,
                "entry_ready": readiness.get("entry_ready") is True,
                "validation_passed": validation.get("validated_for_submission")
                if validation
                else False,
                "confirm_live": request.confirm_live,
                "runtime_dry_run": bool(runtime.get("dry_run", True)),
                "kill_switch": bool(runtime.get("kill_switch", False)),
                "market_open": market_session.get("is_market_open") is True,
                "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            },
            "validation": validation,
            "validation_error": validation_error,
            "order_result": order_result,
            "analysis": analysis,
            "readiness": readiness,
            "market_session": _public_market_session(market_session),
            "audit_metadata": _audit_metadata(
                symbol=requested_symbol,
                quantity=quantity,
                gate_level=gate_level,
                confirm_live=request.confirm_live,
                runtime=runtime,
                analysis=analysis,
                submitted=order.get("real_order_submitted") is True,
            ),
            "real_order_submit_allowed": result == "executed",
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "created_at": created_at,
        }
        return sanitize_kis_payload(payload)

    def _create_signal(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        analysis: dict[str, Any],
        readiness: dict[str, Any],
        gate_level: int,
    ) -> SignalLog:
        signal = SignalLog(
            symbol=str(payload.get("symbol") or ""),
            action=str(payload.get("action") or "hold"),
            buy_score=_score(analysis, "final_buy_score", "final_entry_score", "score"),
            sell_score=_score(analysis, "final_sell_score"),
            confidence=_score(analysis, "confidence"),
            reason=str(payload.get("reason") or ""),
            indicator_payload=_json(analysis.get("indicator_payload") or {}),
            quant_buy_score=_score(analysis, "quant_buy_score", "quant_score"),
            quant_sell_score=_score(analysis, "quant_sell_score"),
            ai_buy_score=_score(analysis, "ai_buy_score"),
            ai_sell_score=_score(analysis, "ai_sell_score"),
            final_buy_score=_score(analysis, "final_buy_score", "final_entry_score", "score"),
            final_sell_score=_score(analysis, "final_sell_score"),
            quant_reason=analysis.get("quant_reason"),
            ai_reason=analysis.get("gpt_reason"),
            risk_flags=_json(payload.get("risk_flags") or []),
            approved_by_risk=payload.get("result") == "executed",
            related_order_id=_order_id(payload),
            signal_status=str(payload.get("result") or "blocked"),
            trigger_source=TRIGGER_SOURCE,
            gate_level=gate_level,
            hard_block_reason=readiness.get("block_reason"),
            hard_blocked=readiness.get("block_reason") in {"hard_blocked", "gpt_hard_block_new_buy"},
            gating_notes=_json(payload.get("gating_notes") or []),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def _create_run(
        self,
        db: Session,
        *,
        payload: dict[str, Any],
        gate_level: int,
        signal_id: int,
        order_id: int | None,
    ) -> TradeRunLog:
        run = TradeRunLog(
            run_key=f"{SOURCE}_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=str(payload.get("symbol") or ""),
            mode=MODE,
            gate_level=gate_level,
            stage="done",
            result=str(payload.get("result") or "blocked"),
            reason=str(payload.get("reason") or ""),
            signal_id=signal_id,
            order_id=order_id,
            request_payload=_json(
                {
                    "provider": PROVIDER,
                    "market": MARKET,
                    "mode": MODE,
                    "source": SOURCE,
                    "source_type": SOURCE_TYPE,
                    "symbol": payload.get("requested_symbol"),
                    "gate_level": gate_level,
                    "quantity": payload.get("quantity"),
                    "amount": payload.get("amount"),
                    "confirm_live": payload.get("checks", {}).get("confirm_live"),
                    "trigger_source": TRIGGER_SOURCE,
                }
            ),
            response_payload=_json(payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _audit_metadata(
    *,
    symbol: str,
    quantity: int | None,
    gate_level: int,
    confirm_live: bool,
    runtime: dict[str, Any],
    analysis: dict[str, Any],
    submitted: bool,
) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "source": SOURCE,
            "source_type": SOURCE_TYPE,
            "trigger_source": TRIGGER_SOURCE,
            "symbol": symbol,
            "quantity": quantity,
            "gate_level": gate_level,
            "confirm_live": confirm_live,
            "dry_run": bool(runtime.get("dry_run", True)),
            "manual_confirm_required": True,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
            "real_order_submit_allowed": submitted,
            "current_price": _score(analysis, "current_price"),
            "final_score": _score(analysis, "final_buy_score", "final_entry_score", "score"),
            "confidence": _score(analysis, "confidence"),
            "quant_score": _score(analysis, "quant_buy_score", "quant_score"),
            "gpt_buy_score": _score(analysis, "gpt_buy_score", "ai_buy_score"),
            "risk_flags": _string_list(analysis.get("risk_flags")),
            "gating_notes": _string_list(analysis.get("gating_notes")),
        }
    )


def _safety_summary(
    *,
    runtime: dict[str, Any],
    settings: Any,
    market_session: dict[str, Any],
    confirm_live: bool,
    quantity: int | None,
    validation: dict[str, Any] | None,
) -> dict[str, Any]:
    return sanitize_kis_payload(
        {
            "runtime_dry_run": bool(runtime.get("dry_run", True)),
            "dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(settings, "kis_real_order_enabled", False)
            ),
            "market_open": market_session.get("is_market_open") is True,
            "entry_allowed_now": market_session.get("is_entry_allowed_now") is True,
            "no_new_entry_after": market_session.get("no_new_entry_after"),
            "confirm_live": confirm_live,
            "quantity": quantity,
            "validation_passed": validation.get("validated_for_submission")
            if validation
            else False,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "auto_buy_enabled": False,
            "auto_sell_enabled": False,
            "scheduler_real_order_enabled": False,
        }
    )


def _message(reason: str, *, result: str) -> str:
    if result == "executed":
        return "KIS order submitted."
    if result == "dry_run":
        return "Dry-run mode: no real order submitted."
    messages = {
        "confirm_live_required": "Live confirmation is required before submit.",
        "kill_switch_enabled": "Kill switch is ON.",
        "kis_disabled": "KIS trading is disabled.",
        "kis_real_order_disabled": "KIS real order disabled.",
        "market_closed": "Market is closed.",
        "buy_entry_not_allowed_now": "New buy entries are not allowed now.",
        "score_threshold_not_met": "Score below entry threshold.",
        "symbol_mismatch": "Returned candidate does not match selected symbol.",
        "quantity_or_amount_required": "Quantity or amount is required.",
    }
    return messages.get(reason, reason)


def _order_status(order: dict[str, Any], *, result: str) -> str:
    if order.get("real_order_submitted") is True:
        return "Real order submitted"
    if result == "dry_run":
        return "Dry-run, no real order submitted"
    if result == "rejected":
        return "Rejected"
    return "No order created"


def _public_market_session(session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "regular_open",
        "regular_close",
        "effective_close",
        "no_new_entry_after",
    ]
    return {key: session.get(key) for key in keys}


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_key": row.run_key,
        "trigger_source": row.trigger_source,
        "symbol": row.symbol,
        "mode": row.mode,
        "result": row.result,
        "reason": row.reason,
        "signal_id": row.signal_id,
        "order_id": row.order_id,
        "created_at": row.created_at,
    }


def _order_id(payload: dict[str, Any]) -> int | None:
    value = payload.get("order_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _symbol(payload: dict[str, Any]) -> str:
    text = str(
        payload.get("symbol")
        or payload.get("analyzed_symbol")
        or payload.get("requested_symbol")
        or ""
    ).strip().upper()
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text


def _score(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            text = str(value).replace(",", "").strip()
            if not text or text == "null":
                continue
            return float(text)
        except (TypeError, ValueError):
            continue
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _notional(qty: int | None, price: float | None) -> float | None:
    if qty is None or price is None:
        return None
    return round(float(qty) * float(price), 2)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip()
    if len(text) > 180:
        text = f"{text[:180]}..."
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__
