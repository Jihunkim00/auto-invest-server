from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import AutomationProfileBuyReservation, OrderLog, PositionLifecycle, TradeRunLog
from app.services.kis_automation_execution_core import KisAutomationExecutionCore
from app.services.automation_execution_authority_service import AutomationExecutionAuthorityService
from app.services.kis_order_validation_service import KisOrderValidationRequest
from app.services.kis_position_lifecycle_service import CLOSED, CLOSING, OPEN, KisPositionLifecycleService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.automation_profile_service import AutomationProfileService
from app.services.profile_universe_service import (
    candidate_price,
    profile_price_exclusion_reason,
    profile_universe_bounds,
)
from app.services.automation_observability import candidate_gpt_quant_observability
from app.services.target_aware_risk_service import TargetAwareRiskService

KST = ZoneInfo('Asia/Seoul')
PROVIDER = 'kis'
MARKET = 'KR'
MODE = 'automation_profile_scheduler_buy'
TRIGGER_SOURCE = 'automation_profile_scheduler'
POSSIBLE_ORDER_MAX_AGE_SECONDS = 10.0


def build_automation_profile_buy_scheduler_service(db: Session) -> 'AutomationProfileBuySchedulerService':
    settings = get_settings()
    client = KisClient(settings, KisAuthManager(settings, db))
    from app.services.kis_order_sync_service import KisOrderSyncService
    from app.services.kis_order_validation_service import KisOrderValidationService

    return AutomationProfileBuySchedulerService(
        client=client,
        broker=KisBroker(client),
        validation_service=KisOrderValidationService(client),
        order_sync_service=KisOrderSyncService(client),
        runtime_settings=RuntimeSettingService(),
        strategy_profiles=AutomationProfileService(),
    )


