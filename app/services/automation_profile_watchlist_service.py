from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AutomationProfileWatchlistItem,
    AutomationProfileWatchlistSnapshot,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.services.compound_capital_service import CompoundCapitalService


class AutomationProfileWatchlistService:
    """Build a ranked universe per profile from the common raw KR snapshot.

    The raw market snapshot is intentionally shareable.  Every affordability
    filter, rank, top-quant/AI subset, and persisted selected symbol is scoped
    to one automation profile (and its nullable Admin/user owner scope).
    """

    def __init__(self, *, capital_service: CompoundCapitalService | None = None) -> None:
        self.capital_service = capital_service or CompoundCapitalService()

    def build(
        self,
        db: Session,
        *,
        profile: dict[str, Any],
        owner_user_id: int | None,
        scheduler_slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        profile_id = _positive_int(profile.get('id'), 'profile_id')
        provider = str(profile.get('provider') or 'kis').strip().lower()
        market = str(profile.get('market') or 'KR').strip().upper()
        current = _utc(now or datetime.now(UTC))
        snapshot_date = current.date().isoformat()
        existing = (
            db.query(AutomationProfileWatchlistSnapshot)
            .filter(
                AutomationProfileWatchlistSnapshot.profile_id == profile_id,
                AutomationProfileWatchlistSnapshot.owner_user_id == owner_user_id,
                AutomationProfileWatchlistSnapshot.snapshot_date == snapshot_date,
                AutomationProfileWatchlistSnapshot.scheduler_slot == str(scheduler_slot),
            )
            .first()
        )
        if existing is not None:
            return self.serialize(db, existing, include_items=True)

        settings = _settings(profile)
        universe = _object(settings.get('universe'))
        capital = _object(settings.get('capital'))
        raw_run = self._latest_raw_run(db, market=market)
        capital_state = self.capital_service.calculate(
            db,
            profile_key=str(profile.get('profile_key') or ''),
            initial_budget_krw=_number(capital.get('initial_budget_krw')),
            fixed_budget_krw=_number(capital.get('fixed_budget')),
            compound_enabled=bool(capital.get('compound_enabled')),
            compound_basis=str(capital.get('compound_basis') or 'realized_pnl'),
            provider=provider,
            market=market,
            configured_max_order_notional_krw=_number(capital.get('max_order_notional_krw')),
        )
        entry_budget = _number(capital_state.get('effective_next_entry_budget_krw'))
        configured_max = _number(universe.get('max_price_krw'))
        max_candidate_price = min(
            value for value in (configured_max, entry_budget) if value > 0
        ) if configured_max > 0 and entry_budget > 0 else 0.0
        selected, source_count, eligible_count = self._rank_raw_items(
            db,
            raw_run=raw_run,
            universe=universe,
            max_candidate_price=max_candidate_price,
        )
        watchlist_size = max(0, int(_number(universe.get('watchlist_size'))))
        top_quant = max(0, int(_number(universe.get('top_quant_candidates'))))
        top_ai = max(0, int(_number(universe.get('top_ai_candidates'))))
        selected = selected[:watchlist_size]
        diagnostics = {
            'profile_id': profile_id,
            'owner_user_id': owner_user_id,
            'raw_snapshot_id': raw_run.id if raw_run else None,
            'configured_min_price_krw': _number(universe.get('min_price_krw')),
            'configured_max_price_krw': configured_max,
            'effective_entry_budget_krw': entry_budget,
            'effective_max_candidate_price': max_candidate_price,
            'watchlist_size': watchlist_size,
            'top_quant_candidates': top_quant,
            'top_ai_candidates': top_ai,
            'capital_state': capital_state,
        }
        row = AutomationProfileWatchlistSnapshot(
            profile_id=profile_id,
            owner_user_id=owner_user_id,
            provider=provider,
            market=market,
            snapshot_date=snapshot_date,
            scheduler_slot=str(scheduler_slot),
            source_run_id=raw_run.id if raw_run else None,
            generated_at=current,
            source_count=source_count,
            eligible_count=eligible_count,
            selected_count=len(selected),
            effective_entry_budget_krw=entry_budget,
            effective_max_candidate_price=max_candidate_price,
            diagnostics_json=json.dumps(diagnostics, ensure_ascii=False, default=str),
            status='success' if raw_run is not None else 'empty',
        )
        db.add(row)
        try:
            db.flush()
            db.add_all([
                AutomationProfileWatchlistItem(
                    snapshot_id=row.id,
                    symbol=item['symbol'],
                    name=item['name'],
                    market=item['market'],
                    current_price=item['current_price'],
                    quant_buy_score=item['quant_buy_score'],
                    quant_sell_score=item['quant_sell_score'],
                    rank=index,
                    quant_rank=index,
                    ai_rank=index if index <= top_ai else None,
                    eligible=True,
                    indicators_json=json.dumps(item['indicators'], ensure_ascii=False, default=str),
                )
                for index, item in enumerate(selected, start=1)
            ])
            db.commit()
        except IntegrityError:
            db.rollback()
            duplicate = (
                db.query(AutomationProfileWatchlistSnapshot)
                .filter(
                    AutomationProfileWatchlistSnapshot.profile_id == profile_id,
                    AutomationProfileWatchlistSnapshot.owner_user_id == owner_user_id,
                    AutomationProfileWatchlistSnapshot.snapshot_date == snapshot_date,
                    AutomationProfileWatchlistSnapshot.scheduler_slot == str(scheduler_slot),
                )
                .first()
            )
            if duplicate is None:
                raise
            return self.serialize(db, duplicate, include_items=True)
        db.refresh(row)
        return self.serialize(db, row, include_items=True)

    def latest(
        self,
        db: Session,
        *,
        profile_id: int,
        owner_user_id: int | None,
    ) -> dict[str, Any]:
        query = db.query(AutomationProfileWatchlistSnapshot).filter(
            AutomationProfileWatchlistSnapshot.profile_id == int(profile_id),
        )
        query = query.filter(
            AutomationProfileWatchlistSnapshot.owner_user_id.is_(None)
            if owner_user_id is None
            else AutomationProfileWatchlistSnapshot.owner_user_id == int(owner_user_id)
        )
        row = query.order_by(
            AutomationProfileWatchlistSnapshot.generated_at.desc(),
            AutomationProfileWatchlistSnapshot.id.desc(),
        ).first()
        return self.serialize(db, row, include_items=True) if row else {'snapshot': None, 'items': []}

    def select_candidate(
        self,
        db: Session,
        *,
        profile: dict[str, Any],
        owner_user_id: int | None,
        scheduler_slot: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        snapshot = self.build(
            db,
            profile=profile,
            owner_user_id=owner_user_id,
            scheduler_slot=scheduler_slot,
            now=now,
        )
        items = snapshot.get('items') or []
        if not items:
            return None
        item = items[0]
        return {
            **item,
            'candidate_source': 'automation_profile_watchlist_snapshot',
            'automation_profile_id': int(profile['id']),
            'automation_profile_key': profile.get('profile_key'),
            'profile_snapshot_id': snapshot['snapshot']['id'],
        }

    def serialize(
        self,
        db: Session,
        row: AutomationProfileWatchlistSnapshot,
        *,
        include_items: bool = False,
    ) -> dict[str, Any]:
        diagnostics = _json_object(row.diagnostics_json)
        snapshot = {
            'id': row.id,
            'profile_id': row.profile_id,
            'owner_user_id': row.owner_user_id,
            'provider': row.provider,
            'market': row.market,
            'snapshot_date': row.snapshot_date,
            'scheduler_slot': row.scheduler_slot,
            'source_run_id': row.source_run_id,
            'generated_at': _iso(row.generated_at),
            'source_count': row.source_count,
            'eligible_count': row.eligible_count,
            'selected_count': row.selected_count,
            'effective_entry_budget_krw': row.effective_entry_budget_krw,
            'effective_max_candidate_price': row.effective_max_candidate_price,
            'diagnostics': diagnostics,
            'status': row.status,
        }
        items: list[dict[str, Any]] = []
        if include_items:
            rows = (
                db.query(AutomationProfileWatchlistItem)
                .filter(AutomationProfileWatchlistItem.snapshot_id == int(row.id))
                .order_by(AutomationProfileWatchlistItem.rank.asc(), AutomationProfileWatchlistItem.id.asc())
                .all()
            )
            items = [
                {
                    'symbol': item.symbol,
                    'name': item.name,
                    'market': item.market,
                    'current_price': item.current_price,
                    'quant_buy_score': item.quant_buy_score,
                    'quant_sell_score': item.quant_sell_score,
                    'rank': item.rank,
                    'quant_rank': item.quant_rank,
                    'ai_rank': item.ai_rank,
                    'eligible': bool(item.eligible),
                    'indicator_payload': _json_object(item.indicators_json),
                }
                for item in rows
            ]
        return {'snapshot': snapshot, 'items': items}

    @staticmethod
    def _latest_raw_run(db: Session, *, market: str) -> WatchlistSnapshotRun | None:
        return (
            db.query(WatchlistSnapshotRun)
            .filter(WatchlistSnapshotRun.market == market, WatchlistSnapshotRun.status == 'success')
            .order_by(WatchlistSnapshotRun.completed_at.desc(), WatchlistSnapshotRun.id.desc())
            .first()
        )

    @staticmethod
    def _rank_raw_items(
        db: Session,
        *,
        raw_run: WatchlistSnapshotRun | None,
        universe: dict[str, Any],
        max_candidate_price: float,
    ) -> tuple[list[dict[str, Any]], int, int]:
        if raw_run is None or max_candidate_price <= 0:
            return [], 0, 0
        min_price = _number(universe.get('min_price_krw'))
        allowed_markets = set()
        if universe.get('include_kospi', True):
            allowed_markets.add('KOSPI')
        if universe.get('include_kosdaq', True):
            allowed_markets.add('KOSDAQ')
        min_volume_ratio = universe.get('min_volume_ratio')
        result: list[dict[str, Any]] = []
        rows = db.query(WatchlistSnapshotItem).filter(WatchlistSnapshotItem.run_id == raw_run.id).all()
        for row in rows:
            price = _number(row.current_price)
            name = str(row.name or '')
            market = str(row.market or '').upper()
            indicators = _json_object(row.indicators_json)
            if not str(row.symbol or '').strip() or market not in allowed_markets:
                continue
            if price < min_price or price > max_candidate_price:
                continue
            if universe.get('exclude_preferred', True) and ('우선' in name or 'preferred' in name.lower()):
                continue
            if universe.get('exclude_etf', True) and 'ETF' in name.upper():
                continue
            if universe.get('exclude_etn', True) and 'ETN' in name.upper():
                continue
            if universe.get('exclude_spac', True) and ('SPAC' in name.upper() or '스팩' in name):
                continue
            if min_volume_ratio is not None and _number(indicators.get('volume_ratio')) < _number(min_volume_ratio):
                continue
            result.append({
                'symbol': str(row.symbol).strip().upper(),
                'name': name,
                'market': market,
                'current_price': price,
                'quant_buy_score': _number(row.quant_buy_score),
                'quant_sell_score': _number(row.quant_sell_score),
                'indicators': indicators,
            })
        result.sort(key=lambda item: (
            -item['quant_buy_score'], item['quant_sell_score'], item['symbol'],
        ))
        return result, len(rows), len(result)


def _settings(profile: dict[str, Any]) -> dict[str, Any]:
    # StrategyProfileService.serialize_profile exposes custom automation
    # settings as automation_settings, while AutomationProfileService.serialize
    # exposes them as effective_settings. Both are canonical profile payloads.
    for key in ('effective_settings', 'automation_settings', 'settings'):
        value = profile.get(key)
        if isinstance(value, dict) and value:
            return value
    return {}


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value)) if value is not None and not isinstance(value, bool) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _positive_int(value: Any, field: str) -> int:
    numeric = int(value or 0)
    if numeric <= 0:
        raise ValueError(f'{field}_required')
    return numeric


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat().replace('+00:00', 'Z') if value else None