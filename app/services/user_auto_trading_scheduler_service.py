from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AutomationProfileAiCandidateResult,
    SignalLog,
    TradeRunLog,
    User,
    UserAutoTradingSlotClaim,
    UserTradingSettings,
)
from app.services.market_session_service import MarketSessionService
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService
from app.services.kis_dry_run_risk_service import position_exit_threshold_reasons
from app.services.kis_payload_sanitizer import sanitize_kis_text
from app.services.kis_watchlist_preview_service import normalize_symbol_identity
from app.services.profile_universe_service import profile_universe_bounds
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


class _UserSchedulerProcessingError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        self.failure_stage = str(stage or 'canonical_analysis')
        self.cause = cause
        super().__init__(str(cause))


@contextmanager
def _scheduler_stage(stage: str):
    try:
        yield
    except _UserSchedulerProcessingError:
        raise
    except Exception as exc:
        raise _UserSchedulerProcessingError(stage, exc) from exc


class UserAutoTradingCandidateService:
    """Select only from the active profile's persisted ranked universe."""

    def __init__(
        self,
        *,
        profile_watchlists: AutomationProfileWatchlistService | None = None,
        runtime_preview_service: Any | None = None,
    ) -> None:
        self.profile_watchlists = profile_watchlists or AutomationProfileWatchlistService()
        self.runtime_preview_service = runtime_preview_service
        self.last_pipeline_diagnostics: dict[str, Any] | None = None
        self.last_pipeline_candidate: dict[str, Any] | None = None

    def select_candidates(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        profile: dict[str, Any] | None = None,
        scheduler_slot: str = 'manual',
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self.last_pipeline_diagnostics = None
        self.last_pipeline_candidate = None
        normalized_provider = str(provider or '').strip().lower()
        if normalized_provider != 'kis' or not profile:
            return []
        try:
            snapshot = self.profile_watchlists.build(
                db,
                profile=profile,
                owner_user_id=int(user.id),
                scheduler_slot=scheduler_slot,
                now=now,
            )
        except _UserSchedulerProcessingError:
            raise
        except Exception as exc:
            raise _UserSchedulerProcessingError('profile_watchlist', exc) from exc
        snapshot_data = snapshot.get("snapshot") or {}
        if (
            _int_or_none(snapshot_data.get("profile_id")) != _int_or_none(profile.get("id"))
            or _int_or_none(snapshot_data.get("owner_user_id")) != int(user.id)
        ):
            cause = ValueError('profile_snapshot_scope_mismatch')
            raise _UserSchedulerProcessingError('profile_watchlist', cause) from cause

        min_price_krw, max_price_krw = profile_universe_bounds(profile)
        snapshot_max_price = _number(snapshot_data.get('effective_max_candidate_price'))
        if snapshot_max_price > 0:
            max_price_krw = (
                min(max_price_krw, snapshot_max_price)
                if max_price_krw is not None and max_price_krw > 0
                else snapshot_max_price
            )
        runtime_preview = self.runtime_preview_service
        if runtime_preview is not None:
            try:
                preview = runtime_preview.run_preview(
                    include_gpt=True,
                    db=db,
                    record_run=False,
                    trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
                    min_price_krw=min_price_krw,
                    max_price_krw=max_price_krw,
                    profile_snapshot_items=snapshot.get("items") or [],
                    profile_snapshot_context=snapshot_data,
                    canonical_profile_pipeline=True,
                    decision_timestamp=now,
                )
            except _UserSchedulerProcessingError:
                raise
            except Exception as exc:
                raise _UserSchedulerProcessingError(
                    _infer_canonical_failure_stage(exc),
                    exc,
                ) from exc
            preview = preview if isinstance(preview, dict) else {}
            lineage = _canonical_pipeline_lineage(
                preview,
                snapshot_items=snapshot.get("items") or [],
            )
            try:
                _validate_canonical_pipeline_lineage(lineage)
            except Exception as exc:
                raise _UserSchedulerProcessingError('final_ranking', exc) from exc
            self.last_pipeline_diagnostics = {
                "canonical_profile_pipeline": True,
                "profile_id": profile.get("id"),
                "owner_user_id": int(user.id),
                "snapshot_id": snapshot_data.get("id"),
                "snapshot_date": snapshot_data.get("snapshot_date"),
                "scheduler_slot": scheduler_slot,
                "source_count": snapshot_data.get("source_count"),
                "eligible_count": snapshot_data.get("eligible_count"),
                "selected_count": snapshot_data.get("selected_count"),
                "effective_max_candidate_price": snapshot_data.get(
                    "effective_max_candidate_price"
                ),
                "unaffordable_runtime_candidates": [
                    normalize_symbol_identity(symbol)
                    for symbol in (preview.get("unaffordable_runtime_candidates") or [])
                    if normalize_symbol_identity(symbol)
                ],
                **lineage,
                "selected_final_symbol": lineage.get("selected_symbol"),
                "runtime_quant_candidate_count": preview.get(
                    "runtime_quant_candidate_count", 0
                ),
                "gpt_failed_symbols": preview.get("gpt_failed_symbols", []),
                "gpt_replacement_count": preview.get(
                    "gpt_replacement_count", 0
                ),
                "final_ranked_top5": preview.get(
                    "final_ranked_top5",
                    (preview.get("final_ranked_candidates") or [])[:5],
                ),
            }
            self.last_pipeline_candidate = {
                "_pipeline_preview": preview,
                "_pipeline_snapshot": snapshot,
            }
            final_candidates = preview.get("final_ranked_candidates")
            if not isinstance(final_candidates, list) or not final_candidates:
                return []
            selected_raw = next(
                (
                    item
                    for item in final_candidates
                    if isinstance(item, dict)
                    and (
                        _int_or_none(item.get("final_rank")) == 1
                        or bool(item.get("final_selected"))
                    )
                ),
                final_candidates[0],
            )
            selected = dict(selected_raw)
            selected["_pipeline_preview"] = preview
            selected["_pipeline_snapshot"] = snapshot
            selected["_analysis_override"] = _runtime_analysis_override(selected, profile=profile)
            selected.update({
                "candidate_source": "automation_profile_runtime_quant_gpt",
                "automation_profile_id": int(profile["id"]),
                "automation_profile_key": profile.get("profile_key"),
                "profile_snapshot_id": snapshot_data.get("id"),
                "profile_snapshot_date": snapshot_data.get("snapshot_date"),
                "profile_quant_rank": selected.get("runtime_quant_rank"),
                "profile_ai_rank": selected.get("gpt_target_rank"),
            })
            return [selected]
        self.last_pipeline_diagnostics = None
        self.last_pipeline_candidate = None
        settings = profile.get('effective_settings')
        settings = settings if isinstance(settings, dict) else profile.get('settings')
        universe = settings.get('universe') if isinstance(settings, dict) else {}
        universe = universe if isinstance(universe, dict) else {}
        top_quant = max(0, int(_number(universe.get('top_quant_candidates'))))
        top_ai = max(0, int(_number(universe.get('top_ai_candidates'))))
        limit = min(top_quant, top_ai, len(snapshot.get("items") or []))
        items = list(snapshot.get("items") or [])
        return [
            {
                **item,
                "candidate_source": "automation_profile_watchlist_snapshot",
                "automation_profile_id": int(profile["id"]),
                "automation_profile_key": profile.get("profile_key"),
                "profile_snapshot_id": snapshot_data.get("id"),
                "profile_snapshot_date": snapshot_data.get("snapshot_date"),
                "_pipeline_snapshot": snapshot,
                "profile_quant_rank": item.get("quant_rank"),
                "profile_ai_rank": item.get("ai_rank"),
            }
            for item in items[:limit]
        ]

    def persist_results(
        self,
        db: Session,
        *,
        candidate: dict[str, Any],
        run_id: int | None,
        profile: dict[str, Any],
        user: User,
        scheduler_slot: str,
        now: datetime,
    ) -> None:
        if run_id is None:
            return
        preview = candidate.get("_pipeline_preview")
        snapshot = candidate.get("_pipeline_snapshot")
        if not isinstance(preview, dict) or not isinstance(snapshot, dict):
            return
        snapshot_data = snapshot.get("snapshot") or {}
        snapshot_id = snapshot_data.get("id")
        if snapshot_id is None:
            return
        items = preview.get("items")
        if not isinstance(items, list):
            return
        snapshot_date = str(
            snapshot_data.get("snapshot_date")
            or now.astimezone(_SCOPE["kis"][1]).date().isoformat()
        )
        for item in items:
            if not isinstance(item, dict) or not item.get("symbol"):
                continue
            symbol = str(item.get("symbol")).strip().upper()
            row = (
                db.query(AutomationProfileAiCandidateResult)
                .filter(
                    AutomationProfileAiCandidateResult.profile_id == int(profile["id"]),
                    AutomationProfileAiCandidateResult.owner_user_id == int(user.id),
                    AutomationProfileAiCandidateResult.snapshot_date == snapshot_date,
                    AutomationProfileAiCandidateResult.scheduler_slot == str(scheduler_slot),
                    AutomationProfileAiCandidateResult.symbol == symbol,
                )
                .first()
            )
            values = {
                "owner_user_id": int(user.id),
                "profile_id": int(profile["id"]),
                "snapshot_id": int(snapshot_id),
                "run_id": int(run_id),
                "snapshot_date": snapshot_date,
                "scheduler_slot": str(scheduler_slot),
                "symbol": symbol,
                "symbol_name": item.get("name"),
                "snapshot_rank": _int_or_none(
                    item.get("snapshot_rank") or item.get("rank")
                ),
                "runtime_quant_rank": _int_or_none(item.get("runtime_quant_rank")),
                "runtime_quant_buy_score": _optional_number(
                    item.get("runtime_quant_buy_score")
                    if item.get("runtime_quant_buy_score") is not None
                    else item.get("quant_buy_score")
                ),
                "runtime_quant_sell_score": _optional_number(
                    item.get("runtime_quant_sell_score")
                    if item.get("runtime_quant_sell_score") is not None
                    else item.get("quant_sell_score")
                ),
                "gpt_target_rank": _int_or_none(item.get("gpt_target_rank")),
                "gpt_used": bool(item.get("gpt_used")),
                "gpt_analysis_status": str(
                    item.get("gpt_analysis_status") or "not_run"
                ).strip().lower(),
                "ai_buy_score": _optional_number(item.get("ai_buy_score")),
                "ai_sell_score": _optional_number(item.get("ai_sell_score")),
                "confidence": _optional_number(item.get("confidence")),
                "ai_reason": item.get("ai_reason") or item.get("gpt_reason"),
                "final_buy_score": _optional_number(item.get("final_buy_score")),
                "final_sell_score": _optional_number(item.get("final_sell_score")),
                "final_rank": _int_or_none(item.get("final_rank")),
                "final_selected": bool(item.get("final_selected")),
                "diagnostics_json": json.dumps(
                    self.last_pipeline_diagnostics or {},
                    ensure_ascii=False,
                    default=str,
                ),
            }
            if row is None:
                db.add(AutomationProfileAiCandidateResult(**values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        db.flush()
    def select_candidate(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        profile: dict[str, Any] | None = None,
        scheduler_slot: str = 'manual',
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        return next(iter(self.select_candidates(
            db,
            user=user,
            provider=provider,
            profile=profile,
            scheduler_slot=scheduler_slot,
            now=now,
        )), None)


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
        profile: dict[str, Any] | None = None,
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
        exit_settings = _profile_exit_settings(profile)
        threshold_reasons, diagnostics = position_exit_threshold_reasons(
            normalized_position,
            stop_loss_threshold=exit_settings.get('stop_loss_pct'),
            take_profit_threshold=exit_settings.get('take_profit_pct'),
        )
        diagnostics['profile_stop_loss_pct'] = exit_settings.get('stop_loss_pct')
        diagnostics['profile_take_profit_pct'] = exit_settings.get('take_profit_pct')
        diagnostics['threshold_source'] = 'active_automation_profile' if profile else 'legacy_defaults'
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
        self.candidate_service = (
            candidate_service
            if candidate_service is not None
            else UserAutoTradingCandidateService(
                runtime_preview_service=getattr(
                    getattr(self.execution_service, "analysis_service", None),
                    "kis_preview_service",
                    None,
                )
            )
        )
        self.position_management_service = position_management_service or UserPositionManagementService()
        self.account_service = account_service or self.execution_service.account_service
        self.session_service = session_service or self.execution_service.session_service
        self.automation_profiles = automation_profiles or AutomationProfileService()
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
        if db is None:
            from app.db.database import SessionLocal

            owned_db = SessionLocal()
            try:
                return self.dispatcher_jobs(owned_db, now=now)
            finally:
                owned_db.close()
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
            settings = self._existing_settings(db, user)
            if settings is None or not bool(settings.auto_trading_enabled):
                aggregate['ignored'] += 1
                continue
            if str(settings.auto_trading_provider or '').strip().lower() != normalized_provider:
                aggregate['ignored'] += 1
                continue
            profile_schedule = self._owned_profile_schedule(
                db,
                user=user,
                provider=normalized_provider,
                market=market,
                now=current,
            )
            profile_slots = self._profile_analysis_times(profile_schedule)
            if profile_schedule is None or str(scheduler_slot) not in profile_slots:
                aggregate['ignored'] += 1
                aggregate['items'].append({
                    'owner_user_id': int(user.id),
                    'provider': normalized_provider,
                    'market': market,
                    'scheduler_slot': scheduler_slot,
                    'result': 'SKIPPED',
                    'reason': (
                        'profile_slot_not_due'
                        if profile_schedule is not None
                        else 'automation_profile_missing'
                    ),
                    'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
                })
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
                    profile_schedule=profile_schedule,
                )
                self._finish_claim(db, claim, item)
                aggregate['completed'] += 1
                aggregate['items'].append(item)
            except Exception as exc:
                db.rollback()
                failure_profile = (
                    (profile_schedule or {}).get('profile')
                    if isinstance(profile_schedule, dict)
                    else None
                )
                item = self._safe_failure(
                    db,
                    user=user,
                    provider=normalized_provider,
                    market=market,
                    scheduler_slot=scheduler_slot,
                    run_key=claim.run_key,
                    exception=exc,
                    profile_context=(
                        self._profile_context(
                            profile=failure_profile,
                            scheduler_slot=scheduler_slot,
                            user=user,
                        )
                        if isinstance(failure_profile, dict)
                        else None
                    ),
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
        profile_schedule: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if profile_schedule is None:
            with _scheduler_stage('profile_resolution'):
                profile_schedule = self._owned_profile_schedule(
                    db,
                    user=user,
                    provider=provider,
                    market=market,
                    now=now,
                )
        profile = (profile_schedule or {}).get('profile') or {}
        if (
            not profile_schedule
            or profile_schedule.get('status') != 'active'
            or str(profile.get('provider') or '').strip().lower() != provider
            or str(profile.get('market') or '').strip().upper() != market
        ):
            return self._record_profile_missing_skip(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
            )

        with _scheduler_stage('live_gate'):
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
        with _scheduler_stage('market_session'):
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
        with _scheduler_stage('account_snapshot'):
            snapshot = self.account_service.get_broker_snapshot(db, user, provider)
        with _scheduler_stage('position_management'):
            position_result = self._manage_positions(
                db,
                user=user,
                provider=provider,
                snapshot=snapshot,
                scheduler_slot=scheduler_slot,
                now=now,
                profile=profile,
            )
        action = str(position_result.get('action') or '').strip().lower()
        if action == 'sell':
            exit_method = getattr(self.execution_service, 'run_exit_once', None)
            if callable(exit_method):
                with _scheduler_stage('execution'):
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
        with _scheduler_stage('canonical_analysis'):
            candidates = self._select_candidates(
                db,
                user=user,
                provider=provider,
                profile=profile,
                scheduler_slot=scheduler_slot,
                now=now,
            )
        pipeline_diagnostics = getattr(
            self.candidate_service,
            "last_pipeline_diagnostics",
            None,
        )
        if not candidates:
            profile_context = self._profile_context(
                profile=profile,
                scheduler_slot=scheduler_slot,
                user=user,
                pipeline_diagnostics=pipeline_diagnostics,
            )
            no_candidate_result = self._record_result(
                db,
                user=user,
                provider=provider,
                market=market,
                scheduler_slot=scheduler_slot,
                run_key=run_key,
                result='HOLD',
                reason=(
                    'no_completed_gpt_final_candidate'
                    if pipeline_diagnostics
                    else 'no_qualifying_candidate'
                ),
                symbol='NONE',
                create_signal=not bool(pipeline_diagnostics),
                profile_context=profile_context,
            )
            persist = getattr(self.candidate_service, "persist_results", None)
            pipeline_candidate = getattr(
                self.candidate_service,
                "last_pipeline_candidate",
                None,
            )
            if (
                pipeline_diagnostics
                and callable(persist)
                and isinstance(pipeline_candidate, dict)
            ):
                persist(
                    db,
                    candidate=pipeline_candidate,
                    run_id=no_candidate_result.get("run_id"),
                    profile=profile,
                    user=user,
                    scheduler_slot=scheduler_slot,
                    now=now,
                )
                db.commit()
            pipeline_snapshot = (
                pipeline_candidate.get('_pipeline_snapshot')
                if isinstance(pipeline_candidate, dict)
                else None
            )
            no_candidate_result.update({
                'profile_id': profile.get('id'),
                'profile_snapshot': (
                    pipeline_snapshot.get('snapshot')
                    if isinstance(pipeline_snapshot, dict)
                    else None
                ),
                'pipeline_diagnostics': pipeline_diagnostics,
            })
            return no_candidate_result

        candidate = next(
            (
                item
                for item in candidates
                if _int_or_none(item.get('final_rank')) == 1
                or bool(item.get('final_selected'))
            ),
            candidates[0],
        )
        analysis_override = candidate.get("_analysis_override")
        if analysis_override is None:
            candidate, analysis_override = self._choose_profile_candidate(
                db,
                provider=provider,
                candidates=candidates,
                now=now,
            )
        profile_context = self._profile_context(
            profile=profile,
            candidate=candidate,
            scheduler_slot=scheduler_slot,
            user=user,
            pipeline_diagnostics=pipeline_diagnostics,
        )
        with _scheduler_stage('execution'):
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
                analysis_override=analysis_override,
                profile_context=profile_context,
            )
        persist = getattr(self.candidate_service, "persist_results", None)
        if callable(persist):
            with _scheduler_stage('result_persistence'):
                persist(
                    db,
                    candidate=candidate,
                    run_id=result.get("run_id"),
                    profile=profile,
                    user=user,
                    scheduler_slot=scheduler_slot,
                    now=now,
                )
                db.commit()
        public_candidate = {
            key: value
            for key, value in candidate.items()
            if not str(key).startswith("_")
        }
        return {
            **result,
            'action': (
                analysis_override.get('action')
                if isinstance(analysis_override, dict)
                else (result.get('analysis') or {}).get('action')
            ),
            'candidate': public_candidate,
            'profile_context': profile_context,
            'profile_id': profile.get('id'),
            'profile_snapshot': (
                candidate.get('_pipeline_snapshot', {}).get('snapshot')
                if isinstance(candidate.get('_pipeline_snapshot'), dict)
                else None
            ),
            'pipeline_diagnostics': pipeline_diagnostics,
            'candidate_count': len(candidates),
        }

    def _select_candidates(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        profile: dict[str, Any],
        scheduler_slot: str,
        now: datetime,
    ) -> list[dict[str, Any]]:
        selector = self.candidate_service
        if callable(selector):
            value = selector(
                db, user=user, provider=provider, profile=profile,
                scheduler_slot=scheduler_slot, now=now,
            )
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            return [value] if isinstance(value, dict) else []
        method = getattr(selector, 'select_candidates', None)
        if callable(method):
            value = method(
                db, user=user, provider=provider, profile=profile,
                scheduler_slot=scheduler_slot, now=now,
            )
            return [item for item in (value or []) if isinstance(item, dict)]
        candidate = selector.select_candidate(
            db, user=user, provider=provider, profile=profile,
            scheduler_slot=scheduler_slot, now=now,
        )
        return [candidate] if isinstance(candidate, dict) else []

    def _choose_profile_candidate(
        self,
        db: Session,
        *,
        provider: str,
        candidates: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if len(candidates) <= 1:
            return candidates[0], None
        analyzer = getattr(self.execution_service, 'analysis_service', None)
        analyze = getattr(analyzer, 'analyze', None)
        if not callable(analyze):
            return candidates[0], None
        evaluated: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for index, candidate in enumerate(candidates):
            try:
                result = dict(analyze(
                    db,
                    provider=provider,
                    symbol=str(candidate['symbol']),
                    gate_level=2,
                    now=now,
                ) or {})
            except Exception as exc:
                result = {
                    'action': 'hold',
                    'reason': 'analysis_unavailable',
                    'hard_blocked': True,
                    'gating_notes': [f'{exc.__class__.__name__}: {str(exc)[:160]}'],
                }
            evaluated.append((index, candidate, result))
        selected_index, selected_candidate, selected_analysis = max(
            evaluated,
            key=lambda item: (
                _number(
                    item[2].get('final_buy_score')
                    or item[2].get('score')
                    or item[1].get('quant_buy_score')
                ),
                -item[0],
            ),
        )
        del selected_index
        return selected_candidate, selected_analysis

    @staticmethod
    def _profile_context(
        *,
        profile: dict[str, Any],
        candidate: dict[str, Any] | None = None,
        scheduler_slot: str,
        user: User,
        pipeline_diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings = profile.get('effective_settings')
        settings = settings if isinstance(settings, dict) else profile.get('settings')
        settings = settings if isinstance(settings, dict) else {}
        capital = settings.get('capital')
        capital = capital if isinstance(capital, dict) else profile.get('capital')
        capital = capital if isinstance(capital, dict) else {}
        pipeline_snapshot = (candidate or {}).get('_pipeline_snapshot')
        snapshot_data = (
            pipeline_snapshot.get('snapshot')
            if isinstance(pipeline_snapshot, dict)
            else {}
        )
        snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
        snapshot_diagnostics = snapshot_data.get('diagnostics')
        snapshot_diagnostics = snapshot_diagnostics if isinstance(snapshot_diagnostics, dict) else {}
        capital_state = snapshot_diagnostics.get('capital_state')
        capital_state = capital_state if isinstance(capital_state, dict) else {}
        effective_entry_budget = (
            snapshot_data.get('effective_entry_budget_krw')
            if snapshot_data.get('effective_entry_budget_krw') is not None
            else capital_state.get('effective_next_entry_budget_krw')
        )
        return {
            'profile_id': profile.get('id'),
            'profile_key': profile.get('profile_key'),
            'profile_name': profile.get('custom_name') or profile.get('display_name'),
            'owner_user_id': int(user.id),
            'scheduler_slot': scheduler_slot,
            'profile_snapshot_id': (candidate or {}).get('profile_snapshot_id'),
            'symbol': (candidate or {}).get('symbol'),
            'symbol_name': (candidate or {}).get('name'),
            'quant_rank': (candidate or {}).get('quant_rank'),
            'ai_rank': (candidate or {}).get('ai_rank'),
            'sizing_source': 'automation_profile',
            'sizing_mode': str(capital.get('sizing_mode') or 'equity_pct').strip().lower(),
            'effective_entry_budget_krw': effective_entry_budget,
            'profile_budget_krw': effective_entry_budget,
            'fixed_budget_krw': capital.get('fixed_budget'),
            'target_position_pct': capital.get('target_position_pct'),
            'max_position_pct': capital.get('max_position_pct'),
            'max_total_exposure_pct': capital.get('max_total_exposure_pct'),
            'max_order_notional_krw': capital.get('max_order_notional_krw'),
            'max_open_positions': int(settings.get('max_open_positions') or 1),
            'pipeline': 'raw_universe->profile_eligibility->canonical_quant_top50->quant_top10->ai_top5->final_candidate',
            'pipeline_diagnostics': pipeline_diagnostics or {},
        }
    def _select_candidate(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        profile: dict[str, Any],
        scheduler_slot: str,
        now: datetime,
    ):
        selector = self.candidate_service
        if callable(selector):
            return selector(
                db, user=user, provider=provider, profile=profile,
                scheduler_slot=scheduler_slot, now=now,
            )
        return selector.select_candidate(
            db, user=user, provider=provider, profile=profile,
            scheduler_slot=scheduler_slot, now=now,
        )

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
        values: set[str] = set()
        if db is not None and self.automation_profiles is not None:
            for _user, _settings, profile_schedule in self._eligible_user_profiles(
                db,
                provider=normalized_provider,
                market=market,
                now=now,
            ):
                values.update(self._profile_analysis_times(profile_schedule))
        if not values:
            values.update(
                str(item.get('time'))
                for item in self.session_service.get_entry_slots(market)
                if isinstance(item, dict) and item.get('time')
            )
        local_now = now.astimezone(timezone)
        result = []
        for value in sorted(values):
            try:
                hour, minute = (int(part) for part in value.split(':', 1))
            except (TypeError, ValueError):
                continue
            candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= local_now:
                candidate += timedelta(days=1)
            result.append((value, candidate))
        return result

    def _eligible_user_profiles(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
        now: datetime,
    ) -> list[tuple[User, UserTradingSettings, dict[str, Any]]]:
        """Return active owner profiles that are allowed to drive dispatch slots."""
        rows: list[tuple[User, UserTradingSettings, dict[str, Any]]] = []
        users = (
            db.query(User)
            .filter(User.enabled.is_(True))
            .order_by(User.id.asc())
            .all()
        )
        for user in users:
            if str(user.role or '').strip().lower() == 'admin':
                continue
            settings = self._existing_settings(db, user)
            if settings is None or not bool(settings.auto_trading_enabled):
                continue
            if str(settings.auto_trading_provider or '').strip().lower() != provider:
                continue
            profile_schedule = self._owned_profile_schedule(
                db,
                user=user,
                provider=provider,
                market=market,
                now=now,
            )
            if profile_schedule is None:
                continue
            if not self._profile_analysis_times(profile_schedule):
                continue
            rows.append((user, settings, profile_schedule))
        return rows

    def _owned_profile_schedule(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        market: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        """Resolve only the active profile owned by this exact regular user."""
        try:
            schedule = self.automation_profiles.selected_owned_profile_schedule(
                db,
                owner_user_id=int(user.id),
                now=now,
            )
        except Exception:
            return None
        if not isinstance(schedule, dict) or schedule.get('status') != 'active':
            return None
        profile = schedule.get('profile')
        if not isinstance(profile, dict):
            return None
        try:
            owner_user_id = int(profile.get('owner_user_id'))
        except (TypeError, ValueError):
            return None
        if owner_user_id != int(user.id):
            return None
        if profile.get('enabled') is not True:
            return None
        if str(profile.get('custom_status') or '').strip().lower() != 'active':
            return None
        if str(profile.get('provider') or '').strip().lower() != provider:
            return None
        if str(profile.get('market') or '').strip().upper() != market:
            return None
        return schedule

    @staticmethod
    def _profile_analysis_times(
        profile_schedule: dict[str, Any] | None,
    ) -> set[str]:
        if not isinstance(profile_schedule, dict):
            return set()
        profile = profile_schedule.get('profile')
        if not isinstance(profile, dict):
            return set()
        effective = profile.get('effective_settings')
        effective = effective if isinstance(effective, dict) else profile.get('settings')
        entry = effective.get('entry') if isinstance(effective, dict) else None
        if not isinstance(entry, dict):
            return set()
        values: set[str] = set()
        for raw in entry.get('analysis_times') or []:
            try:
                hour, minute = (int(part) for part in str(raw).split(':', 1))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    values.add(f'{hour:02d}:{minute:02d}')
            except (TypeError, ValueError):
                continue
        if 'analysis_times' in profile_schedule:
            canonical: set[str] = set()
            for raw in profile_schedule.get('analysis_times') or []:
                try:
                    hour, minute = (int(part) for part in str(raw).split(':', 1))
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        canonical.add(f'{hour:02d}:{minute:02d}')
                except (TypeError, ValueError):
                    continue
            return values.intersection(canonical)
        return values

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
    def _existing_settings(
        db: Session,
        user: User,
    ) -> UserTradingSettings | None:
        return (
            db.query(UserTradingSettings)
            .filter(UserTradingSettings.user_id == int(user.id))
            .first()
        )

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
        if (
            str(provider or '').strip().lower() != 'kis'
            or str(settings.auto_trading_provider or '').strip().lower() != 'kis'
        ):
            return 'auto_live_kis_provider_required'
        if settings.auto_live_confirmed_at is None:
            return 'auto_live_confirmation_required'
        if bool(settings.kill_switch):
            return 'user_kill_switch_enabled'
        return None

    def _record_profile_missing_skip(
        self,
        db: Session,
        *,
        user: User,
        provider: str,
        market: str,
        scheduler_slot: str,
        run_key: str,
    ) -> dict[str, Any]:
        """Record a scheduler outcome without creating a trading SignalLog."""
        run = db.query(TradeRunLog).filter(
            TradeRunLog.owner_user_id == int(user.id),
            TradeRunLog.run_key == run_key,
        ).first()
        if run is None:
            run = TradeRunLog(
                owner_user_id=int(user.id),
                run_key=run_key,
                trigger_source=USER_SCHEDULER_TRIGGER_SOURCE,
                symbol='NONE',
                mode='user_scheduler',
                stage='done',
                result='skipped',
                reason='automation_profile_missing',
            )
            db.add(run)
        else:
            run.trigger_source = USER_SCHEDULER_TRIGGER_SOURCE
            run.symbol = 'NONE'
            run.mode = 'user_scheduler'
            run.stage = 'done'
            run.result = 'skipped'
            run.reason = 'automation_profile_missing'
            run.signal_id = None
            run.order_id = None
        run.request_payload = json.dumps({
            'provider': provider,
            'market': market,
            'scheduler_slot': scheduler_slot,
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'precondition': 'owner_automation_profile',
        }, ensure_ascii=False, default=str)
        run.response_payload = json.dumps({
            'owner_user_id': int(user.id),
            'result': 'skipped',
            'reason': 'automation_profile_missing',
            'trading_signal_created': False,
            'execution_service_called': False,
        }, ensure_ascii=False, default=str)
        db.commit()
        return {
            'owner_user_id': int(user.id),
            'provider': provider,
            'market': market,
            'symbol': 'NONE',
            'scheduler_slot': scheduler_slot,
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'result': 'skipped',
            'reason': 'automation_profile_missing',
            'run_id': run.id,
            'signal_id': None,
            'order_id': None,
            'real_order_submitted': False,
            'broker_submit_called': False,
        }

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
        profile_context: dict[str, Any] | None = None,
        create_signal: bool = True,
        failure_stage: str | None = None,
        failure_diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        failure_payload = dict(failure_diagnostics or {})
        if failure_stage:
            failure_payload['failure_stage'] = str(failure_stage)
        result_stage = (
            str(failure_payload.get('failure_stage') or 'done')[:20]
            if result.lower() == 'failed'
            else 'done'
        )
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
                stage=result_stage,
                result=result,
                reason=reason,
                request_payload=json.dumps({
                    'provider': provider,
                    'market': market,
                    'scheduler_slot': scheduler_slot,
                    'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
                    'trading_mode': str(self._settings(db, user).trading_mode or 'paper'),
                    'profile_context': profile_context,
                }, ensure_ascii=False, default=str),
            )
            db.add(run)
        else:
            run.trigger_source = USER_SCHEDULER_TRIGGER_SOURCE
            run.symbol = symbol[:20] or 'NONE'
            run.mode = 'user_scheduler'
            run.stage = result_stage
            run.result = result
            run.reason = reason
        signal = None
        if create_signal:
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
        run.signal_id = signal.id if signal is not None else None
        response_payload = {
            'owner_user_id': int(user.id),
            'provider': provider,
            'market': market,
            'scheduler_slot': scheduler_slot,
            'trigger_source': USER_SCHEDULER_TRIGGER_SOURCE,
            'result': result,
            'reason': reason,
            'position_management': position_management,
            'trading_signal_created': signal is not None,
            'profile_context': profile_context,
            **failure_payload,
        }
        run.response_payload = json.dumps(
            response_payload,
            ensure_ascii=False,
            default=str,
        )
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
            'signal_id': signal.id if signal is not None else None,
            'order_id': None,
            'position_management': position_management,
            'trading_signal_created': signal is not None,
            'real_order_submitted': False,
            'broker_submit_called': False,
            'profile_context': profile_context,
            **failure_payload,
        }

    def _safe_failure(
        self,
        db: Session,
        *,
        exception: Exception | None = None,
        profile_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        details = _failure_details(exception)
        return self._record_result(
            db,
            **kwargs,
            profile_context=profile_context,
            result='failed',
            reason='user_scheduler_processing_failed',
            symbol='NONE',
            failure_stage=details['failure_stage'],
            failure_diagnostics=details,
        )


def _profile_exit_settings(profile: dict[str, Any] | None) -> dict[str, float | None]:
    source = profile if isinstance(profile, dict) else {}
    settings = source.get('effective_settings')
    settings = settings if isinstance(settings, dict) else source.get('settings')
    settings = settings if isinstance(settings, dict) else {}
    exit_settings = settings.get('exit') if isinstance(settings.get('exit'), dict) else {}
    return {
        'stop_loss_pct': _number(exit_settings.get('stop_loss_pct')) or None,
        'take_profit_pct': _number(exit_settings.get('take_profit_pct')) or None,
    }


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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _symbol_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        raw = item.get('symbol') if isinstance(item, dict) else item
        symbol = normalize_symbol_identity(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _canonical_pipeline_lineage(
    preview: dict[str, Any],
    *,
    snapshot_items: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot_symbols = _symbol_list(snapshot_items)

    def values_or(name: str, fallback: list[str]) -> list[str]:
        values = preview.get(name)
        return _symbol_list(values) if isinstance(values, list) else list(fallback)

    runtime_input = values_or('runtime_input_symbols', snapshot_symbols)
    runtime_quant = values_or(
        'runtime_quant_candidate_symbols',
        _symbol_list(
            preview.get('quant_ranked_candidates')
            or preview.get('top_quant_candidates')
            or preview.get('items')
        ),
    )
    runtime_top5 = values_or('runtime_quant_top5_symbols', runtime_quant[:5])
    gpt_targets = values_or('gpt_target_symbols', runtime_top5)
    gpt_completed = values_or('gpt_completed_symbols', [])

    final_values = preview.get('final_ranked_candidates')
    final_candidates = final_values if isinstance(final_values, list) else []
    final_symbols = _symbol_list(
        final_candidates
        if final_candidates
        else preview.get('final_candidate_symbols')
    )
    final_rank_1 = next(
        (
            normalize_symbol_identity(item.get('symbol'))
            for item in final_candidates
            if isinstance(item, dict)
            and (
                _int_or_none(item.get('final_rank')) == 1
                or bool(item.get('final_selected'))
            )
        ),
        final_symbols[0] if final_symbols else None,
    )
    selected_symbol = normalize_symbol_identity(preview.get('selected_final_symbol'))
    if not selected_symbol:
        selected_symbol = final_rank_1

    return {
        'profile_snapshot_selected_symbols': snapshot_symbols,
        'runtime_input_symbols': runtime_input,
        'runtime_quant_candidate_symbols': runtime_quant,
        'runtime_quant_top5_symbols': runtime_top5,
        'gpt_target_symbols': gpt_targets,
        'gpt_completed_symbols': gpt_completed,
        'final_candidate_symbols': final_symbols,
        'selected_symbol': selected_symbol,
        'final_rank_1_symbol': final_rank_1,
        'final_selected_count': sum(
            1
            for item in final_candidates
            if isinstance(item, dict) and bool(item.get('final_selected'))
        ),
    }


def _validate_canonical_pipeline_lineage(lineage: dict[str, Any]) -> None:
    snapshot = set(lineage.get('profile_snapshot_selected_symbols') or [])
    runtime_input = set(lineage.get('runtime_input_symbols') or [])
    runtime_quant = set(lineage.get('runtime_quant_candidate_symbols') or [])
    runtime_top5 = set(lineage.get('runtime_quant_top5_symbols') or [])
    gpt_targets = set(lineage.get('gpt_target_symbols') or [])
    gpt_completed = set(lineage.get('gpt_completed_symbols') or [])
    final_candidates = set(lineage.get('final_candidate_symbols') or [])

    if runtime_input != snapshot:
        raise ValueError('runtime_input_outside_profile_snapshot')
    if not runtime_quant <= runtime_input:
        raise ValueError('runtime_quant_outside_runtime_input')
    if not runtime_top5 <= runtime_quant:
        raise ValueError('runtime_top5_outside_runtime_quant')
    if not gpt_targets <= runtime_top5:
        raise ValueError('gpt_target_outside_runtime_top5')
    if not gpt_completed <= gpt_targets:
        raise ValueError('gpt_completed_outside_gpt_target')
    if not final_candidates <= gpt_completed:
        raise ValueError('final_candidate_outside_gpt_completed')
    final_rank_1 = lineage.get('final_rank_1_symbol')
    selected = lineage.get('selected_symbol')
    if final_rank_1 is not None and selected != final_rank_1:
        raise ValueError('selected_symbol_is_not_final_rank_one')


def _infer_canonical_failure_stage(exc: Exception) -> str:
    explicit = getattr(exc, 'failure_stage', None) or getattr(exc, 'stage', None)
    if explicit:
        return str(explicit)
    text = f'{exc.__class__.__name__} {exc}'.lower()
    for marker, stage in (
        ('quant', 'runtime_quant'),
        ('gpt', 'gpt_analysis'),
        ('ai_', 'gpt_analysis'),
        ('final', 'final_ranking'),
    ):
        if marker in text:
            return stage
    return 'canonical_analysis'


def _failure_details(exception: Exception | None) -> dict[str, str]:
    current = exception or RuntimeError('unknown_scheduler_failure')
    stage = getattr(current, 'failure_stage', None)
    cause = getattr(current, 'cause', None)
    if isinstance(cause, Exception):
        stage = stage or getattr(cause, 'failure_stage', None)
        current = cause
    failure_stage = str(stage or _infer_canonical_failure_stage(current))[:40]
    raw = str(current).strip() or current.__class__.__name__
    lowered = raw.lower()
    sensitive_markers = (
        'appkey',
        'appsecret',
        'access_token',
        'approval_key',
        'authorization header',
        'broker credential',
        'account number',
    )
    sanitized = (
        'sensitive broker error details redacted'
        if any(marker in lowered for marker in sensitive_markers)
        else sanitize_kis_text(raw)
    )
    return {
        'failure_stage': failure_stage,
        'exception_type': current.__class__.__name__[:80],
        'sanitized_error': sanitized[:240],
    }


def _runtime_analysis_override(
    candidate: dict[str, Any],
    *,
    profile: dict[str, Any],
) -> dict[str, Any]:
    settings = profile.get("effective_settings")
    settings = settings if isinstance(settings, dict) else profile.get("settings")
    settings = settings if isinstance(settings, dict) else {}
    entry = settings.get("entry")
    entry = entry if isinstance(entry, dict) else {}
    threshold = max(65.0, _number(entry.get("min_final_score")))
    score = _optional_number(candidate.get("final_buy_score"))
    price = _optional_number(candidate.get("current_price"))
    gpt_completed = (
        bool(candidate.get("gpt_used"))
        and str(candidate.get("gpt_analysis_status") or "").strip().lower()
        == "completed"
        and _optional_number(candidate.get("ai_buy_score")) is not None
        and _optional_number(candidate.get("ai_sell_score")) is not None
    )
    data_sufficient = (
        price is not None
        and price > 0
        and str(candidate.get("indicator_status") or "").strip().lower()
        in {"ok", "partial"}
    )
    action = "buy" if gpt_completed and data_sufficient and score is not None and score >= threshold else "hold"
    reason = (
        "profile_final_candidate"
        if action == "buy"
        else (
            "below_profile_buy_threshold"
            if score is not None and score < threshold
            else "profile_final_candidate_below_entry_gate"
        )
    )
    return {
        "provider": "kis",
        "market": "KR",
        "symbol": candidate.get("symbol"),
        "analyzed_symbol": candidate.get("symbol"),
        "returned_symbol": candidate.get("symbol"),
        "action": action,
        "reason": reason,
        "block_reason": reason if action == "hold" else None,
        "current_price": candidate.get("current_price"),
        "final_buy_score": candidate.get("final_buy_score"),
        "final_sell_score": candidate.get("final_sell_score"),
        "quant_buy_score": candidate.get("quant_buy_score"),
        "quant_sell_score": candidate.get("quant_sell_score"),
        "ai_buy_score": candidate.get("ai_buy_score"),
        "ai_sell_score": candidate.get("ai_sell_score"),
        "confidence": candidate.get("confidence"),
        "ai_reason": candidate.get("ai_reason") or candidate.get("gpt_reason"),
        "quant_reason": candidate.get("quant_reason"),
        "indicator_payload": candidate.get("indicator_payload") or {},
        "indicator_status": candidate.get("indicator_status"),
        "data_sufficient": data_sufficient,
        "gpt_used": bool(candidate.get("gpt_used")),
        "gpt_analysis_status": candidate.get("gpt_analysis_status") or "not_run",
        "gpt_reason": candidate.get("gpt_reason"),
        "risk_flags": candidate.get("risk_flags") or [],
        "gating_notes": candidate.get("gating_notes") or [],
        "hard_blocked": not gpt_completed or not data_sufficient,
        "entry_ready": action == "buy",
    }

def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
