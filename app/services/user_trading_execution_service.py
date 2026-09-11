from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.brokers.user_alpaca_client import (
    UserAlpacaLiveExecutionBlocked,
    UserAlpacaTradingClient,
)
from app.core.enums import InternalOrderStatus
from app.db.models import (
    OrderLog,
    PositionLifecycle,
    SignalLog,
    TradeRunLog,
    User,
    UserTradingSettings,
)
from app.services.market_session_service import MarketSessionService
from app.services.order_service import map_broker_status_to_internal, normalize_broker_status
from app.services.user_broker_account_service import UserBrokerAccountService
from app.services.user_broker_credential_service import UserBrokerCredentialService
from app.services.user_risk_state_service import UserRiskStateService, normalize_trading_scope
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService


PAPER_MODE = "paper"
LIVE_MODE = "live"
REGULAR_USER_LIVE_BLOCK = "regular_user_live_execution_disabled"
KIS_SIMULATION_MODE = "kis_user_simulation"
ALPACA_PAPER_MODE = "alpaca_user_paper"
USER_TRIGGER_SOURCE = "user_run_once"
MIN_ENTRY_SCORE = 65.0
_TERMINAL_ORDER_STATUSES = {
    InternalOrderStatus.FILLED.value,
    InternalOrderStatus.CANCELED.value,
    "CANCELLED",
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.EXPIRED.value,
    InternalOrderStatus.FAILED.value,
}


