from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    SignalLog,
    TradeRunLog,
    User,
    UserAutoTradingSlotClaim,
    UserTradingSettings,
    UserWatchlist,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.services.market_session_service import MarketSessionService
from app.services.kis_dry_run_risk_service import position_exit_threshold_reasons
from app.services.user_trading_execution_service import UserTradingExecutionService


USER_SCHEDULER_TRIGGER_SOURCE = 'user_scheduler'
USER_AUTO_KIS_JOB_ID_PREFIX = 'user_auto_kis'
USER_AUTO_ALPACA_JOB_ID_PREFIX = 'user_auto_alpaca'
USER_AUTO_JOB_ID_PREFIXES = {
    'kis': USER_AUTO_KIS_JOB_ID_PREFIX,
    'alpaca': USER_AUTO_ALPACA_JOB_ID_PREFIX,
}
_SCOPE = {
    'kis': ('KR', ZoneInfo('Asia/Seoul')),
    'alpaca': ('US', ZoneInfo('America/New_York')),
}
_ACTIVE_ORDER_STATUSES = {
    'REQUESTED', 'SUBMITTED', 'ACCEPTED', 'PENDING', 'PARTIALLY_FILLED',
}


class UserAutoTradingCandidateService:
    def select_candidate(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        normalized_provider = str(provider or '').strip().lower()
        market = _SCOPE[normalized_provider][0]
        watchlist = (
            db.query(UserWatchlist)
            .filter(
                UserWatchlist.user_id == int(user.id),
                UserWatchlist.provider == normalized_provider,
            )
            .order_by(UserWatchlist.id.asc())
            .all()
        )
        allowed = {str(row.symbol or '').strip().upper() for row in watchlist}
        rows: list[dict[str, Any]] = []

        if normalized_provider == 'kis':
            snapshot = (
                db.query(WatchlistSnapshotRun)
                .filter(
                    WatchlistSnapshotRun.market == market,
                    WatchlistSnapshotRun.status == 'success',
                )
                .order_by(
                    WatchlistSnapshotRun.completed_at.desc(),
                    WatchlistSnapshotRun.id.desc(),
                )
                .first()
            )
            if snapshot is not None:
                snapshot_rows = (
                    db.query(WatchlistSnapshotItem)
                    .filter(WatchlistSnapshotItem.run_id == int(snapshot.id))
                    .all()
                )
                for row in snapshot_rows:
                    symbol = str(row.symbol or '').strip().upper()
                    if allowed and symbol not in allowed:
                        continue
                    rows.append({
                        'symbol': symbol,
                        'name': row.name,
                        'current_price': row.current_price,
                        'quant_buy_score': row.quant_buy_score,
                        'quant_sell_score': row.quant_sell_score,
                        'indicator_payload': _json_object(row.indicators_json),
                        'candidate_source': 'shared_watchlist_snapshot',
                        'captured_at': row.captured_at.isoformat() if row.captured_at else None,
                    })

        if not rows:
            rows = [
                {
                    'symbol': str(row.symbol or '').strip().upper(),
                    'name': row.symbol,
                    'candidate_source': 'user_watchlist',
                }
                for row in watchlist
                if str(row.market or market).strip().upper() in {market, 'KOSPI', 'KOSDAQ'}
            ]

        rows = [row for row in rows if row.get('symbol')]
        rows.sort(key=lambda row: (
            -_number(row.get('final_buy_score') or row.get('quant_buy_score')),
            _number(row.get('quant_sell_score')),
            str(row.get('symbol') or ''),
        ))
        return rows[0] if rows else None


class UserPositionManagementService:
    def manage(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        snapshot: dict[str, Any],
        now: datetime,
        scheduler_slot: str,
    ) -> dict[str, Any]:
        positions = [
            item for item in (snapshot.get('positions') or [])
            if isinstance(item, dict) and abs(_number(item.get('quantity') or item.get('qty'))) > 0
        ]
        if not positions:
            return {'action': 'entry_scan', 'reason': 'no_open_position', 'positions': []}

        position = positions[0]
        symbol = str(position.get('symbol') or '').strip().upper()
        open_orders = snapshot.get('open_orders') or []
        if any(
            isinstance(item, dict)
            and str(item.get('symbol') or '').strip().upper() == symbol
            and str(item.get('side') or '').strip().lower() == 'sell'
            and str(item.get('status') or '').strip().upper() in _ACTIVE_ORDER_STATUSES
            for item in open_orders
        ):
            return {
                'action': 'hold',
                'reason': 'duplicate_open_sell_order',
                'symbol': symbol,
                'positions': positions,
            }

        normalized_position = {
            **position,
            'qty': position.get('qty') or position.get('quantity') or position.get('hldg_qty'),
            'avg_entry_price': position.get('avg_entry_price')
            or position.get('avg_price')
            or position.get('average_price')
            or position.get('pchs_avg_pric'),
        }
        threshold_reasons, diagnostics = position_exit_threshold_reasons(
            normalized_position,
        )
        if 'stop_loss_triggered' in threshold_reasons:
            return {
                'action': 'sell',
                'reason': 'stop_loss_triggered',
                'symbol': symbol,
                'quantity': _number(position.get('available_quantity') or position.get('quantity') or position.get('qty')),
                'positions': positions,
                'exit_diagnostics': diagnostics,
            }
        if 'take_profit_triggered' in threshold_reasons:
            return {
                'action': 'sell',
                'reason': 'take_profit_triggered',
                'symbol': symbol,
                'quantity': _number(position.get('available_quantity') or position.get('quantity') or position.get('qty')),
                'positions': positions,
                'exit_diagnostics': diagnostics,
            }
        return {
            'action': 'hold',
            'reason': 'no_exit_condition',
            'symbol': symbol,
            'positions': positions,
            'exit_diagnostics': diagnostics,
        }


class UserAutoTradingSchedulerService:
    def __init__(
        self,
        *,
        execution_service: UserTradingExecutionService | None = None,
        candidate_service: UserAutoTradingCandidateService | Callable[..., Any] | None = None,
        position_management_service: UserPositionManagementService | Callable[..., Any] | None = None,
        account_service: Any | None = None,
        session_service: MarketSessionService | None = None,
        automation_profiles: Any | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.execution_service = execution_service or UserTradingExecutionService()
        self.candidate_service = candidate_service or UserAutoTradingCandidateService()
        self.position_management_service = position_management_service or UserPositionManagementService()
        self.account_service = account_service or self.execution_service.account_service
        self.session_service = session_service or self.execution_service.session_service
        self.automation_profiles = automation_profiles
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self._last_status: dict[str, Any] = {}

    @staticmethod
    def job_id(provider: str, slot: str) -> str:
        prefix = USER_AUTO_JOB_ID_PREFIXES[str(provider).strip().lower()]
        return f'{prefix}_{str(slot).replace(":", "")}'

    def dispatcher_jobs(
        self,
        db: Session | None = None,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = _aware_utc(now or self.now_provider())
        result = []
        for provider in ('kis', 'alpaca'):
            market, timezone = _SCOPE[provider]
            for slot, local_time in self._slots(db, provider, current):
                result.append({
                    'job_id': self.job_id(provider, slot),
                    'provider': provider,
                    'market': market,
                    'slot': slot,
                    'timezone': str(timezone),
                    'schedule_at': local_time.isoformat(),
                    'recurring': True,
                    'automatic': True,
                    'user_scoped': True,
                    'admin_scheduler_unchanged': True,
                })
        return result

    def next_slot(
        self,
        db: Session,
        *,
        provider: str,
        now: datetime | None = None,
    ) -> str | None:
        current = _aware_utc(now or self.now_provider())
        due = self._slots(db, provider, current)
        for slot, local_time in due:
            if local_time > current.astimezone(local_time.tzinfo):
                return slot
        return due[0][0] if due else None

    def due_slots(
        self,
        db: Session,
        *,
        provider: str,
        now: datetime | None = None,
    ) -> list[tuple[str, datetime]]:
        current = _aware_utc(now or self.now_provider())
        local_now = current.astimezone(_SCOPE[str(provider).strip().lower()][1])
        due: list[tuple[str, datetime]] = []
        for slot, next_local_time in self._slots(db, provider, current):
            candidate = next_local_time
            if candidate.date() > local_now.date():
                candidate -= timedelta(days=1)
            elapsed = (local_now - candidate).total_seconds()
            if 0 <= elapsed < 60:
                due.append((slot, candidate))
        return due

    def run_provider_once(
        self,
        db: Session,
        *,
        provider: str,
        scheduler_slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_provider = str(provider or '').strip().lower()
        if normalized_provider not in _SCOPE:
            raise ValueError('unsupported_trading_provider')
        current = _aware_utc(now or self.now_provider())
        market, timezone = _SCOPE[normalized_provider]
        trading_date = current.astimezone(timezone).date().isoformat()
        aggregate: dict[str, Any] = {
            'scheduler': self.__class__.__name__,
            'provider': normalized_provider,
            'market': market,
            'scheduler_slot': scheduler_slot,
            'timezone': str(timezone),
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'processed': 0,
            'ignored': 0,
            'completed': 0,
            'failed': 0,
            'items': [],
        }
        users = (
            db.query(User)
            .filter(User.enabled.is_(True))
            .order_by(User.id.asc())
            .all()
        )
        for user in users:
            if str(user.role or '').strip().lower() == 'admin':
                aggregate['ignored'] += 1
                continue
            settings = self._settings(db, user)
            if not bool(settings.auto_trading_enabled):
                aggregate['ignored'] += 1
                continue
            if str(settings.auto_trading_provider or '').strip().lower() != normalized_provider:
                aggregate['ignored'] += 1
                continue
            claim = self._claim(
                db,
                user_id=int(user.id),
                provider=normalized_provider,
                market=market,
                trading_date=trading_date,
                scheduler_slot=scheduler_slot,
            )
            if claim is None:
                aggregate['ignored'] += 1
                aggregate['items'].append({
                    'owner_user_id': int(user.id),
                    'result': 'SKIPPED',
                    'reason': 'duplicate_scheduler_slot',
                    'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
                })
                continue
            aggregate['processed'] += 1
            try:
                item = self._process_user(
                    db,
                    user=user,
                    settings=settings,
                    provider=normalized_provider,
                    market=market,
                    scheduler_slot=scheduler_slot,
                    run_key=claim.run_key,
                    now=current,
                )
                self._finish_claim(db, claim, item)
                aggregate['completed'] += 1
                aggregate['items'].append(item)
            except Exception:
                db.rollback()
                item = self._safe_failure(
                    db,
                    user=user,
                    provider=normalized_provider,
                    market=market,
                    scheduler_slot=scheduler_slot,
                    run_key=claim.run_key,
                )
                self._finish_claim(db, claim, item)
                aggregate['failed'] += 1
                aggregate['items'].append(item)
        aggregate['result'] = 'failed' if aggregate['failed'] and not aggregate['completed'] else 'completed'
        aggregate['last_scheduler_run_at'] = current.isoformat()
        aggregate['last_scheduler_result'] = aggregate['result']
        self._last_status[normalized_provider] = aggregate
        return aggregate

    def _process_user(
        self,
        db: Session,
        *,
        user: User,
        settings: UserTradingSettings,
        provider: str,
        market: str,
        scheduler_slot: str,
        run_key: str,
        now: datetime,
    ) -> dict[str, Any]:
        gate_reason = self._live_gate_reason(settings, provider)
        if gate_reason:
            return self._record_result(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
                result='blocked',
                reason=gate_reason,
                symbol='NONE',
            )
        session = self.session_service.get_session_status(market, now=now)
        if session.get('is_market_open') is not True:
            return self._record_result(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
                result='SKIPPED',
                reason='market_closed',
                symbol='NONE',
            )
        snapshot = self.account_service.get_broker_snapshot(db, user, provider)
        position_result = self._manage_positions(
            db,
            user=user,
            provider=provider,
            snapshot=snapshot,
            scheduler_slot=scheduler_slot,
            now=now,
        )
        action = str(position_result.get('action') or '').strip().lower()
        if action == 'sell':
            exit_method = getattr(self.execution_service, 'run_exit_once', None)
            if callable(exit_method):
                result = exit_method(
                    db,
                    user,
                    provider=provider,
                    symbol=str(position_result.get('symbol') or ''),
                    confirm_live=False,
                    now=now,
                    trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
                    authorization_mode='automatic',
                    scheduler_slot=scheduler_slot,
                    snapshot_override=snapshot,
                    run_key=run_key,
                    exit_reason=str(position_result.get('reason') or 'position_exit'),
                )
                return {**result, 'position_management': position_result}
        if position_result.get('positions'):
            return self._record_result(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
                result='HOLD',
                reason=str(position_result.get('reason') or 'position_management_priority'),
                symbol=str(position_result.get('symbol') or 'NONE'),
                position_management=position_result,
            )
        candidate = self._select_candidate(
            db,
            user=user,
            provider=provider,
            now=now,
        )
        if not candidate or not candidate.get('symbol'):
            return self._record_result(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
                result='HOLD',
                reason='no_qualifying_candidate',
                symbol='NONE',
            )
        result = self.execution_service.run_once(
            db,
            user,
            provider=provider,
            symbol=str(candidate['symbol']),
            confirm_live=False,
            now=now,
            trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
            authorization_mode='automatic',
            scheduler_slot=scheduler_slot,
            snapshot_override=snapshot,
            run_key=run_key,
        )
        return {**result, 'candidate': candidate}

    def _select_candidate(self, db: Session, *, user: User, provider: str, now: datetime):
        selector = self.candidate_service
        if callable(selector):
            return selector(db, user=user, provider=provider, now=now)
        return selector.select_candidate(db, user=user, provider=provider, now=now)

    def _manage_positions(self, db: Session, **kwargs: Any) -> dict[str, Any]:
        manager = self.position_management_service
        if callable(manager):
            return dict(manager(db, **kwargs) or {})
        return dict(manager.manage(db, **kwargs) or {})

    def _slots(
        self,
        db: Session | None,
        provider: str,
        now: datetime,
    ) -> list[tuple[str, datetime]]:
        normalized_provider = str(provider).strip().lower()
        market, timezone = _SCOPE[normalized_provider]
        values: list[str] = []
        if normalized_provider == 'kis' and db is not None and self.automation_profiles is not None:
            try:
                schedule = self.automation_profiles.selected_profile_schedule(
                    db,
                    now=now.astimezone(timezone),
                )
                if schedule and schedule.get('status') == 'active':
                    values = [str(value) for value in schedule.get('analysis_times') or []]
            except Exception:
                values = []
        if not values:
            values = [
                str(item.get('time'))
                for item in self.session_service.get_entry_slots(market)
                if isinstance(item, dict) and item.get('time')
            ]
        local_now = now.astimezone(timezone)
        result = []
        for value in sorted(set(values)):
            try:
                hour, minute = (int(part) for part in value.split(':', 1))
            except (TypeError, ValueError):
                continue
            candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= local_now:
                candidate += timedelta(days=1)
            result.append((value, candidate))
        return result

    @staticmethod
    def _settings(db: Session, user: User) -> UserTradingSettings:
        row = (
            db.query(UserTradingSettings)
            .filter(UserTradingSettings.user_id == int(user.id))
            .first()
        )
        if row is None:
            row = UserTradingSettings(user_id=int(user.id))
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def _claim(db: Session, **values: Any) -> UserAutoTradingSlotClaim | None:
        user_id = int(values['user_id'])
        provider = str(values['provider'])
        market = str(values['market'])
        trading_date = str(values['trading_date'])
        slot = str(values['scheduler_slot'])
        run_key = f'uauto_{user_id}_{provider}_{trading_date}_{slot}'.replace(':', '')
        row = UserAutoTradingSlotClaim(
            user_id=user_id,
            provider=provider,
            market=market,
            trading_date=trading_date,
            scheduler_slot=slot,
            run_key=run_key[:64],
            status='claimed',
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return row
        except IntegrityError:
            db.rollback()
            return None

    @staticmethod
    def _finish_claim(db: Session, claim: UserAutoTradingSlotClaim, result: dict[str, Any]) -> None:
        row = db.get(UserAutoTradingSlotClaim, int(claim.id))
        if row is None:
            return
        row.status = 'failed' if str(result.get('result') or '').lower() == 'failed' else 'completed'
        row.result = str(result.get('result') or '')[:40]
        row.reason = str(result.get('reason') or '')[:160]
        db.commit()

    @staticmethod
    def _live_gate_reason(settings: UserTradingSettings, provider: str) -> str | None:
        if str(settings.trading_mode or 'paper').strip().lower() != 'live':
            return None
        if not bool(settings.live_trading_enabled):
            return 'live_trading_disabled'
        if settings.auto_live_confirmed_at is None:
            return 'auto_live_confirmation_required'
        if bool(settings.kill_switch):
            return 'user_kill_switch_enabled'
        return None

    def _record_result(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        market: str,
        scheduler_slot: str,
        run_key: str,
        result: str,
        reason: str,
        symbol: str,
        position_management: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = db.query(TradeRunLog).filter(
            TradeRunLog.owner_user_id == int(user.id),
            TradeRunLog.run_key == run_key,
        ).first()
        if run is None:
            run = TradeRunLog(
                owner_user_id=int(user.id),
                run_key=run_key,
                trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
                symbol=symbol[:20] or 'NONE',
                mode='user_scheduler',
                stage='done',
                result=result,
                reason=reason,
                request_payload=json.dumps({
                    'provider': provider,
                    'market': market,
                    'scheduler_slot': scheduler_slot,
                    'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
                    'trading_mode': str(self._settings(db, user).trading_mode or 'paper'),
                }, ensure_ascii=False, default=str),
            )
            db.add(run)
        else:
            run.trigger_source = USER_SCHEDULER_TRIGGER_SOURCE
            run.symbol = symbol[:20] or 'NONE'
            run.mode = 'user_scheduler'
            run.stage = 'done'
            run.result = result
            run.reason = reason
        signal = SignalLog(
            owner_user_id=int(user.id),
            symbol=symbol[:20] or 'NONE',
            action='hold' if result.upper() != 'SELL' else 'sell',
            reason=reason,
            signal_status=result,
            trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
            timeframe=scheduler_slot,
            hard_blocked=result.lower() in {'blocked', 'failed'},
        )
        db.add(signal)
        db.flush()
        run.signal_id = signal.id
        run.response_payload = json.dumps({
            'owner_user_id': int(user.id),
            'provider': provider,
            'market': market,
            'scheduler_slot': scheduler_slot,
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'result': result,
            'reason': reason,
            'position_management': position_management,
        }, ensure_ascii=False, default=str)
        db.commit()
        return {
            'owner_user_id': int(user.id),
            'provider': provider,
            'market': market,
            'symbol': symbol,
            'scheduler_slot': scheduler_slot,
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'result': result,
            'reason': reason,
            'run_id': run.id,
            'signal_id': signal.id,
            'order_id': None,
            'position_management': position_management,
            'real_order_submitted': False,
            'broker_submit_called': False,
        }

    def _safe_failure(self, db: Session, **kwargs: Any) -> dict[str, Any]:
        return self._record_result(
            db,
            **kwargs,
            result='failed',
            reason='user_scheduler_processing_failed',
            symbol='NONE',
        )


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