class AutomationProfileBuySchedulerService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        broker: Any | None = None,
        validation_service: Any | None = None,
        order_sync_service: Any | None = None,
        lifecycle_service: Any | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        strategy_profiles: AutomationProfileService | None = None,
        target_risk_service: Any | None = None,
        positions_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
        balance_loader: Callable[[Session], dict[str, Any]] | None = None,
        open_orders_loader: Callable[[Session], list[dict[str, Any]]] | None = None,
        candidate_provider: Callable[..., Any] | None = None,
        execution_core: KisAutomationExecutionCore | None = None,
    ) -> None:
        self.client = client
        self.broker = broker
        self.validation_service = validation_service
        self.order_sync_service = order_sync_service
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.strategy_profiles = strategy_profiles or AutomationProfileService(
            runtime_settings=self.runtime_settings,
        )
        self.target_risk_service = target_risk_service or TargetAwareRiskService()
        self.positions_loader = positions_loader
        self.balance_loader = balance_loader
        self.open_orders_loader = open_orders_loader
        self.candidate_provider = candidate_provider
        self.lifecycle_service = lifecycle_service or KisPositionLifecycleService(
            client, runtime_settings=self.runtime_settings
        )
        self.execution_core = execution_core or KisAutomationExecutionCore(
            client,
            broker=broker,
            validation_service=validation_service,
            order_sync_service=order_sync_service,
            lifecycle_service=self.lifecycle_service,
            runtime_settings=self.runtime_settings,
            positions_loader=positions_loader,
            open_orders_loader=open_orders_loader,
        )

    def live_order_gate(self, db: Session) -> dict[str, Any]:
        authority_reader = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
        if authority_reader:
            authority = AutomationExecutionAuthorityService(self.runtime_settings).snapshot(db)
            runtime = self.runtime_settings.get_settings_read_only(db)
            scheduler_allowed = bool(authority.get('scheduler_allowed'))
            return {
                **authority,
                'allowed': scheduler_allowed,
                'scheduler_allowed': scheduler_allowed,
                'simulation_allowed': bool(authority.get('simulation_allowed')),
                'broker_submit_allowed': bool(authority.get('broker_submit_allowed')),
                'dry_run': bool(runtime.get('dry_run', True)),
                'kill_switch': bool(runtime.get('kill_switch', True)),
                'kis_real_order_enabled': bool(getattr(getattr(self.runtime_settings, 'settings', None), 'kis_real_order_enabled', False)),
                'runtime_authorized': bool(authority.get('broker_submit_allowed')),
                'live_order_possible': bool(authority.get('broker_submit_allowed')),
                'blocking_reasons': [] if scheduler_allowed else ['automation_mode_off'],
                'source_of_truth': 'automation_mode',
                'legacy_flags_ignored': authority.get('legacy_flags_ignored', []),
            }
        reader = getattr(self.runtime_settings, 'get_automation_profile_live_order_gate_read_only', None)
        if callable(reader):
            return dict(reader(db))
        runtime = self.runtime_settings.get_settings_read_only(db)
        app_settings = getattr(self.runtime_settings, 'settings', None)
        dry_run = bool(runtime.get('dry_run', True))
        kill_switch = bool(runtime.get('kill_switch', True))
        kis_real = bool(getattr(app_settings, 'kis_real_order_enabled', False))
        authorized = bool(runtime.get('runtime_authorized', runtime.get('real_orders_allowed', False)))
        possible = bool(runtime.get('live_order_possible', authorized and not dry_run and not kill_switch and kis_real))
        reasons = []
        if dry_run:
            reasons.append('dry_run_true')
        if kill_switch:
            reasons.append('kill_switch_enabled')
        if not kis_real:
            reasons.append('kis_real_order_disabled')
        if not authorized:
            reasons.append('runtime_not_authorized')
        if not possible:
            reasons.append('live_order_not_possible')
        return {
            'dry_run': dry_run,
            'kill_switch': kill_switch,
            'kis_real_order_enabled': kis_real,
            'runtime_authorized': authorized,
            'live_order_possible': possible,
            'allowed': not reasons,
            'blocking_reasons': reasons,
            'source_of_truth': 'automation_profile_live_order_gate',
        }

    def _active_profile(self, db: Session) -> dict[str, Any]:
        profile = self.strategy_profiles.get_active_profile(db)
        return dict(profile) if isinstance(profile, dict) else {}

    def _position_priority(self, db: Session) -> bool:
        return bool(
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.status.in_([OPEN, CLOSING]))
            .count()
        )

    def readiness(self, db: Session, *, now: datetime | None = None) -> dict[str, Any]:
        now_utc = _utc(now)
        profile = self._active_profile(db)
        runtime = self.runtime_settings.get_settings_read_only(db)
        settings = _profile_settings(profile)
        gate = self.live_order_gate(db)
        runtime['automation_profile_scheduler_enabled'] = bool(gate.get('scheduler_allowed', gate.get('allowed')))
        checks = {
            'scheduler_ready': bool(runtime.get('automation_profile_scheduler_enabled') and profile.get('enabled') and profile.get('status') == 'active'),
            'profile_ready': bool(profile.get('profile_key') and profile.get('status') == 'active'),
            'execution_core_ready': self.execution_core is not None,
            'account_read_ready': bool(self.client or self.positions_loader or self.balance_loader),
            'possible_order_path_ready': callable(getattr(self.client, 'get_domestic_possible_order', None)),
            'validation_path_ready': bool(self.validation_service or self.execution_core.validation_service),
            'order_sync_ready': bool(self.order_sync_service or self.execution_core.order_sync_service),
            'lifecycle_ready': self.lifecycle_service is not None,
        }
        blocking = [key for key, ok in checks.items() if not ok]
        return {
            'automation_mode': gate.get('automation_mode'),
            'execution_authority': gate.get('execution_authority'),
            'scheduler_allowed': bool(gate.get('scheduler_allowed')),
            'simulation_allowed': bool(gate.get('simulation_allowed')),
            'broker_submit_allowed': bool(gate.get('broker_submit_allowed')),
            'source_of_truth': gate.get('source_of_truth', 'automation_mode'),
            'authority_snapshot_source': gate.get(
                'authority_snapshot_source',
                'AutomationExecutionAuthorityService',
            ),
            'buy_ready_except_score': not blocking,
            **checks,
            'next_slot': _iso(_next_slot(now_utc, settings.get('entry', {}).get('analysis_times'))),
            'blocking_reasons': blocking,
            'hard_safety': {
                'min_final_score': 65.0,
                'possible_order_max_age_seconds': POSSIBLE_ORDER_MAX_AGE_SECONDS,
                'max_positions': 1,
                'cash_only': True,
            },
            'live_order_gate': gate,
            'live_order_conditions': {
                'dry_run_false': gate.get('dry_run') is False,
                'kill_switch_false': gate.get('kill_switch') is False,
                'kis_real_order_enabled': gate.get('kis_real_order_enabled') is True,
                'runtime_authorized': gate.get('runtime_authorized') is True,
                'live_order_possible': gate.get('live_order_possible') is True,
            },
            'safety': _safety(read_only=True),
        }

    def run_once(
        self,
        db: Session,
        candidates: Any = None,
        *,
        scheduler_slot: str | None = None,
        trigger_source: str = TRIGGER_SOURCE,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        profile = self._active_profile(db)
        if not str(trigger_source).lower().startswith(('scheduler', 'automation_profile_scheduler')):
            return self._blocked('manual_execution_isolation', profile=profile)
        if not profile.get('profile_key') or profile.get('status') != 'active':
            return self._blocked('profile_status_not_active', profile=profile)
        runtime = self.runtime_settings.get_settings(db)
        gate = self.live_order_gate(db)
        runtime['automation_profile_scheduler_enabled'] = bool(gate.get('scheduler_allowed', gate.get('allowed')))
        if not gate.get('allowed'):
            return self._blocked((gate.get('blocking_reasons') or ['automation_mode_off'])[0], profile=profile, live_order_gate=gate)
        if not runtime.get('automation_profile_scheduler_enabled'):
            return self._blocked('profile_scheduler_disabled', profile=profile)
        slot = _slot(scheduler_slot)
        settings = _profile_settings(profile)
        configured = {_slot(value) for value in settings.get('entry', {}).get('analysis_times', [])}
        if slot is None or slot not in configured:
            return self._blocked('scheduled_slot_not_configured', profile=profile)
        if now_utc.astimezone(KST).strftime('%H:%M') != slot:
            return self._blocked('missed_slot_replay_forbidden', profile=profile)
        if not gate.get('allowed'):
            return self._blocked((gate.get('blocking_reasons') or ['live_order_not_possible'])[0], profile=profile, live_order_gate=gate)
        existing_slot = (
            db.query(AutomationProfileBuyReservation)
            .filter(AutomationProfileBuyReservation.profile_key == str(profile.get('profile_key')))
            .filter(AutomationProfileBuyReservation.trade_date_kst == now_utc.astimezone(KST).date().isoformat())
            .filter(AutomationProfileBuyReservation.scheduler_slot_kst == slot)
            .order_by(AutomationProfileBuyReservation.id.asc())
            .first()
        )
        if existing_slot is not None:
            return self._recovery(db, existing_slot, gate)
        values = _candidate_values(candidates)
        if not values and self.candidate_provider:
            try:
                values = _candidate_values(self.candidate_provider(db=db, profile=profile, now=now_utc))
            except TypeError:
                values = _candidate_values(self.candidate_provider(db, profile))
        min_price_krw, max_price_krw = profile_universe_bounds(profile)
        eligible_values: list[dict[str, Any]] = []
        profile_exclusion_counts: dict[str, int] = {}
        filtered_symbols: set[str] = set()
        for candidate in values:
            reason = profile_price_exclusion_reason(
                candidate_price(candidate),
                min_price_krw=min_price_krw,
                max_price_krw=max_price_krw,
            )
            if reason is None:
                eligible_values.append(candidate)
                continue
            symbol = _symbol(candidate)
            if symbol not in filtered_symbols:
                filtered_symbols.add(symbol)
                profile_exclusion_counts[reason] = (
                    profile_exclusion_counts.get(reason, 0) + 1
                )
        values = eligible_values
        if not values:
            reason = next(iter(profile_exclusion_counts), 'no_buy_candidate')
            return self._blocked(
                reason,
                profile=profile,
                profile_eligible_symbol_count=0,
                profile_price_filtered_count=len(filtered_symbols),
                profile_exclusion_counts=profile_exclusion_counts,
                live_order_gate=gate,
            )
        selected, target, plan, top_score = self._select_candidate(db, profile, values, self._account_snapshot(db))
        if selected is None:
            reason = 'below_profile_buy_threshold' if top_score is not None and top_score < 65 else 'no_executable_candidate'
            return self._blocked(reason, profile=profile, final_buy_score=top_score, live_order_gate=gate)
        symbol = _symbol(selected)
        key = ':'.join([str(profile.get('profile_key')), now_utc.astimezone(KST).date().isoformat(), slot, symbol])
        existing = db.query(AutomationProfileBuyReservation).filter(AutomationProfileBuyReservation.reservation_key == key).first()
        if existing:
            return self._recovery(db, existing, gate)
        if self._position_priority(db):
            return self._blocked('position_management_priority', profile=profile, selected_symbol=symbol)
        reservation = AutomationProfileBuyReservation(
            reservation_key=key,
            provider=PROVIDER,
            market=MARKET,
            profile_key=str(profile.get('profile_key')),
            trade_date_kst=now_utc.astimezone(KST).date().isoformat(),
            scheduler_slot_kst=slot,
            symbol=symbol,
            status='reserved',
        )
        order = self._buy_order(profile, selected, target, plan, slot, key)
        db.add(reservation)
        db.add(order)
        db.flush()
        reservation.order_id = order.id
        db.commit()
        validation = self._validate(db, symbol, int(plan['quantity']), profile, selected, 'buy')
        if validation.get('validated_for_submission') is not True:
            return self._validation_block(db, reservation, order, validation)
        execution = self.execution_core.submit_market_buy(
            db,
            order=order,
            symbol=symbol,
            qty=int(plan['quantity']),
            expected_price=plan['price'],
            max_positions=1,
            max_order_notional_krw=plan['approved_notional_krw'],
            min_price_krw=(settings.get('universe') or {}).get('min_price_krw'),
            max_price_krw=(settings.get('universe') or {}).get('max_price_krw'),
            now=now_utc,
        )
        if execution.get('submitted') is not True:
            reservation.status = 'blocked'
            reservation.block_reason = execution.get('reason') or 'execution_core_gate_blocked'
            db.commit()
            return self._blocked(reservation.block_reason, profile=profile, order_id=order.id, reservation_id=reservation.id, validation_called=True, broker_submit_called=bool(execution.get('broker_submit_called')), live_order_gate=gate)
        reservation.status = 'submitted'
        db.commit()
        if self.execution_core.order_sync_service is not None:
            self.execution_core.sync_order(db, order.id)
        db.refresh(order)
        if str(order.internal_status).upper() == InternalOrderStatus.FILLED.value:
            reservation.status = 'filled'
        db.commit()
        lifecycle = db.query(PositionLifecycle).filter(PositionLifecycle.entry_order_id == order.id).first()
        result = {
            'status': reservation.status,
            'action': 'buy',
            'reason': 'buy_filled' if reservation.status == 'filled' else 'buy_submitted',
            'selected_symbol': symbol,
            'selected_candidate_observability': candidate_gpt_quant_observability(
                selected
            ),
            'final_buy_score': _score(selected, 'final_buy_score', 'final_score', 'buy_score'),
            'required_entry_score': _threshold(profile),
            'quantity': int(plan['quantity']),
            'approved_notional_krw': plan['approved_notional_krw'],
            'order_id': order.id,
            'reservation_id': reservation.id,
            'internal_status': order.internal_status,
            'validation_called': True,
            'validation_call_count': 1,
            'broker_submit_called': bool(execution.get('broker_submit_called')),
            'broker_buy_call_count': 1 if execution.get('broker_submit_called') else 0,
            'real_external_kis_submit_count': 0,
            'lifecycle': _lifecycle(lifecycle),
            'live_order_gate': gate,
            'safety': _safety(read_only=False),
        }
        self._record_run(db, result, slot, now_utc)
        return result

    def _account_snapshot(self, db: Session) -> dict[str, Any]:
        positions = self.positions_loader(db) if self.positions_loader is not None else []
        open_orders = self.open_orders_loader(db) if self.open_orders_loader is not None else []
        balance = {}
        if self.balance_loader is not None:
            balance = self.balance_loader(db) or {}
        elif self.client is not None:
            reader = getattr(self.client, 'get_account_balance', None)
            if callable(reader):
                value = reader()
                balance = value if isinstance(value, dict) else {}
        return {
            'positions': positions if isinstance(positions, list) else [],
            'open_orders': open_orders if isinstance(open_orders, list) else [],
            'balance': balance if isinstance(balance, dict) else {},
            'read_at': datetime.now(UTC).isoformat(),
        }

    def _blocked(self, reason: str, *, profile: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {
            'status': 'blocked',
            'action': 'hold',
            'reason': reason,
            'profile_key': profile.get('profile_key'),
            'required_entry_score': _threshold(profile),
            'validation_called': bool(extra.pop('validation_called', False)),
            'broker_submit_called': bool(extra.pop('broker_submit_called', False)),
            'broker_buy_call_count': 0,
            'real_external_kis_submit_count': 0,
            'safety': _safety(read_only=False),
            **extra,
        }

    def _select_candidate(self, db: Session, profile: dict[str, Any], values: list[dict[str, Any]], account: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any], float | None]:
        values.sort(key=lambda item: -(_score(item, 'final_buy_score', 'final_score', 'buy_score') or -1))
        top_score = _score(values[0], 'final_buy_score', 'final_score', 'buy_score') if values else None
        for candidate in values:
            score = _score(candidate, 'final_buy_score', 'final_score', 'buy_score')
            if score is None or score < _threshold(profile):
                continue
            price = _score(candidate, 'current_price', 'price', 'simulated_price')
            if price is None or price <= 0:
                continue
            target = self.target_risk_service.evaluate_entry(
                db,
                {
                    'provider': PROVIDER,
                    'market': MARKET,
                    'symbol': _symbol(candidate),
                    'side': 'buy',
                    'requested_notional_krw': _score(candidate, 'approved_notional_krw', 'recommended_notional_krw'),
                    'buy_score': score,
                    'trigger_source': TRIGGER_SOURCE,
                    'dry_run': False,
                },
                profile_name=str(profile.get('profile_key') or profile.get('profile_name') or 'safe'),
            )
            target = dict(target or {})
            if target.get('approved') is not True:
                continue
            approved = _score(target, 'approved_notional_krw', 'recommended_notional_krw') or _score(candidate, 'approved_notional_krw', 'recommended_notional_krw')
            if approved is None or approved <= 0:
                continue
            quantity = math.floor(approved / price)
            if quantity < 1:
                continue
            cash = _score(account.get('balance') or {}, 'cash', 'available_cash', 'orderable_cash')
            if cash is not None and cash < quantity * price:
                continue
            return candidate, target, {'quantity': quantity, 'price': price, 'approved_notional_krw': round(approved, 2)}, top_score
        return None, {}, {}, top_score

    def _buy_order(self, profile: dict[str, Any], candidate: dict[str, Any], target: dict[str, Any], plan: dict[str, Any], slot: str, key: str) -> OrderLog:
        exit_settings = _profile_settings(profile).get('exit') or {}
        return OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=_symbol(candidate),
            side='buy',
            order_type='market',
            time_in_force='day',
            qty=float(plan['quantity']),
            requested_qty=float(plan['quantity']),
            remaining_qty=float(plan['quantity']),
            limit_price=float(plan['price']),
            notional=round(float(plan['quantity']) * float(plan['price']), 2),
            internal_status=InternalOrderStatus.REQUESTED.value,
            request_payload=_json({
                'source': 'strategy_live_auto_buy',
                'source_type': 'profile_aware_guarded_live_auto_buy',
                'mode': MODE,
                'trigger_source': TRIGGER_SOURCE,
                'scheduler_slot': slot,
                'reservation_key': key,
                'automation_profile': True,
                'automation_profile_key': profile.get('profile_key'),
                'final_buy_score': _score(candidate, 'final_buy_score', 'final_score', 'buy_score'),
                'target_risk_result': target,
                'estimated_price': plan['price'],
                'stop_loss_pct': exit_settings.get('stop_loss_pct', 2.0),
                'take_profit_pct': exit_settings.get('take_profit_pct', 8.0),
            }),
        )

    def _validate(self, db: Session, symbol: str, qty: int, profile: dict[str, Any], candidate: dict[str, Any], side: str) -> dict[str, Any]:
        if self.validation_service is not None:
            self.execution_core.validation_service = self.validation_service
        return self.execution_core.validate_order(
            db,
            KisOrderValidationRequest(
                market=MARKET,
                symbol=symbol,
                side=side,
                qty=qty,
                order_type='market',
                dry_run=True,
                reason=f'{MODE} {side} validation',
                source_metadata={
                    'source_context': TRIGGER_SOURCE,
                    'mode': MODE,
                    'profile_key': profile.get('profile_key'),
                    'final_buy_score': _score(candidate, 'final_buy_score', 'final_score', 'buy_score'),
                },
            ),
        )

    def _validation_block(self, db: Session, reservation: AutomationProfileBuyReservation, order: OrderLog, validation: dict[str, Any]) -> dict[str, Any]:
        reason = validation.get('primary_block_reason') or (validation.get('block_reasons') or ['validation_failed'])[0]
        reservation.status = 'blocked'
        reservation.block_reason = reason
        order.internal_status = InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
        db.commit()
        return {
            'status': 'blocked',
            'action': 'hold',
            'reason': reason,
            'selected_symbol': order.symbol,
            'order_id': order.id,
            'reservation_id': reservation.id,
            'validation_called': True,
            'broker_submit_called': False,
            'broker_buy_call_count': 0,
            'real_external_kis_submit_count': 0,
            'validation': validation,
            'safety': _safety(read_only=False),
        }

    def _recovery(self, db: Session, reservation: AutomationProfileBuyReservation, gate: dict[str, Any]) -> dict[str, Any]:
        order = db.get(OrderLog, reservation.order_id) if reservation.order_id else None
        lifecycle = db.query(PositionLifecycle).filter(PositionLifecycle.entry_order_id == reservation.order_id).first() if reservation.order_id else None
        return {
            'status': reservation.status,
            'action': 'buy',
            'reason': 'scheduled_slot_already_attempted',
            'selected_symbol': reservation.symbol,
            'order_id': reservation.order_id,
            'reservation_id': reservation.id,
            'internal_status': order.internal_status if order else None,
            'lifecycle': _lifecycle(lifecycle),
            'broker_submit_called': False,
            'broker_buy_call_count': 0,
            'real_external_kis_submit_count': 0,
            'live_order_gate': gate,
            'safety': {**_safety(read_only=False), 'idempotent_replay': True},
        }

    def _record_run(self, db: Session, result: dict[str, Any], slot: str, now: datetime) -> None:
        db.add(TradeRunLog(
            run_key=':'.join([MODE, uuid.uuid4().hex[:12]]),
            trigger_source=TRIGGER_SOURCE,
            symbol=str(result.get('selected_symbol') or 'WATCHLIST'),
            mode=MODE,
            stage='done',
            result=str(result.get('status') or 'filled'),
            reason=str(result.get('reason') or ''),
            order_id=result.get('order_id'),
            request_payload=_json({'scheduler_slot': slot, 'validation_called': True, 'manual_submit_called': False}),
            response_payload=_json(result),
            created_at=now,
        ))
        db.commit()

    def manage_exit_once(self, db: Session, *, current_price: float, now: datetime | None = None) -> dict[str, Any]:
        lifecycle = db.query(PositionLifecycle).filter(PositionLifecycle.status == OPEN).order_by(PositionLifecycle.opened_at.desc(), PositionLifecycle.id.desc()).first()
        if lifecycle is None:
            return {'status': 'hold', 'reason': 'no_open_lifecycle', 'broker_sell_call_count': 0}
        if lifecycle.exit_order_id is not None:
            return {'status': 'hold', 'reason': 'exit_order_already_pending', 'broker_sell_call_count': 0}
        entry = float(lifecycle.entry_price)
        stop = entry * (1 - abs(float(lifecycle.stop_loss_threshold_pct or 2)) / 100)
        take = entry * (1 + abs(float(lifecycle.take_profit_threshold_pct or 8)) / 100)
        if current_price >= take:
            trigger, reason = 'take_profit', 'take_profit_triggered'
        elif current_price <= stop:
            trigger, reason = 'stop_loss', 'stop_loss_triggered'
        else:
            return {'status': 'hold', 'reason': 'no_exit_condition', 'current_price': current_price, 'broker_sell_call_count': 0}
        gate = self.live_order_gate(db)
        if not gate.get('allowed'):
            return {'status': 'blocked', 'reason': (gate.get('blocking_reasons') or ['live_order_not_possible'])[0], 'trigger': trigger, 'broker_sell_call_count': 0}
        qty = max(1, int(float(lifecycle.quantity or 0)))
        order = OrderLog(
            broker=PROVIDER,
            market=MARKET,
            symbol=lifecycle.symbol,
            side='sell',
            order_type='market',
            qty=qty,
            requested_qty=qty,
            remaining_qty=qty,
            limit_price=current_price,
            notional=round(current_price * qty, 2),
            internal_status=InternalOrderStatus.REQUESTED.value,
            request_payload=_json({'source': 'strategy_live_auto_exit', 'source_type': 'guarded_profile_exit', 'mode': MODE, 'automation_profile': True, 'trigger': trigger, 'reason': reason}),
        )
        db.add(order)
        db.commit()
        validation = self._validate(db, lifecycle.symbol, qty, self._active_profile(db), {}, 'sell')
        if validation.get('validated_for_submission') is not True:
            order.internal_status = InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value
            db.commit()
            return {'status': 'blocked', 'reason': 'validation_failed', 'trigger': trigger, 'broker_sell_call_count': 0}
        execution = self.execution_core.submit_market_sell(
            db,
            order=order,
            symbol=lifecycle.symbol,
            qty=qty,
            now=_utc(now),
        )
        if execution.get('submitted') is not True:
            return {'status': 'blocked', 'reason': execution.get('reason'), 'trigger': trigger, 'broker_sell_call_count': 0}
        if self.execution_core.order_sync_service is not None:
            self.execution_core.sync_order(db, order.id)
        db.refresh(lifecycle)
        return {'status': 'closed' if lifecycle.status == CLOSED else 'submitted', 'reason': reason, 'trigger': trigger, 'order_id': order.id, 'broker_sell_call_count': 1, 'lifecycle': _lifecycle(lifecycle)}


