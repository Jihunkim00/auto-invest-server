from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.db.models import WatchlistSnapshotItem, WatchlistSnapshotRun
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.quant_signal_service import QuantSignalService
from app.services.technical_indicator_service import (
    EMPTY_TECHNICAL_INDICATORS,
    TechnicalIndicatorService,
    indicator_payload_is_quant_ready,
)

logger = logging.getLogger(__name__)

KST = ZoneInfo('Asia/Seoul')
DEFAULT_KR_UNIVERSE_PATH = 'config/watchlist_kr_test4_universe.yaml'
SNAPSHOT_DAILY_BAR_LIMIT = 120


class WatchlistUniverseError(ValueError):
    pass


# Snapshot refresh state is intentionally independent from trading scheduler state.


class WatchlistSnapshotService:
    '''Build a KR market/quant snapshot without entering a trading path.'''

    _refresh_lock = threading.Lock()

    def __init__(self, *, client: Any | None = None,
                 client_factory: Callable[[Session], Any] | None = None,
                 universe_path: str | Path = DEFAULT_KR_UNIVERSE_PATH,
                 indicator_service: TechnicalIndicatorService | None = None,
                 quant_signal_service: QuantSignalService | None = None,
                 market_data_service_factory: Callable[[Any], MarketDataSnapshotService]
                 | None = None,
                 now_provider: Callable[[], datetime] | None = None) -> None:
        self.client = client
        self.client_factory = client_factory or self._default_client_factory
        self.universe_path = Path(universe_path)
        self.indicator_service = indicator_service or TechnicalIndicatorService()
        self.quant_signal_service = quant_signal_service or QuantSignalService()
        self.market_data_service_factory = (
            market_data_service_factory
            or (lambda value: MarketDataSnapshotService(value, now_provider=now_provider))
        )
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    @classmethod
    def is_refresh_running(cls) -> bool:
        return cls._refresh_lock.locked()

    def load_universe(self) -> list[dict[str, str]]:
        path = self._resolve_path(self.universe_path)
        if not path.exists():
            raise WatchlistUniverseError(f'KR snapshot universe not found: {path}')
        try:
            payload = yaml.safe_load(path.read_text(encoding='utf-8'))
        except (OSError, yaml.YAMLError) as exc:
            raise WatchlistUniverseError(
                f'KR snapshot universe could not be read: {path}'
            ) from exc

        raw_items = payload.get('symbols') if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            raise WatchlistUniverseError('KR snapshot universe must contain a symbols list.')

        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            symbol = str(raw.get('symbol') or raw.get('ticker') or '').strip()
            market = str(raw.get('market') or raw.get('listing_market') or '').strip().upper()
            if len(symbol) != 6 or not symbol.isdigit():
                continue
            if market not in {'KOSPI', 'KOSDAQ'} or symbol in seen:
                continue
            seen.add(symbol)
            name = str(raw.get('name') or raw.get('source_name') or symbol).strip()
            result.append({'symbol': symbol, 'name': name or symbol, 'market': market})

        if not result:
            raise WatchlistUniverseError('KR snapshot universe contains no usable symbols.')
        return result

    def refresh(self, db: Session, *, market: str = 'KR',
                gate_level: int = DEFAULT_GATE_LEVEL) -> dict[str, Any]:
        normalized_market = str(market or 'KR').strip().upper()
        if normalized_market != 'KR':
            raise ValueError('Watchlist snapshot currently supports KR only.')
        if not self._refresh_lock.acquire(blocking=False):
            return {
                'status': 'already_running',
                'market': normalized_market,
                'message': 'A watchlist snapshot refresh is already running.',
            }

        started_at = self._now_utc()
        started_monotonic = time.monotonic()
        run: WatchlistSnapshotRun | None = None
        try:
            universe = self.load_universe()
            run = WatchlistSnapshotRun(
                market=normalized_market,
                started_at=started_at,
                source_count=len(universe),
                status='running',
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            items: list[WatchlistSnapshotItem] = []
            scored_count = 0
            error_count = 0
            client = self.client or self.client_factory(db)
            market_data = self.market_data_service_factory(client)

            for source in universe:
                item, scored, had_error = self._build_item(
                    source,
                    market_data=market_data,
                    gate_level=gate_level,
                )
                items.append(WatchlistSnapshotItem(
                    run_id=run.id,
                    symbol=item['symbol'],
                    name=item['name'],
                    market=item['market'],
                    current_price=item['current_price'],
                    quant_buy_score=item['quant_buy_score'],
                    quant_sell_score=item['quant_sell_score'],
                    indicators_json=item['indicators_json'],
                    quant_reason=item['quant_reason'],
                    captured_at=item['captured_at'],
                ))
                scored_count += int(scored)
                error_count += int(had_error)

            db.add_all(items)
            run.scored_count = scored_count
            run.error_count = error_count
            run.completed_at = self._now_utc()
            run.elapsed_seconds = round(time.monotonic() - started_monotonic, 3)
            run.status = (
                'success'
                if universe and scored_count == len(universe) and error_count == 0
                else 'failed'
            )
            db.commit()
            db.refresh(run)
            payload = serialize_snapshot_run(run)
            logger.info(
                'watchlist snapshot refresh completed market=%s status=%s '
                'source_count=%s scored_count=%s error_count=%s started_at=%s '
                'completed_at=%s elapsed_seconds=%s',
                normalized_market, run.status, run.source_count, run.scored_count,
                run.error_count, run.started_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                run.elapsed_seconds,
            )
            return payload
        except Exception as exc:
            db.rollback()
            if run is not None and run.id is not None:
                try:
                    failed_run = db.get(WatchlistSnapshotRun, run.id)
                    if failed_run is not None:
                        failed_run.completed_at = self._now_utc()
                        failed_run.elapsed_seconds = round(
                            time.monotonic() - started_monotonic, 3
                        )
                        failed_run.status = 'failed'
                        failed_run.error_count = max(1, int(failed_run.error_count or 0))
                        db.commit()
                        db.refresh(failed_run)
                        return serialize_snapshot_run(failed_run)
                except Exception:
                    db.rollback()
            logger.exception('watchlist snapshot refresh failed market=%s', normalized_market)
            raise exc
        finally:
            self._refresh_lock.release()

    def latest_successful_run(self, db: Session, *, market: str = 'KR') -> WatchlistSnapshotRun | None:
        return (
            db.query(WatchlistSnapshotRun)
            .filter(
                WatchlistSnapshotRun.market == str(market or 'KR').strip().upper(),
                WatchlistSnapshotRun.status == 'success',
            )
            .order_by(
                WatchlistSnapshotRun.completed_at.desc(),
                WatchlistSnapshotRun.id.desc(),
            )
            .first()
        )

    def latest_run(self, db: Session, *, market: str = 'KR') -> WatchlistSnapshotRun | None:
        return (
            db.query(WatchlistSnapshotRun)
            .filter(WatchlistSnapshotRun.market == str(market or 'KR').strip().upper())
            .order_by(
                WatchlistSnapshotRun.started_at.desc(),
                WatchlistSnapshotRun.id.desc(),
            )
            .first()
        )

    def _build_item(self, source: dict[str, str], *,
                    market_data: MarketDataSnapshotService,
                    gate_level: int) -> tuple[dict[str, Any], bool, bool]:
        symbol = source['symbol']
        captured_at = self._now_utc()
        current_price: float | None = None
        indicators: dict[str, Any] = {}
        quant: dict[str, Any] = {
            'quant_buy_score': 0.0,
            'quant_sell_score': 0.0,
            'quant_reason': 'insufficient data',
        }
        had_error = False
        scored = False
        name = source['name']
        try:
            raw = market_data.snapshot(symbol, daily_limit=SNAPSHOT_DAILY_BAR_LIMIT)
            captured_at = _parse_datetime(raw.get('captured_at'), captured_at)
            quote = raw.get('quote') if isinstance(raw, dict) else None
            if isinstance(quote, dict):
                current_price = _finite(quote.get('current_price'))
                name = str(quote.get('name') or '').strip() or name
            had_error = bool(raw.get('quote_error') or raw.get('daily_error'))
            indicator_result = self.indicator_service.calculate(
                list(raw.get('daily_bars') or []),
                current_price=current_price,
            )
            indicators = dict(
                indicator_result.get('indicator_payload') or EMPTY_TECHNICAL_INDICATORS
            )
            if current_price is None:
                current_price = _finite(indicators.get('price'))
            if indicator_payload_is_quant_ready(indicators):
                quant = self.quant_signal_service.score(indicators, gate_level=gate_level)
                scored = True
            else:
                had_error = True
        except Exception:
            had_error = True

        item = {
            'symbol': symbol,
            'name': name,
            'market': source['market'],
            'current_price': current_price,
            'quant_buy_score': round(float(quant.get('quant_buy_score') or 0.0), 2),
            'quant_sell_score': round(float(quant.get('quant_sell_score') or 0.0), 2),
            'indicators_json': json.dumps(indicators, ensure_ascii=False, sort_keys=True),
            'quant_reason': str(quant.get('quant_reason') or 'insufficient data'),
            'captured_at': captured_at,
        }
        return item, scored, had_error

    def _default_client_factory(self, db: Session) -> KisClient:
        settings = get_settings()
        return KisClient(settings, KisAuthManager(settings, db))

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    def _now_utc(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def serialize_snapshot_item(row: WatchlistSnapshotItem) -> dict[str, Any]:
    try:
        indicators = json.loads(row.indicators_json or '{}')
    except (TypeError, ValueError):
        indicators = {}
    if not isinstance(indicators, dict):
        indicators = {}
    return {
        'id': row.id,
        'run_id': row.run_id,
        'symbol': row.symbol,
        'name': row.name,
        'market': row.market,
        'current_price': row.current_price,
        'quant_buy_score': row.quant_buy_score,
        'quant_sell_score': row.quant_sell_score,
        'indicators': indicators,
        'indicators_json': indicators,
        'quant_reason': row.quant_reason,
        'captured_at': _iso(row.captured_at),
    }


def serialize_snapshot_run(row: WatchlistSnapshotRun, *,
                           include_items: bool = False,
                           items: list[WatchlistSnapshotItem] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'snapshot_id': row.id,
        'id': row.id,
        'market': row.market,
        'started_at': _iso(row.started_at),
        'completed_at': _iso(row.completed_at),
        'source_count': row.source_count,
        'scored_count': row.scored_count,
        'error_count': row.error_count,
        'elapsed_seconds': row.elapsed_seconds,
        'status': row.status,
    }
    if include_items:
        payload['items'] = [serialize_snapshot_item(item) for item in (items or [])]
    return payload


def _parse_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or '').strip()
        if not text:
            return fallback
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _parse_datetime(value, datetime.now(UTC)).isoformat().replace('+00:00', 'Z')


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
