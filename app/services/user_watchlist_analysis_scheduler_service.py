from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import User, UserWatchlist, UserWatchlistAnalysis
from app.services.user_symbol_analysis_service import UserSymbolAnalysisService


USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE = 'user_watchlist_analysis'
USER_WATCHLIST_ANALYSIS_JOB_ID_PREFIX = 'user_watchlist_analysis_kis'
KST = ZoneInfo('Asia/Seoul')
KR_WATCHLIST_ANALYSIS_SLOTS = ('09:30', '12:00', '14:30')


class UserWatchlistAnalysisSchedulerService:
    """Scheduled personal-favorite analysis with no trading side effects."""

    def __init__(
        self,
        *,
        analysis_service: UserSymbolAnalysisService | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.analysis_service = analysis_service or UserSymbolAnalysisService()
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self._last_status: dict[str, Any] = {}

    @staticmethod
    def job_id(slot: str) -> str:
        return f"{USER_WATCHLIST_ANALYSIS_JOB_ID_PREFIX}_{slot.replace(':', '')}"

    def dispatcher_jobs(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        return [
            {
                'job_id': self.job_id(slot),
                'provider': 'kis',
                'market': 'KR',
                'slot': slot,
                'timezone': 'Asia/Seoul',
                'recurring': True,
                'automatic': True,
                'analytics_only': True,
                'trigger_source': USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE,
                'order_submission': False,
            }
            for slot in KR_WATCHLIST_ANALYSIS_SLOTS
        ]

    def due_slots(self, *, now: datetime | None = None) -> list[str]:
        current = _utc(now or self.now_provider()).astimezone(KST)
        return [
            slot for slot in KR_WATCHLIST_ANALYSIS_SLOTS
            if _slot_time(current, slot) <= current < _slot_time(current, slot) + timedelta(minutes=1)
        ]

    def run_once(
        self,
        db: Session,
        *,
        scheduler_slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if scheduler_slot not in KR_WATCHLIST_ANALYSIS_SLOTS:
            raise ValueError('unsupported_watchlist_analysis_slot')
        current = _utc(now or self.now_provider())
        local = current.astimezone(KST)
        result: dict[str, Any] = {
            'trigger_source': USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE,
            'scheduler_slot': scheduler_slot,
            'provider': 'kis',
            'market': 'KR',
            'analytics_only': True,
            'processed': 0,
            'stored': 0,
            'failed': 0,
            'items': [],
            'real_order_submitted': False,
            'broker_submit_called': False,
            'risk_approval_called': False,
        }
        users = (
            db.query(User)
            .filter(User.enabled.is_(True))
            .order_by(User.id.asc())
            .all()
        )
        for user in users:
            if str(user.role or '').strip().lower() == 'admin':
                continue
            favorites = (
                db.query(UserWatchlist)
                .filter(
                    UserWatchlist.user_id == int(user.id),
                    UserWatchlist.provider == 'kis',
                    UserWatchlist.market.in_(['KR', 'KOSPI', 'KOSDAQ']),
                )
                .order_by(UserWatchlist.id.asc())
                .all()
            )
            for favorite in favorites:
                result['processed'] += 1
                symbol = str(favorite.symbol or '').strip().upper().zfill(6)
                try:
                    analysis = dict(self.analysis_service.analyze(
                        db,
                        provider='kis',
                        symbol=symbol,
                        gate_level=2,
                        now=current,
                    ) or {})
                    row = self._upsert(
                        db,
                        user_id=int(user.id),
                        symbol=symbol,
                        scheduler_slot=scheduler_slot,
                        analysis_date=local.date().isoformat(),
                        analyzed_at=current,
                        analysis=analysis,
                    )
                    result['stored'] += 1
                    result['items'].append(self.serialize(row))
                except Exception as exc:
                    db.rollback()
                    result['failed'] += 1
                    result['items'].append({
                        'owner_user_id': int(user.id),
                        'symbol': symbol,
                        'result': 'failed',
                        'reason': f'watchlist_analysis_failed:{exc.__class__.__name__}',
                    })
        result['result'] = 'failed' if result['failed'] and not result['stored'] else 'completed'
        self._last_status = result
        return result

    @staticmethod
    def _upsert(
        db: Session,
        *,
        user_id: int,
        symbol: str,
        scheduler_slot: str,
        analysis_date: str,
        analyzed_at: datetime,
        analysis: dict[str, Any],
    ) -> UserWatchlistAnalysis:
        row = (
            db.query(UserWatchlistAnalysis)
            .filter(
                UserWatchlistAnalysis.user_id == user_id,
                UserWatchlistAnalysis.symbol == symbol,
                UserWatchlistAnalysis.provider == 'kis',
                UserWatchlistAnalysis.analysis_date == analysis_date,
                UserWatchlistAnalysis.scheduler_slot == scheduler_slot,
            )
            .first()
        )
        if row is None:
            row = UserWatchlistAnalysis(
                user_id=user_id,
                symbol=symbol,
                provider='kis',
                market='KR',
                analysis_date=analysis_date,
                scheduler_slot=scheduler_slot,
                analyzed_at=analyzed_at,
            )
            db.add(row)
        row.analyzed_at = analyzed_at
        row.quant_buy_score = _number(analysis.get('quant_buy_score'))
        row.quant_sell_score = _number(analysis.get('quant_sell_score'))
        row.ai_buy_score = _number(analysis.get('ai_buy_score'))
        row.ai_sell_score = _number(analysis.get('ai_sell_score'))
        row.final_buy_score = _number(analysis.get('final_buy_score') or analysis.get('score'))
        row.final_sell_score = _number(analysis.get('final_sell_score'))
        row.confidence = _number(analysis.get('confidence'))
        row.action = str(analysis.get('action') or 'watch')[:30]
        row.reason = str(analysis.get('reason') or '')
        row.indicator_payload = json.dumps(
            analysis.get('indicator_payload') or {}, ensure_ascii=False, default=str,
        )
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def serialize(row: UserWatchlistAnalysis) -> dict[str, Any]:
        try:
            indicators = json.loads(row.indicator_payload or '{}')
        except (TypeError, ValueError):
            indicators = {}
        return {
            'id': row.id,
            'owner_user_id': row.user_id,
            'symbol': row.symbol,
            'provider': row.provider,
            'market': row.market,
            'analyzed_at': row.analyzed_at.isoformat() if row.analyzed_at else None,
            'scheduler_slot': row.scheduler_slot,
            'quant_buy_score': row.quant_buy_score,
            'quant_sell_score': row.quant_sell_score,
            'ai_buy_score': row.ai_buy_score,
            'ai_sell_score': row.ai_sell_score,
            'final_buy_score': row.final_buy_score,
            'final_sell_score': row.final_sell_score,
            'confidence': row.confidence,
            'action': row.action,
            'reason': row.reason,
            'indicator_payload': indicators,
            'trigger_source': USER_WATCHLIST_ANALYSIS_TRIGGER_SOURCE,
            'analytics_only': True,
        }


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _slot_time(now: datetime, slot: str) -> datetime:
    hour, minute = (int(part) for part in slot.split(':', 1))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None