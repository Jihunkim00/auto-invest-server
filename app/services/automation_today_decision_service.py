from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import (
    AutomationProfileAiCandidateResult,
    AutomationProfileWatchlistItem,
    AutomationProfileWatchlistSnapshot,
    SignalLog,
    TradeRunLog,
)
from app.services.automation_profile_service import AutomationProfileService


KST = ZoneInfo('Asia/Seoul')
_INVALID_SYMBOLS = {'', 'NONE', 'NULL', 'UNKNOWN'}


class AutomationTodayDecisionService:
    """Read-only, owner/profile/slot-scoped feed for the home decision card."""

    def __init__(self, *, profiles: AutomationProfileService | None = None) -> None:
        self.profiles = profiles or AutomationProfileService()

    def get_today(
        self,
        db: Session,
        *,
        owner_user_id: int | None = None,
        admin_user_id: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(now or datetime.now(UTC))
        schedule = self._schedule(
            db,
            owner_user_id=owner_user_id,
            admin_user_id=admin_user_id,
            now=current,
        )
        if schedule is None:
            return {
                'trade_date_kst': current.astimezone(KST).date().isoformat(),
                'timezone': 'Asia/Seoul',
                'provider': None,
                'market': None,
                'profile_id': None,
                'profile_key': None,
                'profile_name': None,
                'owner_user_id': owner_user_id,
                'profile_status': None,
                'slots': [],
            }

        profile = schedule.get('profile') or {}
        timezone = _timezone(schedule.get('timezone'), profile.get('market'))
        local_date = current.astimezone(timezone).date()
        runs = self._runs_for_day(
            db,
            owner_user_id=owner_user_id,
            admin_user_id=admin_user_id,
            start=_local_boundary(local_date, timezone),
            end=_local_boundary(local_date + timedelta(days=1), timezone),
        )
        decisions = [
            self._decision_for_slot(
                db,
                run=self._run_for_slot(runs, slot, current, timezone),
                profile=profile,
                schedule=schedule,
                slot=slot,
                local_date=local_date,
                now=current,
                admin_user_id=admin_user_id,
            )
            for slot in self._slots(schedule)
        ]
        return {
            'trade_date_kst': local_date.isoformat(),
            'timezone': str(schedule.get('timezone') or 'Asia/Seoul'),
            'provider': profile.get('provider'),
            'market': profile.get('market'),
            'profile_id': _int_or_none(profile.get('id')),
            'profile_key': profile.get('profile_key'),
            'profile_name': profile.get('custom_name') or profile.get('display_name'),
            'owner_user_id': (
                profile.get('owner_user_id')
                if owner_user_id is None
                else owner_user_id
            ),
            'profile_status': schedule.get('status'),
            'slots': decisions,
        }

    def _schedule(
        self,
        db: Session,
        *,
        owner_user_id: int | None,
        admin_user_id: int | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        if owner_user_id is not None:
            return self.profiles.selected_owned_profile_schedule(
                db, owner_user_id=int(owner_user_id), now=now,
            )
        if admin_user_id is not None:
            return self.profiles.selected_profile_schedule(db, now=now)
        return None

    @staticmethod
    def _slots(schedule: dict[str, Any]) -> list[str]:
        values = schedule.get('analysis_times') or []
        return sorted({str(value) for value in values if _valid_slot(value)})

    @staticmethod
    def _runs_for_day(
        db: Session,
        *,
        owner_user_id: int | None,
        admin_user_id: int | None,
        start: datetime,
        end: datetime,
    ) -> list[TradeRunLog]:
        query = db.query(TradeRunLog).filter(
            TradeRunLog.created_at >= start,
            TradeRunLog.created_at < end,
        )
        if owner_user_id is not None:
            query = query.filter(
                TradeRunLog.owner_user_id == int(owner_user_id),
                TradeRunLog.trigger_source == 'user_scheduler',
            )
        elif admin_user_id is not None:
            query = query.filter(
                or_(
                    TradeRunLog.owner_user_id.is_(None),
                    TradeRunLog.owner_user_id == int(admin_user_id),
                ),
                TradeRunLog.trigger_source == 'automation_scheduler',
                TradeRunLog.mode == 'automation_scheduler_profile_analysis',
            )
        else:
            return []
        return query.order_by(
            TradeRunLog.created_at.desc(), TradeRunLog.id.desc()
        ).all()

    def _run_for_slot(
        self,
        runs: list[TradeRunLog],
        slot: str,
        now: datetime,
        timezone: ZoneInfo,
    ) -> TradeRunLog | None:
        exact: list[TradeRunLog] = []
        for run in runs:
            request = _json(run.request_payload)
            response = _json(run.response_payload)
            value = (
                request.get('scheduler_slot')
                or response.get('scheduler_slot')
                or response.get('slot_kst')
            )
            if str(value or '') == slot:
                exact.append(run)
        if exact:
            return exact[0]

        # Legacy Admin rows had no explicit slot. Link them only when the
        # timestamp is close to this profile's slot on the same local date.
        hour, minute = (int(part) for part in slot.split(':', 1))
        target = now.astimezone(timezone).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        candidates = [
            run for run in runs
            if abs(
                (_aware_utc(run.created_at) - target.astimezone(UTC)).total_seconds()
            ) <= 15 * 60
        ]
        return candidates[0] if candidates else None

    def _decision_for_slot(
        self,
        db: Session,
        *,
        run: TradeRunLog | None,
        profile: dict[str, Any],
        schedule: dict[str, Any],
        slot: str,
        local_date: date,
        now: datetime,
        admin_user_id: int | None,
    ) -> dict[str, Any]:
        profile_id = _int_or_none(profile.get('id'))
        owner = _int_or_none(profile.get('owner_user_id'))
        pipeline = self._pipeline_for_slot(
            db,
            profile_id=profile_id,
            owner_user_id=owner,
            admin_user_id=admin_user_id,
            local_date=local_date,
            slot=slot,
        )
        base = {
            'scheduler_slot': slot,
            'profile_id': profile_id,
            'profile_key': profile.get('profile_key'),
            'profile_name': profile.get('custom_name') or profile.get('display_name'),
            'owner_user_id': owner,
            **pipeline,
            'status': (
                'analysis_pending'
                if _slot_future(slot, local_date, now, schedule)
                else 'no_result'
            ),
            'signal_status': None,
            'run_id': None,
            'run_key': None,
            'signal_id': None,
            'symbol': None,
            'symbol_name': None,
            'action': None,
            'final_buy_score': None,
            'final_sell_score': None,
            'confidence': None,
            'reason': None,
            'ai_reason': None,
            'created_at': None,
            'created_at_kst': None,
        }
        if run is None:
            return base

        request = _json(run.request_payload)
        response = _json(run.response_payload)
        context = _profile_context(request, response)
        if (
            profile_id is not None
            and context.get('profile_id') is not None
            and context['profile_id'] != profile_id
        ):
            return base
        profile_key = str(profile.get('profile_key') or '').strip().lower()
        context_key = str(context.get('profile_key') or '').strip().lower()
        if profile_key and context_key and profile_key != context_key:
            return base
        symbol = _normalize_symbol(
            response.get('returned_symbol')
            or response.get('analyzed_symbol')
            or run.symbol
        )
        if symbol in _INVALID_SYMBOLS:
            # A completed scheduler run may have no executable symbol when the
            # C gate produces no GPT/final candidate. This is not no_result.
            if pipeline.get('profile_snapshot_id') is None:
                return base
            created_at = _aware_utc(run.created_at)
            return {
                **base,
                'status': 'analysis_complete',
                'signal_status': run.result,
                'run_id': run.id,
                'run_key': run.run_key,
                'signal_id': run.signal_id,
                'action': 'hold',
                'reason': 'no_completed_gpt_final_candidate',
                'created_at': created_at.isoformat().replace('+00:00', 'Z'),
                'created_at_kst': created_at.astimezone(KST).isoformat(),
            }
        signal = db.get(SignalLog, run.signal_id) if run.signal_id else None
        if (signal is not None and admin_user_id is None and owner is not None
                and signal.owner_user_id != owner):
            return base
        if (
            signal is not None
            and admin_user_id is not None
            and signal.owner_user_id not in {None, int(admin_user_id)}
        ):
            return base

        snapshot_item = self._snapshot_item(
            db,
            profile_id=profile_id,
            owner_user_id=owner,
            admin_user_id=admin_user_id,
            local_date=local_date,
            slot=slot,
            symbol=symbol,
        )
        # The snapshot is the authoritative profile link for old rows that did
        # not persist profile_id. It also supplies the display-name snapshot.
        if snapshot_item is None:
            return base
        analysis = (
            response.get('analysis')
            if isinstance(response.get('analysis'), dict)
            else {}
        )
        action = (
            signal.action
            if signal is not None
            else response.get('action') or response.get('result')
        )
        reason = signal.reason if signal is not None else response.get('reason')
        created_at = _aware_utc(run.created_at)
        return {
            **base,
            'status': 'result',
            'signal_status': signal.signal_status if signal is not None else run.result,
            'run_id': run.id,
            'run_key': run.run_key,
            'signal_id': signal.id if signal is not None else run.signal_id,
            'symbol': symbol,
            'symbol_name': (
                snapshot_item.name
                or response.get('selected_symbol_name')
                or response.get('symbol_name')
            ),
            'action': str(action or 'hold').lower(),
            'final_buy_score': _first(
                signal.final_buy_score if signal is not None else None,
                response.get('final_buy_score'),
                analysis.get('final_buy_score'),
                analysis.get('score'),
            ),
            'final_sell_score': _first(
                signal.final_sell_score if signal is not None else None,
                response.get('final_sell_score'),
                analysis.get('final_sell_score'),
            ),
            'confidence': _first(
                signal.confidence if signal is not None else None,
                response.get('confidence'),
                analysis.get('confidence'),
            ),
            'reason': reason,
            'ai_reason': _first(
                signal.ai_reason if signal is not None else None,
                analysis.get('ai_reason'),
                analysis.get('gpt_reason'),
            ),
            'created_at': created_at.isoformat().replace('+00:00', 'Z'),
            'created_at_kst': created_at.astimezone(KST).isoformat(),
            'quant_rank': snapshot_item.quant_rank,
            'ai_rank': snapshot_item.ai_rank,
            'profile_snapshot_id': snapshot_item.snapshot_id,
        }

    @staticmethod
    def _pipeline_for_slot(
        db: Session,
        *,
        profile_id: int | None,
        owner_user_id: int | None,
        admin_user_id: int | None,
        local_date: date,
        slot: str,
    ) -> dict[str, Any]:
        empty = {
            'profile_snapshot_id': None,
            'snapshot_source_count': None,
            'snapshot_eligible_count': None,
            'snapshot_selected_count': None,
            'runtime_quant_candidate_count': 0,
            'runtime_quant_top5_symbols': [],
            'gpt_target_symbols': [],
            'gpt_target_count': 0,
            'gpt_completed_symbols': [],
            'gpt_completed_count': 0,
            'gpt_failed_symbols': [],
            'gpt_failed_count': 0,
            'final_candidate_symbols': [],
            'final_candidate_count': 0,
            'final_ranked_top5': [],
            'final_selected_symbol': None,
        }
        if profile_id is None:
            return empty
        snapshot_query = db.query(AutomationProfileWatchlistSnapshot).filter(
            AutomationProfileWatchlistSnapshot.profile_id == int(profile_id),
            AutomationProfileWatchlistSnapshot.snapshot_date == local_date.isoformat(),
            AutomationProfileWatchlistSnapshot.scheduler_slot == str(slot),
        )
        if admin_user_id is not None:
            snapshot_query = snapshot_query.filter(or_(
                AutomationProfileWatchlistSnapshot.owner_user_id.is_(None),
                AutomationProfileWatchlistSnapshot.owner_user_id == int(admin_user_id),
            ))
        elif owner_user_id is None:
            snapshot_query = snapshot_query.filter(
                AutomationProfileWatchlistSnapshot.owner_user_id.is_(None)
            )
        else:
            snapshot_query = snapshot_query.filter(
                AutomationProfileWatchlistSnapshot.owner_user_id == int(owner_user_id)
            )
        snapshot = snapshot_query.order_by(
            AutomationProfileWatchlistSnapshot.id.desc()
        ).first()
        query = db.query(AutomationProfileAiCandidateResult).filter(
            AutomationProfileAiCandidateResult.profile_id == int(profile_id),
            AutomationProfileAiCandidateResult.snapshot_date == local_date.isoformat(),
            AutomationProfileAiCandidateResult.scheduler_slot == str(slot),
        )
        if admin_user_id is not None:
            query = query.filter(or_(
                AutomationProfileAiCandidateResult.owner_user_id.is_(None),
                AutomationProfileAiCandidateResult.owner_user_id == int(admin_user_id),
            ))
        elif owner_user_id is None:
            query = query.filter(
                AutomationProfileAiCandidateResult.owner_user_id.is_(None)
            )
        else:
            query = query.filter(
                AutomationProfileAiCandidateResult.owner_user_id == int(owner_user_id)
            )
        rows = query.order_by(
            AutomationProfileAiCandidateResult.runtime_quant_rank.asc(),
            AutomationProfileAiCandidateResult.id.asc(),
        ).all()
        if not rows:
            if snapshot is None:
                return empty
            return {
                **empty,
                'profile_snapshot_id': snapshot.id,
                'snapshot_source_count': snapshot.source_count,
                'snapshot_eligible_count': snapshot.eligible_count,
                'snapshot_selected_count': snapshot.selected_count,
            }

        def candidate(row: AutomationProfileAiCandidateResult) -> dict[str, Any]:
            final_score = row.final_buy_score
            return {
                'symbol': row.symbol,
                'name': row.symbol_name,
                'symbol_name': row.symbol_name,
                'snapshot_rank': row.snapshot_rank,
                'runtime_quant_rank': row.runtime_quant_rank,
                'quant_buy_score': row.runtime_quant_buy_score,
                'quant_sell_score': row.runtime_quant_sell_score,
                'gpt_target_rank': row.gpt_target_rank,
                'gpt_used': bool(row.gpt_used),
                'gpt_analysis_status': row.gpt_analysis_status,
                'ai_buy_score': row.ai_buy_score,
                'ai_sell_score': row.ai_sell_score,
                'confidence': row.confidence,
                'ai_reason': row.ai_reason,
                'final_buy_score': final_score,
                'final_sell_score': row.final_sell_score,
                'final_entry_score': final_score,
                'final_rank': row.final_rank,
                'final_selected': bool(row.final_selected),
                'score': final_score,
                'entry_ready': False,
                'action': 'watch',
                'action_hint': 'watch',
            }

        runtime_rows = [row for row in rows if row.runtime_quant_rank is not None]
        target_rows = sorted(
            [row for row in rows if row.gpt_target_rank is not None],
            key=lambda row: (row.gpt_target_rank, row.id),
        )
        completed_rows = [
            row for row in target_rows
            if bool(row.gpt_used)
            and str(row.gpt_analysis_status or '').lower() == 'completed'
            and row.ai_buy_score is not None
            and row.ai_sell_score is not None
        ]
        failed_rows = [row for row in target_rows if row not in completed_rows]
        final_rows = sorted(
            [row for row in rows if row.final_rank is not None],
            key=lambda row: (row.final_rank, row.id),
        )
        snapshot = (
            db.get(AutomationProfileWatchlistSnapshot, int(rows[0].snapshot_id))
            if rows[0].snapshot_id is not None
            else snapshot
        )
        final_items = [candidate(row) for row in final_rows[:5]]
        return {
            'profile_snapshot_id': rows[0].snapshot_id,
            'snapshot_source_count': snapshot.source_count if snapshot else None,
            'snapshot_eligible_count': snapshot.eligible_count if snapshot else None,
            'snapshot_selected_count': snapshot.selected_count if snapshot else None,
            'runtime_quant_candidate_count': len(runtime_rows),
            'runtime_quant_top5_symbols': [
                row.symbol for row in sorted(
                    runtime_rows,
                    key=lambda row: (row.runtime_quant_rank, row.id),
                )[:5]
            ],
            'gpt_target_symbols': [row.symbol for row in target_rows],
            'gpt_target_count': len(target_rows),
            'gpt_completed_symbols': [row.symbol for row in completed_rows],
            'gpt_completed_count': len(completed_rows),
            'gpt_failed_symbols': [row.symbol for row in failed_rows],
            'gpt_failed_count': len(failed_rows),
            'final_candidate_symbols': [row.symbol for row in final_rows],
            'final_candidate_count': len(final_rows),
            'final_ranked_top5': final_items,
            'final_selected_symbol': next(
                (row.symbol for row in final_rows if row.final_selected),
                final_rows[0].symbol if final_rows else None,
            ),
        }
    @staticmethod
    def _snapshot_item(
        db: Session,
        *,
        profile_id: int | None,
        owner_user_id: int | None,
        admin_user_id: int | None,
        local_date: date,
        slot: str,
        symbol: str,
    ) -> AutomationProfileWatchlistItem | None:
        if profile_id is None:
            return None
        query = (
            db.query(AutomationProfileWatchlistItem)
            .join(
                AutomationProfileWatchlistSnapshot,
                AutomationProfileWatchlistItem.snapshot_id
                == AutomationProfileWatchlistSnapshot.id,
            )
            .filter(
                AutomationProfileWatchlistSnapshot.profile_id == profile_id,
                AutomationProfileWatchlistSnapshot.snapshot_date == local_date.isoformat(),
                AutomationProfileWatchlistSnapshot.scheduler_slot == slot,
                AutomationProfileWatchlistItem.symbol == symbol,
                AutomationProfileWatchlistItem.eligible.is_(True),
            )
        )
        if admin_user_id is not None:
            query = query.filter(
                or_(
                    AutomationProfileWatchlistSnapshot.owner_user_id.is_(None),
                    AutomationProfileWatchlistSnapshot.owner_user_id == int(admin_user_id),
                )
            )
        elif owner_user_id is None:
            query = query.filter(
                AutomationProfileWatchlistSnapshot.owner_user_id.is_(None)
            )
        else:
            query = query.filter(
                AutomationProfileWatchlistSnapshot.owner_user_id == owner_user_id
            )
        return query.first()


def _json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or '{}')
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _profile_context(*payloads: dict[str, Any]) -> dict[str, Any]:
    for payload in payloads:
        for key in ('profile_context', 'automation_profile', 'candidate'):
            value = payload.get(key)
            if isinstance(value, dict) and (
                _int_or_none(value.get('profile_id'))
                or value.get('automation_profile_id')
            ):
                return {
                    'profile_id': _int_or_none(
                        value.get('profile_id') or value.get('automation_profile_id')
                    ),
                    'profile_key': value.get('profile_key') or value.get(
                        'automation_profile_key'
                    ),
                }
        value = _int_or_none(
            payload.get('profile_id') or payload.get('automation_profile_id')
        )
        if value is not None:
            return {
                'profile_id': value,
                'profile_key': payload.get('profile_key') or payload.get(
                    'automation_profile_key'
                ),
            }
    for payload in payloads:
        if payload.get('profile_key') or payload.get('automation_profile_key'):
            return {
                'profile_id': _int_or_none(
                    payload.get('profile_id') or payload.get('automation_profile_id')
                ),
                'profile_key': payload.get('profile_key') or payload.get(
                    'automation_profile_key'
                ),
            }
    return {}


def _timezone(value: Any, market: Any) -> ZoneInfo:
    name = str(value or '').strip()
    if not name:
        name = (
            'Asia/Seoul'
            if str(market or '').upper() == 'KR'
            else 'America/New_York'
        )
    try:
        return ZoneInfo(name)
    except Exception:
        return KST


def _local_boundary(value: date, timezone: ZoneInfo) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone).astimezone(UTC)


def _slot_future(
    slot: str,
    local_date: date,
    now: datetime,
    schedule: dict[str, Any],
) -> bool:
    timezone = _timezone(
        schedule.get('timezone'),
        (schedule.get('profile') or {}).get('market'),
    )
    hour, minute = (int(part) for part in slot.split(':', 1))
    return datetime.combine(
        local_date, time(hour, minute), tzinfo=timezone
    ) > now.astimezone(timezone)


def _valid_slot(value: Any) -> bool:
    try:
        hour, minute = (int(part) for part in str(value).split(':', 1))
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except (TypeError, ValueError):
        return False


def _normalize_symbol(value: Any) -> str:
    return str(value or '').strip().upper()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
