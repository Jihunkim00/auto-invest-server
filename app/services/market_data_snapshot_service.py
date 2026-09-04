from __future__ import annotations

import copy
import math
import threading
import time
from datetime import UTC, date, datetime, time as date_time
from typing import Any
from zoneinfo import ZoneInfo


KST = ZoneInfo('Asia/Seoul')
DAILY_CACHE_PROVIDER = 'kis'
DAILY_CACHE_MARKET = 'KR'
INTRADAY_MAX_FRESHNESS_SECONDS = 600.0


class MarketDataSnapshotService:
    '''Coordinate one watchlist run's market-data reads.'''

    _daily_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    _daily_cache_lock = threading.RLock()

    def __init__(
        self,
        client,
        *,
        daily_cache_ttl_seconds: float = 86_400.0,
        now_provider=None,
    ) -> None:
        self.client = client
        self.daily_cache_ttl_seconds = max(1.0, float(daily_cache_ttl_seconds))
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self._stats = self._empty_stats()

    @classmethod
    def clear_process_cache(cls) -> None:
        with cls._daily_cache_lock:
            cls._daily_cache.clear()

    def reset_run_stats(self) -> None:
        self._stats = self._empty_stats()

    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def snapshot(self, symbol: str, *, daily_limit: int = 120) -> dict[str, Any]:
        normalized_symbol = str(symbol or '').strip().upper()
        captured_at = self._now_utc().isoformat()
        quote: dict[str, Any] | None = None
        daily_bars: list[dict[str, Any]] = []
        quote_error: str | None = None
        daily_error: str | None = None

        self._stats['price_request_count'] += 1
        try:
            quote = self.client.get_domestic_stock_price(normalized_symbol)
        except Exception as exc:
            quote_error = _safe_error(exc)

        try:
            daily_bars, daily_metadata = self.get_daily_bars(
                normalized_symbol,
                limit=daily_limit,
            )
        except Exception as exc:
            daily_metadata = {
                'daily_cache_hit': False,
                'daily_cache_miss': True,
                'daily_cache_key': self._cache_key(normalized_symbol),
            }
            daily_error = _safe_error(exc)

        return {
            'symbol': normalized_symbol,
            'quote': quote,
            'daily_bars': daily_bars,
            'captured_at': captured_at,
            'quote_error': quote_error,
            'daily_error': daily_error,
            'daily_cache_hit': bool(daily_metadata.get('daily_cache_hit')),
            'daily_cache_miss': bool(daily_metadata.get('daily_cache_miss')),
            'daily_cache_key': daily_metadata.get('daily_cache_key'),
            'daily_bars_source': daily_metadata.get('source', 'kis'),
        }

    def get_daily_bars(
        self,
        symbol: str,
        *,
        limit: int = 120,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        normalized_symbol = str(symbol or '').strip().upper()
        key = self._cache_key(normalized_symbol)
        now_monotonic = time.monotonic()

        with self._daily_cache_lock:
            cached = self._daily_cache.get(key)
            if cached is not None:
                age = now_monotonic - float(cached.get('stored_monotonic', 0.0))
                bars = cached.get('bars')
                if age <= self.daily_cache_ttl_seconds and _valid_daily_bars(bars):
                    self._stats['daily_cache_hit_count'] += 1
                    return copy.deepcopy(bars)[-max(1, int(limit or 120)) :], {
                        'daily_cache_hit': True,
                        'daily_cache_miss': False,
                        'daily_cache_key': key,
                        'source': 'process_cache',
                    }
                self._daily_cache.pop(key, None)

        self._stats['daily_cache_miss_count'] += 1
        self._stats['daily_bars_request_count'] += 1
        bars = self.client.get_domestic_daily_bars(
            normalized_symbol,
            limit=max(1, int(limit or 120)),
        )
        if not _valid_daily_bars(bars):
            return list(bars or []), {
                'daily_cache_hit': False,
                'daily_cache_miss': True,
                'daily_cache_key': key,
                'source': 'kis',
            }

        with self._daily_cache_lock:
            self._daily_cache[key] = {
                'bars': copy.deepcopy(list(bars)),
                'stored_monotonic': now_monotonic,
                'trading_date': key[-1],
            }
        return list(bars), {
            'daily_cache_hit': False,
            'daily_cache_miss': True,
            'daily_cache_key': key,
            'source': 'kis',
        }

    def get_intraday_bars(
        self,
        symbol: str,
        *,
        as_of: date | datetime | None = None,
        limit: int = 600,
        reference_current_price: float | None = None,
        previous_close: float | None = None,
        regular_open: str = '09:00',
        regular_close: str = '15:30',
        max_freshness_seconds: float = INTRADAY_MAX_FRESHNESS_SECONDS,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self._stats['intraday_request_count'] += 1
        normalized_symbol = str(symbol or '').strip().upper()
        decision = _as_kst_datetime(as_of, fallback=self._now_kst())
        bars = self.client.get_domestic_intraday_bars(
            normalized_symbol,
            as_of=as_of,
            limit=max(1, int(limit or 600)),
        )
        read_metadata = getattr(self.client, '_last_intraday_read_metadata', {})
        if not isinstance(read_metadata, dict):
            read_metadata = {}
        validation_bars, validation_metadata = validate_intraday_snapshot(
            list(bars or []),
            decision_timestamp=decision,
            reference_current_price=reference_current_price,
            previous_close=previous_close,
            regular_open=regular_open,
            regular_close=regular_close,
            max_freshness_seconds=max_freshness_seconds,
        )
        http_request_count = max(
            0,
            _safe_int(read_metadata.get('intraday_http_request_count'), 1),
        )
        page_count = max(
            0,
            _safe_int(read_metadata.get('intraday_page_count'), http_request_count),
        )
        metadata = {
            'provider': DAILY_CACHE_PROVIDER,
            'market': DAILY_CACHE_MARKET,
            'source': 'kis_domestic_minute',
            'symbol': normalized_symbol,
            'raw_timeframe_minutes': 1,
            'as_of': _as_iso(as_of) or decision.date().isoformat(),
            'http_request_count': http_request_count,
            'page_count': page_count,
            'intraday_http_request_count': http_request_count,
            'intraday_page_count': page_count,
            'requested_session_date': read_metadata.get('requested_session_date'),
            'requested_start_time': read_metadata.get('requested_start_time'),
        }
        metadata.update(validation_metadata)
        self._stats['intraday_http_request_count'] += http_request_count
        self._stats['intraday_page_count'] += page_count
        return validation_bars, metadata

    def _cache_key(self, symbol: str) -> tuple[str, str, str, str]:
        return (
            DAILY_CACHE_PROVIDER,
            DAILY_CACHE_MARKET,
            str(symbol or '').strip().upper(),
            self._now_kst().date().isoformat(),
        )

    def _now_utc(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _now_kst(self) -> datetime:
        return self._now_utc().astimezone(KST)

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        return {
            'price_request_count': 0,
            'daily_bars_request_count': 0,
            'intraday_request_count': 0,
            'intraday_http_request_count': 0,
            'intraday_page_count': 0,
            'daily_cache_hit_count': 0,
            'daily_cache_miss_count': 0,
        }


def validate_intraday_snapshot(
    bars: list[dict[str, Any]] | None,
    *,
    decision_timestamp: date | datetime | None = None,
    reference_current_price: float | None = None,
    previous_close: float | None = None,
    regular_open: str = '09:00',
    regular_close: str = '15:30',
    max_freshness_seconds: float = INTRADAY_MAX_FRESHNESS_SECONDS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    '''Validate one same-day KST regular-session intraday snapshot.'''
    decision = _as_kst_datetime(decision_timestamp)
    expected_date = decision.date()
    open_time = _parse_session_time(regular_open, date_time(9, 0))
    close_time = _parse_session_time(regular_close, date_time(15, 30))
    session_open = datetime.combine(expected_date, open_time, tzinfo=KST)
    session_close = datetime.combine(expected_date, close_time, tzinfo=KST)
    effective_cutoff = min(decision, session_close)

    raw_bars = list(bars or [])
    actual_dates: list[str] = []
    parsed_rows: list[tuple[datetime, str, dict[str, Any]]] = []
    malformed_count = 0
    for raw in raw_bars:
        if not isinstance(raw, dict):
            malformed_count += 1
            continue
        timestamp = _parse_bar_timestamp(raw.get('timestamp') or raw.get('datetime'))
        source_date = _parse_session_date(
            raw.get('session_date')
            or raw.get('source_session_date')
            or (timestamp.date().isoformat() if timestamp else None)
        )
        if source_date and source_date not in actual_dates:
            actual_dates.append(source_date)
        if timestamp is None or source_date is None:
            malformed_count += 1
            continue
        if timestamp.date().isoformat() != source_date:
            malformed_count += 1
            continue
        prices = [_finite(raw.get(key)) for key in ('open', 'high', 'low', 'close')]
        volume = _finite(raw.get('volume'), default=None)
        if (
            any(value is None or value <= 0 for value in prices)
            or volume is None
            or volume < 0
            or prices[1] < max(prices[0], prices[3])
            or prices[2] > min(prices[0], prices[3])
        ):
            malformed_count += 1
            continue
        normalized = {
            'symbol': str(raw.get('symbol') or '').strip().upper(),
            'session_date': source_date,
            'time': timestamp.strftime('%H:%M:%S'),
            'timestamp': timestamp.isoformat(),
            'open': float(prices[0]),
            'high': float(prices[1]),
            'low': float(prices[2]),
            'close': float(prices[3]),
            'volume': float(volume),
        }
        for key in ('source_session_date', 'source_time'):
            if raw.get(key) is not None:
                normalized[key] = str(raw.get(key))
        parsed_rows.append((timestamp, source_date, normalized))

    timestamps = [timestamp for timestamp, _source_date, _row in parsed_rows]
    duplicate_count = len(timestamps) - len(set(timestamps))
    ordering_violation = any(
        earlier > later for earlier, later in zip(timestamps, timestamps[1:])
    )
    reasons: list[str] = []
    if not raw_bars:
        reasons.append('empty_intraday_snapshot')
    if malformed_count:
        reasons.append('malformed_or_insane_ohlcv')
    if duplicate_count:
        reasons.append('duplicate_timestamp')
    if ordering_violation:
        reasons.append('timestamp_not_ascending')

    allowed: list[tuple[datetime, dict[str, Any]]] = []
    excluded_count = 0
    future_count = 0
    for timestamp, source_date, row in parsed_rows:
        if timestamp > effective_cutoff:
            future_count += 1
            continue
        if source_date != expected_date.isoformat():
            excluded_count += 1
            continue
        if timestamp < session_open or timestamp > session_close:
            excluded_count += 1
            continue
        allowed.append((timestamp, row))

    if not actual_dates and raw_bars:
        reasons.append('no_parseable_session_date')
    if expected_date.isoformat() not in actual_dates:
        reasons.append('session_date_mismatch')
    if not allowed:
        reasons.append('no_allowed_session_bars')

    latest_allowed_timestamp = allowed[-1][0] if allowed else None
    first_timestamp = allowed[0][0] if allowed else None
    latest_observed = (
        max(parsed_rows, key=lambda value: value[0]) if parsed_rows else None
    )
    latest_timestamp = (
        latest_allowed_timestamp
        if latest_allowed_timestamp is not None
        else (latest_observed[0] if latest_observed else None)
    )
    freshness_seconds = (
        max(0.0, (effective_cutoff - latest_allowed_timestamp).total_seconds())
        if latest_allowed_timestamp is not None
        else None
    )
    freshness_status = (
        'ok'
        if freshness_seconds is not None
        and freshness_seconds <= max(0.0, float(max_freshness_seconds))
        else 'stale'
    )
    if allowed and freshness_status != 'ok':
        reasons.append('latest_bar_stale')
    if allowed and len(allowed) < 120:
        reasons.append('insufficient_current_day_history')

    latest_close = (
        allowed[-1][1]['close']
        if allowed
        else (latest_observed[2]['close'] if latest_observed else None)
    )
    current_price = _finite(reference_current_price, default=None)
    prior_close = _finite(previous_close, default=None)
    price_gap_pct = (
        abs(current_price - latest_close) / latest_close * 100.0
        if current_price is not None and latest_close and latest_close > 0
        else None
    )
    validation_status = 'ok'
    if (
        not allowed
        or freshness_status != 'ok'
        or malformed_count
        or duplicate_count
        or ordering_violation
    ):
        validation_status = 'stale_intraday'
    elif len(allowed) < 120:
        validation_status = 'partial'

    metadata = {
        'expected_session_date': expected_date.isoformat(),
        'actual_session_dates': actual_dates,
        'session_match': bool(allowed),
        'first_bar_at': first_timestamp.isoformat() if first_timestamp else None,
        'last_bar_at': latest_timestamp.isoformat() if latest_timestamp else None,
        'latest_timestamp': latest_timestamp.isoformat() if latest_timestamp else None,
        'first_timestamp': first_timestamp.isoformat() if first_timestamp else None,
        'last_timestamp': latest_timestamp.isoformat() if latest_timestamp else None,
        'latest_bar_timestamp': latest_timestamp.isoformat() if latest_timestamp else None,
        'latest_intraday_close': latest_close,
        'reference_current_price': current_price,
        'previous_close': prior_close,
        'price_gap_pct': round(price_gap_pct, 6) if price_gap_pct is not None else None,
        'bar_count': len(allowed),
        'raw_bar_count': len(raw_bars),
        'raw_timeframe_minutes': 1,
        'decision_at': decision.isoformat(),
        'effective_cutoff_at': effective_cutoff.isoformat(),
        'regular_session_open_at': session_open.isoformat(),
        'regular_session_close_at': session_close.isoformat(),
        'freshness_seconds': round(freshness_seconds, 3) if freshness_seconds is not None else None,
        'freshness_status': freshness_status,
        'validation_status': validation_status,
        'validation_reasons': _dedupe(reasons),
        'malformed_count': malformed_count,
        'duplicate_timestamp_count': duplicate_count,
        'timestamp_ordering_valid': not ordering_violation,
        'future_bar_count': future_count,
        'excluded_bar_count': excluded_count,
        'partial_history': validation_status == 'partial',
    }
    if validation_status != 'ok' and validation_status != 'partial':
        return [], metadata
    return [row for _timestamp, row in allowed], metadata


def _valid_daily_bars(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    if not value:
        return False
    if not value:
        return False
    for bar in value:
        if not isinstance(bar, dict):
            return False
        if not str(bar.get('timestamp') or '').strip():
            return False
        try:
            prices = [float(bar[key]) for key in ('open', 'high', 'low', 'close')]
        except (KeyError, TypeError, ValueError):
            return False
        if any(price <= 0 for price in prices):
            return False
        try:
            float(bar.get('volume', 0.0) or 0.0)
        except (TypeError, ValueError):
            return False
    return True


def _as_iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _as_kst_datetime(
    value: date | datetime | None,
    *,
    fallback: datetime | None = None,
) -> datetime:
    current = value if value is not None else (fallback or datetime.now(KST))
    if isinstance(current, datetime):
        if current.tzinfo is None:
            return current.replace(tzinfo=KST)
        return current.astimezone(KST)
    return datetime.combine(current, date_time(15, 30), tzinfo=KST)


def _parse_bar_timestamp(value: Any) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = f'{text[:-1]}+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _parse_session_date(value: Any) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    digits = ''.join(character for character in text if character.isdigit())
    if len(digits) >= 8:
        text = f'{digits[:4]}-{digits[4:6]}-{digits[6:8]}'
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _parse_session_time(value: Any, default: date_time) -> date_time:
    text = str(value or '').strip()
    digits = ''.join(character for character in text if character.isdigit())
    if len(digits) == 4:
        digits += '00'
    if len(digits) >= 6:
        digits = digits[-6:]
    try:
        return date_time.fromisoformat(f'{digits[:2]}:{digits[2:4]}:{digits[4:6]}')
    except (ValueError, IndexError):
        return default


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if len(message) > 180:
        message = f'{message[:180]}...'
    return f'{exc.__class__.__name__}: {message}'