class UserTradingExecutionService:
    """Manual regular-user paper/simulation execution with ownership isolation."""

    def __init__(
        self,
        *,
        account_service: UserBrokerAccountService | None = None,
        credential_service: UserBrokerCredentialService | None = None,
        analysis_service: UserSymbolAnalysisService | None = None,
        risk_service: UserRiskStateService | None = None,
        session_service: MarketSessionService | None = None,
        alpaca_client_factory: Callable[[dict[str, Any]], Any] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.account_service = account_service or UserBrokerAccountService()
        self.credential_service = credential_service or UserBrokerCredentialService()
        self.analysis_service = analysis_service or UserSymbolAnalysisService(
            session_service=session_service,
        )
        self.risk_service = risk_service or UserRiskStateService()
        self.session_service = session_service or MarketSessionService()
        self.alpaca_client_factory = alpaca_client_factory or UserAlpacaTradingClient
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def run_once(
        self,
        db: Session,
        user: User,
        *,
        provider: str,
        symbol: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = self._utc_now(now)
        normalized_provider, market, currency, _timezone = normalize_trading_scope(
            provider,
            None,
        )
        requested_symbol = self._normalize_symbol(normalized_provider, symbol)
        settings = self._settings(db, user)
        selected_mode = str(settings.trading_mode or PAPER_MODE).strip().lower()
        if selected_mode not in {PAPER_MODE, LIVE_MODE}:
            selected_mode = PAPER_MODE

        run = self._create_run(
            db,
            user=user,
            provider=normalized_provider,
            market=market,
            symbol=requested_symbol,
            selected_mode=selected_mode,
            request_payload={
                "provider": normalized_provider,
                "market": market,
                "requested_symbol": requested_symbol,
                "trading_mode": selected_mode,
                "trigger_source": USER_TRIGGER_SOURCE,
            },
        )

        base = {
            "provider": normalized_provider,
            "market": market,
            "currency": currency,
            "trading_mode": selected_mode,
            "owner_user_id": int(user.id),
            "requested_symbol": requested_symbol,
            "analyzed_symbol": requested_symbol,
            "returned_symbol": requested_symbol,
            "symbol_match": True,
            "real_order_submitted": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "order_id": None,
            "signal_id": None,
            "run_id": run.id,
        }

        if selected_mode == LIVE_MODE:
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason=REGULAR_USER_LIVE_BLOCK,
                message="실거래 주문은 아직 비활성화되어 있습니다.",
                analysis={"action": "hold", "reason": REGULAR_USER_LIVE_BLOCK},
                risk={"risk_allowed": False, "risk_flags": [REGULAR_USER_LIVE_BLOCK]},
            )

        if not bool(settings.enabled):
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason="user_trading_disabled",
                analysis={"action": "hold", "reason": "user_trading_disabled"},
                risk={"risk_allowed": False, "risk_flags": ["user_trading_disabled"]},
            )
        if not bool(settings.paper_trading_enabled):
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason="paper_trading_disabled",
                analysis={"action": "hold", "reason": "paper_trading_disabled"},
                risk={"risk_allowed": False, "risk_flags": ["paper_trading_disabled"]},
            )
        if bool(settings.live_trading_enabled):
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason=REGULAR_USER_LIVE_BLOCK,
                analysis={"action": "hold", "reason": REGULAR_USER_LIVE_BLOCK},
                risk={"risk_allowed": False, "risk_flags": [REGULAR_USER_LIVE_BLOCK]},
            )

        credentials: dict[str, Any] | None = None
        if normalized_provider == "alpaca":
            try:
                credentials = self.credential_service.get_credentials(db, user, "alpaca")
            except Exception as exc:
                return self._finish_blocked(
                    db,
                    run,
                    user=user,
                    base=base,
                    reason=self._credential_reason(exc),
                    analysis={"action": "hold", "reason": self._credential_reason(exc)},
                    risk={"risk_allowed": False, "risk_flags": [self._credential_reason(exc)]},
                )
            if str(credentials.get("environment") or "").strip().lower() != PAPER_MODE:
                return self._finish_blocked(
                    db,
                    run,
                    user=user,
                    base=base,
                    reason=REGULAR_USER_LIVE_BLOCK,
                    message="실거래 주문은 아직 비활성화되어 있습니다.",
                    analysis={"action": "hold", "reason": REGULAR_USER_LIVE_BLOCK},
                    risk={"risk_allowed": False, "risk_flags": [REGULAR_USER_LIVE_BLOCK]},
                )

        try:
            snapshot = self.account_service.get_broker_snapshot(db, user, normalized_provider)
        except Exception as exc:
            reason = self._account_reason(exc)
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason=reason,
                analysis={"action": "hold", "reason": reason},
                risk={"risk_allowed": False, "risk_flags": [reason]},
            )

        try:
            market_session = self.session_service.get_session_status(market, now=now_utc)
        except Exception:
            market_session = {"market": market, "is_market_open": False, "is_entry_allowed_now": False}

        try:
            analysis = self.analysis_service.analyze(
                db,
                provider=normalized_provider,
                symbol=requested_symbol,
                gate_level=2,
                now=now_utc,
            )
        except Exception as exc:
            analysis = {
                "action": "hold",
                "reason": "analysis_unavailable",
                "gating_notes": [f"{exc.__class__.__name__}: {str(exc)[:160]}"],
                "hard_blocked": True,
            }
        analysis = dict(analysis or {})
        analyzed_symbol = str(analysis.get("analyzed_symbol") or analysis.get("symbol") or "").strip().upper()
        returned_symbol = str(analysis.get("returned_symbol") or analysis.get("symbol") or "").strip().upper()
        symbol_match = bool(analyzed_symbol == requested_symbol == returned_symbol)
        base.update(
            {
                "analyzed_symbol": analyzed_symbol or requested_symbol,
                "returned_symbol": returned_symbol or analyzed_symbol or requested_symbol,
                "symbol_match": symbol_match,
                "analysis": analysis,
                "market_session": market_session,
            }
        )

        risk = self.risk_service.get_user_risk_state(
            db,
            user,
            provider=normalized_provider,
            market=market,
            as_of=now_utc,
        )
        risk = dict(risk or {})
        risk_flags = [str(flag) for flag in risk.get("risk_flags") or []]
        self._append_snapshot_risk_flags(
            risk_flags,
            snapshot=snapshot,
            symbol=requested_symbol,
            max_open_positions=int(settings.max_open_positions or 0),
            db=db,
            user=user,
        )
        if market_session.get("is_market_open") is not True:
            risk_flags.append("market_closed")
        if market_session.get("is_entry_allowed_now") is not True:
            risk_flags.append("market_entry_not_allowed")
        if self._past_user_cutoff(settings.no_new_entry_after, market_session):
            risk_flags.append("after_no_new_entry_time")
        if not symbol_match:
            risk_flags.append("symbol_mismatch")
        risk["risk_flags"] = _dedupe(risk_flags)
        risk["risk_allowed"] = not risk["risk_flags"]
        base["risk"] = risk

        if risk["risk_flags"]:
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason=risk["risk_flags"][0],
                analysis=analysis,
                risk=risk,
            )

        if self._is_hold(analysis):
            return self._finish_hold(
                db,
                run,
                user=user,
                base=base,
                analysis=analysis,
                risk=risk,
                reason=str(analysis.get("reason") or "hold_signal"),
            )

        price = _number(analysis.get("current_price") or (analysis.get("indicator_payload") or {}).get("price"))
        sizing = self._size_order(
            snapshot=snapshot,
            price=price,
            max_position_pct=float(settings.max_position_pct or 0),
        )
        base["sizing"] = sizing
        if sizing.get("reason"):
            return self._finish_blocked(
                db,
                run,
                user=user,
                base=base,
                reason=str(sizing["reason"]),
                analysis=analysis,
                risk=risk,
            )

        if normalized_provider == "kis":
            return self._simulate_kis(
                db,
                run,
                user=user,
                base=base,
                analysis=analysis,
                risk=risk,
                sizing=sizing,
                now=now_utc,
            )
        return self._submit_alpaca_paper(
            db,
            run,
            user=user,
            base=base,
            analysis=analysis,
            risk=risk,
            sizing=sizing,
            credentials=credentials or {},
            now=now_utc,
        )

    def _simulate_kis(self, db, run, *, user, base, analysis, risk, sizing, now):
        order = self._create_order(
            db,
            user=user,
            provider="kis",
            market="KR",
            symbol=base["requested_symbol"],
            qty=sizing["quantity"],
            notional=sizing["notional"],
            internal_status=InternalOrderStatus.DRY_RUN_SIMULATED.value,
            request_payload={
                "provider": "kis",
                "market": "KR",
                "mode": KIS_SIMULATION_MODE,
                "simulated": True,
                "requested_symbol": base["requested_symbol"],
                "analyzed_symbol": base["analyzed_symbol"],
                "returned_symbol": base["returned_symbol"],
                "symbol_match": base["symbol_match"],
                "qty": sizing["quantity"],
                "notional": sizing["notional"],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
            response_payload={
                "result": "simulated",
                "reason": "kis_paper_simulation",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
        )
        signal = self._create_signal(
            db,
            user=user,
            base=base,
            analysis=analysis,
            risk=risk,
            result="simulated",
            order_id=order.id,
        )
        order.request_payload = self._json_merge(order.request_payload, {"signal_id": signal.id})
        run.signal_id = signal.id
        run.order_id = order.id
        response = {
            **base,
            "result": "simulated",
            "reason": "kis_paper_simulation",
            "signal_id": signal.id,
            "order_id": order.id,
            "execution": {
                "type": "simulation",
                "status": "simulated",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
        }
        return self._finish_run(db, run, response)

    def _submit_alpaca_paper(
        self,
        db,
        run,
        *,
        user,
        base,
        analysis,
        risk,
        sizing,
        credentials,
        now,
    ):
        order = self._create_order(
            db,
            user=user,
            provider="alpaca",
            market="US",
            symbol=base["requested_symbol"],
            qty=sizing["quantity"],
            notional=sizing["notional"],
            internal_status=InternalOrderStatus.REQUESTED.value,
            request_payload={
                "provider": "alpaca",
                "market": "US",
                "mode": ALPACA_PAPER_MODE,
                "paper": True,
                "credential_environment": "paper",
                "requested_symbol": base["requested_symbol"],
                "analyzed_symbol": base["analyzed_symbol"],
                "returned_symbol": base["returned_symbol"],
                "symbol_match": base["symbol_match"],
                "qty": sizing["quantity"],
                "notional": sizing["notional"],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
        )
        broker_called = False
        try:
            client = self.alpaca_client_factory(credentials)
            broker_called = True
            broker_order = client.submit_market_buy_qty(
                symbol=base["requested_symbol"],
                qty=sizing["quantity"],
            )
            self._apply_broker_order(db, order, broker_order)
            status_value = str(order.internal_status or "").upper()
            real_submitted = status_value not in {InternalOrderStatus.FAILED.value, InternalOrderStatus.REJECTED.value}
            response_payload = {
                "result": "submitted" if real_submitted else "blocked",
                "reason": "alpaca_paper_order_submitted" if real_submitted else "alpaca_paper_order_rejected",
                "provider": "alpaca",
                "market": "US",
                "paper": True,
                "real_order_submitted": real_submitted,
                "broker_submit_called": broker_called,
                "manual_submit_called": False,
                "broker_order_id": order.broker_order_id,
                "broker_status": order.broker_status,
            }
            order.response_payload = json.dumps(response_payload, ensure_ascii=False, default=str)
            self._maybe_create_position_lifecycle(db, user=user, order=order, now=now)
            signal = self._create_signal(
                db,
                user=user,
                base=base,
                analysis=analysis,
                risk=risk,
                result="submitted" if real_submitted else "blocked",
                order_id=order.id if real_submitted else None,
            )
            order.request_payload = self._json_merge(order.request_payload, {"signal_id": signal.id})
            run.signal_id = signal.id
            run.order_id = order.id if real_submitted else None
            response = {
                **base,
                "result": "submitted" if real_submitted else "blocked",
                "reason": response_payload["reason"],
                "signal_id": signal.id,
                "order_id": order.id,
                "real_order_submitted": real_submitted,
                "broker_submit_called": broker_called,
                "manual_submit_called": False,
                "execution": response_payload,
            }
            return self._finish_run(db, run, response)

        except UserAlpacaLiveExecutionBlocked:
            order.internal_status = InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
            order.error_message = REGULAR_USER_LIVE_BLOCK
            order.response_payload = json.dumps(
                {"reason": REGULAR_USER_LIVE_BLOCK, "broker_submit_called": False},
                ensure_ascii=False,
            )
            db.commit()
            return self._finish_blocked(
                db,
                run,
                user=user,
                base={**base, "broker_submit_called": False},
                reason=REGULAR_USER_LIVE_BLOCK,
                analysis=analysis,
                risk=risk,
            )
        except Exception as exc:
            order.internal_status = InternalOrderStatus.FAILED.value
            order.error_message = self._safe_error(exc)
            order.response_payload = json.dumps(
                {
                    "reason": "alpaca_paper_submit_failed",
                    "broker_submit_called": broker_called,
                    "real_order_submitted": False,
                },
                ensure_ascii=False,
            )
            db.commit()
            signal = self._create_signal(
                db,
                user=user,
                base={**base, "broker_submit_called": broker_called},
                analysis=analysis,
                risk=risk,
                result="failed",
                order_id=None,
            )
            run.signal_id = signal.id
            run.order_id = None
            response = {
                **base,
                "result": "failed",
                "reason": "alpaca_paper_submit_failed",
                "signal_id": signal.id,
                "order_id": order.id,
                "broker_submit_called": broker_called,
                "execution": {
                    "type": "alpaca_paper",
                    "status": "failed",
                    "real_order_submitted": False,
                    "broker_submit_called": broker_called,
                    "manual_submit_called": False,
                },
            }
            return self._finish_run(db, run, response)

    @staticmethod
    def _settings(db: Session, user: User) -> UserTradingSettings:
        row = (
            db.query(UserTradingSettings)
            .filter(UserTradingSettings.user_id == int(user.id))
            .first()
        )
        if row is None:
            row = UserTradingSettings(
                user_id=int(user.id),
                trading_mode=PAPER_MODE,
                enabled=False,
                paper_trading_enabled=False,
                live_trading_enabled=False,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def _normalize_symbol(provider: str, symbol: str) -> str:
        normalized = str(symbol or "").strip().upper()
        if provider == "kis":
            if not re.fullmatch(r"\d{1,6}", normalized):
                raise ValueError("invalid_kis_symbol")
            return normalized.zfill(6)
        if not re.fullmatch(r"[A-Z0-9.\-]{1,20}", normalized):
            raise ValueError("invalid_alpaca_symbol")
        return normalized

    def _create_run(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        market: str,
        symbol: str,
        selected_mode: str,
        request_payload: dict[str, Any],
    ) -> TradeRunLog:
        row = TradeRunLog(
            owner_user_id=int(user.id),
            run_key=f"user_{uuid.uuid4().hex[:16]}",
            trigger_source=USER_TRIGGER_SOURCE,
            symbol=symbol,
            mode=selected_mode,
            stage="precheck",
            result="pending",
            reason="user_run_started",
            request_payload=json.dumps(
                {**request_payload, "provider": provider, "market": market},
                ensure_ascii=False,
                default=str,
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _create_signal(
        self,
        db: Session,
        *,
        user: User,
        base: dict[str, Any],
        analysis: dict[str, Any],
        risk: dict[str, Any],
        result: str,
        order_id: int | None,
    ) -> SignalLog:
        signal = SignalLog(
            owner_user_id=int(user.id),
            symbol=str(base["requested_symbol"]),
            action=str(analysis.get("action") or "hold"),
            buy_score=_number(analysis.get("final_buy_score") or analysis.get("score")),
            sell_score=_number(analysis.get("final_sell_score")),
            confidence=_number(analysis.get("confidence")),
            reason=str(analysis.get("reason") or result),
            indicator_payload=json.dumps(analysis.get("indicator_payload") or {}, ensure_ascii=False, default=str),
            quant_buy_score=_number(analysis.get("quant_buy_score")),
            quant_sell_score=_number(analysis.get("quant_sell_score")),
            ai_buy_score=_number(analysis.get("ai_buy_score")),
            ai_sell_score=_number(analysis.get("ai_sell_score")),
            final_buy_score=_number(analysis.get("final_buy_score") or analysis.get("score")),
            final_sell_score=_number(analysis.get("final_sell_score")),
            quant_reason=analysis.get("quant_reason"),
            ai_reason=analysis.get("ai_reason") or analysis.get("gpt_reason"),
            risk_flags=json.dumps(risk.get("risk_flags") or [], ensure_ascii=False),
            approved_by_risk=bool(risk.get("risk_allowed")) if risk else False,
            related_order_id=order_id,
            signal_status=result,
            trigger_source=USER_TRIGGER_SOURCE,
            timeframe="user_run_once",
            gate_level=2,
            hard_block_reason=analysis.get("block_reason") or (risk.get("risk_flags") or [None])[0],
            hard_blocked=bool(analysis.get("hard_blocked")),
            gating_notes=json.dumps(analysis.get("gating_notes") or [], ensure_ascii=False, default=str),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    @staticmethod
    def _create_order(
        db: Session,
        *,
        user: User,
        provider: str,
        market: str,
        symbol: str,
        qty: float,
        notional: float,
        internal_status: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any] | None = None,
    ) -> OrderLog:
        row = OrderLog(
            owner_user_id=int(user.id),
            broker=provider,
            market=market,
            symbol=symbol,
            side="buy",
            order_type="market",
            time_in_force="day",
            qty=float(qty),
            requested_qty=float(qty),
            remaining_qty=float(qty),
            notional=float(notional),
            currency="KRW" if market == "KR" else "USD",
            internal_status=internal_status,
            request_payload=json.dumps(request_payload, ensure_ascii=False, default=str),
            response_payload=(
                json.dumps(response_payload, ensure_ascii=False, default=str)
                if response_payload is not None
                else None
            ),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _apply_broker_order(db: Session, row: OrderLog, broker_order: Any) -> None:
        status = normalize_broker_status(_broker_value(broker_order, "status"))
        row.broker_order_id = _text(_broker_value(broker_order, "id") or _broker_value(broker_order, "order_id"))
        row.client_order_id = _text(_broker_value(broker_order, "client_order_id"))
        row.broker_status = status
        row.broker_order_status = status
        row.internal_status = map_broker_status_to_internal(status)
        row.filled_qty = _number(_broker_value(broker_order, "filled_qty")) or 0.0
        row.remaining_qty = max(float(row.requested_qty or row.qty or 0) - float(row.filled_qty or 0), 0.0)
        row.filled_avg_price = _number(_broker_value(broker_order, "filled_avg_price"))
        row.avg_fill_price = row.filled_avg_price
        row.submitted_at = _broker_datetime(broker_order, "submitted_at")
        row.filled_at = _broker_datetime(broker_order, "filled_at")
        row.canceled_at = _broker_datetime(broker_order, "canceled_at")
        row.response_payload = json.dumps(_safe_broker_payload(broker_order), ensure_ascii=False, default=str)
        db.commit()
        db.refresh(row)

    @staticmethod
    def _maybe_create_position_lifecycle(db: Session, *, user: User, order: OrderLog, now: datetime) -> None:
        status = str(order.internal_status or "").upper()
        filled_qty = float(order.filled_qty or 0.0)
        if filled_qty <= 0 and status == InternalOrderStatus.FILLED.value:
            filled_qty = float(order.qty or 0.0)
        if filled_qty <= 0 or status not in {
            InternalOrderStatus.FILLED.value,
            InternalOrderStatus.PARTIALLY_FILLED.value,
        }:
            return
        if db.query(PositionLifecycle).filter(PositionLifecycle.entry_order_id == order.id).first():
            return
        entry_price = float(order.avg_fill_price or order.filled_avg_price or 0.0)
        if entry_price <= 0:
            return
        db.add(
            PositionLifecycle(
                owner_user_id=int(user.id),
                symbol=order.symbol,
                entry_order_id=order.id,
                entry_price=entry_price,
                cost_basis=entry_price * filled_qty,
                quantity=filled_qty,
                status="open",
                opened_at=order.filled_at or now,
                last_price=entry_price,
                stop_loss_threshold_pct=0.02,
                take_profit_threshold_pct=0.04,
            )
        )
        db.commit()

    def _append_snapshot_risk_flags(
        self,
        risk_flags: list[str],
        *,
        snapshot: dict[str, Any],
        symbol: str,
        max_open_positions: int,
        db: Session,
        user: User,
    ) -> None:
        account = snapshot.get("account") if isinstance(snapshot, dict) else {}
        account = account if isinstance(account, dict) else {}
        positions = snapshot.get("positions") if isinstance(snapshot, dict) else []
        positions = positions if isinstance(positions, list) else []
        open_positions = [
            item for item in positions
            if isinstance(item, dict) and abs(_number(item.get("quantity")) or 0.0) > 0
        ]
        current = next(
            (
                item for item in open_positions
                if str(item.get("symbol") or "").strip().upper() == symbol
            ),
            None,
        )
        if current is not None:
            risk_flags.append("duplicate_position")
        if max_open_positions <= len(open_positions):
            risk_flags.append("max_open_positions_reached")

        open_orders = snapshot.get("open_orders") if isinstance(snapshot, dict) else []
        open_orders = open_orders if isinstance(open_orders, list) else []
        for item in open_orders:
            if not isinstance(item, dict):
                continue
            if str(item.get("symbol") or "").strip().upper() != symbol:
                continue
            status = str(item.get("status") or "").strip().upper()
            if status not in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "FILLED"}:
                risk_flags.append("duplicate_open_order")
                break

        local_rows = (
            db.query(OrderLog)
            .filter(OrderLog.owner_user_id == int(user.id), OrderLog.symbol == symbol)
            .order_by(OrderLog.id.desc())
            .limit(10)
            .all()
        )
        if any(str(row.internal_status or "").upper() not in _TERMINAL_ORDER_STATUSES for row in local_rows):
            risk_flags.append("duplicate_open_order")

        buying_power = _number(account.get("buying_power") or account.get("cash"))
        if buying_power is None or buying_power <= 0:
            risk_flags.append("buying_power_unavailable")

    @staticmethod
    def _size_order(*, snapshot: dict[str, Any], price: float | None, max_position_pct: float) -> dict[str, Any]:
        account = snapshot.get("account") if isinstance(snapshot, dict) else {}
        account = account if isinstance(account, dict) else {}
        portfolio_value = _number(
            account.get("portfolio_value")
            or account.get("equity")
            or account.get("total_asset_value")
        )
        buying_power = _number(account.get("buying_power") or account.get("cash"))
        if portfolio_value is None or portfolio_value <= 0:
            return {"reason": "portfolio_value_unavailable"}
        if buying_power is None or buying_power <= 0:
            return {"reason": "buying_power_unavailable"}
        if price is None or price <= 0:
            return {"reason": "current_price_unavailable"}
        if max_position_pct <= 0:
            return {"reason": "max_position_pct_invalid"}
        current_exposure = 0.0
        for position in snapshot.get("positions") or []:
            if isinstance(position, dict):
                current_exposure += max(0.0, _number(position.get("market_value")) or 0.0)
        target_notional = portfolio_value * (max_position_pct / 100.0)
        exposure_room = max(portfolio_value - current_exposure, 0.0)
        target_notional = min(target_notional, buying_power, exposure_room)
        quantity = math.floor(target_notional / price)
        if quantity <= 0:
            return {"reason": "quantity_invalid", "target_notional": target_notional}
        notional = round(quantity * price, 2)
        return {
            "portfolio_value": portfolio_value,
            "buying_power": buying_power,
            "current_exposure": current_exposure,
            "max_position_pct": max_position_pct,
            "target_notional": target_notional,
            "quantity": int(quantity),
            "price": price,
            "notional": notional,
        }

    @staticmethod
    def _is_hold(analysis: dict[str, Any]) -> bool:
        action = str(analysis.get("action") or "hold").strip().lower()
        if action in {"hold", "skip", "blocked", "sell", ""}:
            return True
        if bool(analysis.get("hard_blocked")):
            return True
        score = _number(analysis.get("final_buy_score") or analysis.get("score"))
        return action != "buy" or score is None or score < MIN_ENTRY_SCORE

    @staticmethod
    def _past_user_cutoff(cutoff: Any, market_session: dict[str, Any]) -> bool:
        text = str(cutoff or "").strip()
        local_time = str(market_session.get("local_time") or "").strip()
        if not text or not local_time:
            return False
        try:
            current = datetime.fromisoformat(local_time.replace("Z", "+00:00")).time()
            hour, minute = [int(value) for value in text.split(":", 1)]
            return (current.hour, current.minute, current.second) >= (hour, minute, 0)
        except (TypeError, ValueError):
            return False

    def _finish_blocked(self, db, run, *, user, base, reason, analysis, risk, message=None):
        signal = self._create_signal(
            db,
            user=user,
            base=base,
            analysis=analysis,
            risk=risk,
            result="blocked",
            order_id=None,
        )
        run.signal_id = signal.id
        response = {
            **base,
            "result": "blocked",
            "reason": reason,
            "message": message or reason,
            "signal_id": signal.id,
            "order_id": None,
            "analysis": analysis,
            "risk": risk,
            "execution": {
                "type": "none",
                "status": "blocked",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
        }
        return self._finish_run(db, run, response)

    def _finish_hold(self, db, run, *, user, base, analysis, risk, reason):
        signal = self._create_signal(
            db,
            user=user,
            base=base,
            analysis=analysis,
            risk=risk,
            result="hold",
            order_id=None,
        )
        run.signal_id = signal.id
        response = {
            **base,
            "result": "hold",
            "reason": reason or "hold_signal",
            "message": "주문 없음",
            "signal_id": signal.id,
            "order_id": None,
            "analysis": analysis,
            "risk": risk,
            "execution": {
                "type": "none",
                "status": "hold",
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            },
        }
        return self._finish_run(db, run, response)

    @staticmethod
    def _finish_run(db, run, response: dict[str, Any]) -> dict[str, Any]:
        run.stage = "done"
        run.result = str(response.get("result") or "blocked")
        run.reason = str(response.get("reason") or "")
        run.response_payload = json.dumps(response, ensure_ascii=False, default=str)
        db.commit()
        db.refresh(run)
        response["run"] = {
            "id": run.id,
            "run_key": run.run_key,
            "owner_user_id": run.owner_user_id,
            "result": run.result,
            "reason": run.reason,
            "signal_id": run.signal_id,
            "order_id": run.order_id,
            "created_at": run.created_at,
        }
        return response

    @staticmethod
    def _json_merge(raw: str | None, values: dict[str, Any]) -> str:
        try:
            current = json.loads(raw or "{}")
        except (TypeError, ValueError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        return json.dumps(current, ensure_ascii=False, default=str)

    @staticmethod
    def _utc_now(value: datetime | None) -> datetime:
        current = value or datetime.now(UTC)
        if current.tzinfo is None:
            return current.replace(tzinfo=UTC)
        return current.astimezone(UTC)

    @staticmethod
    def _credential_reason(exc: Exception) -> str:
        text = str(exc).strip()
        return text if text in {"broker_credentials_not_configured", "broker_environment_invalid"} else "broker_credentials_unavailable"

    @staticmethod
    def _account_reason(exc: Exception) -> str:
        text = str(exc).strip()
        if text == "broker_credentials_not_configured":
            return text
        if text in {"broker_authentication_failed", "broker_unavailable"}:
            return text
        return "account_snapshot_unavailable"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        return text[:180]


def _number(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _broker_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _broker_datetime(value: Any, key: str):
    raw = _broker_value(value, key)
    return raw if isinstance(raw, datetime) else None


def _safe_broker_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        source = value
    elif hasattr(value, "model_dump"):
        source = value.model_dump()
    elif hasattr(value, "dict"):
        source = value.dict()
    else:
        source = {"id": _broker_value(value, "id"), "status": _broker_value(value, "status")}
    allowed = {
        "id", "status", "client_order_id", "symbol", "qty", "filled_qty",
        "filled_avg_price", "submitted_at", "filled_at", "canceled_at",
    }
    return {key: source.get(key) for key in allowed if source.get(key) is not None}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