def _candidate_values(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        values = value.get('candidates') or value.get('final_ranked_candidates') or []
        if not values and value.get('selected_symbol'):
            values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    return [dict(item) for item in values if isinstance(item, dict) and _symbol(item)]


def _profile_settings(profile: dict[str, Any]) -> dict[str, Any]:
    return profile.get('automation_settings') or profile.get('effective_settings') or {}


def _threshold(profile: dict[str, Any]) -> float:
    settings = _profile_settings(profile)
    return max(65.0, float((settings.get('entry') or {}).get('min_final_score') or profile.get('buy_score_threshold') or 0))


def _score(value: Any, *keys: str) -> float | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        raw = value.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            return float(str(raw).replace(',', '').strip())
        except (TypeError, ValueError):
            continue
    return None


def _symbol(value: dict[str, Any]) -> str:
    text = str(value.get('symbol') or value.get('pdno') or value.get('code') or '').strip().upper()
    return text.zfill(6) if text.isdigit() and len(text) < 6 else text


def _slot(value: Any) -> str | None:
    text = str(value or '').strip().lower().replace('profile:', '')
    if len(text) == 5 and text[2] == ':' and text.replace(':', '').isdigit():
        return text
    return None


def _next_slot(now_utc: datetime, values: Any) -> datetime | None:
    local = now_utc.astimezone(KST)
    slots = sorted({_slot(value) for value in values or [] if _slot(value)})
    for value in slots:
        hour, minute = (int(item) for item in value.split(':'))
        candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > local:
            return candidate
    if not slots:
        return None
    hour, minute = (int(item) for item in slots[0].split(':'))
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _lifecycle(row: PositionLifecycle | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {'id': row.id, 'symbol': row.symbol, 'status': row.status, 'entry_order_id': row.entry_order_id, 'exit_order_id': row.exit_order_id, 'entry_price': row.entry_price, 'quantity': row.quantity}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _safety(*, read_only: bool) -> dict[str, Any]:
    return {'read_only': read_only, 'real_order_submitted': False, 'validation_called': False, 'broker_submit_called': False, 'manual_submit_called': False, 'scheduler_changed': False, 'setting_changed': False, 'dry_run_changed': False, 'kill_switch_changed': False, 'kis_real_order_changed': False}
