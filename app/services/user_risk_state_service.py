from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from numbers import Real
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, PositionLifecycle, User, UserTradingRiskState, UserTradingSettings


_KST = ZoneInfo('Asia/Seoul')
_ET = ZoneInfo('America/New_York')
_DEFAULTS: dict[str, Any] = {
    'enabled': False,
    'paper_trading_enabled': False,
    'live_trading_enabled': False,
    'kill_switch': True,
    'trading_mode': 'paper',
    'max_daily_trades': 2,
    'max_daily_loss_pct': 0.02,
    'max_position_pct': 10.0,
    'max_open_positions': 1,
    'same_direction_reentry_limit': 0,
    'no_new_entry_after': '14:00',
}
_FILLED_STATUSES = {
    InternalOrderStatus.FILLED.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
}
_PROVIDER_SCOPE = {
    'kis': ('KR', 'KRW', _KST),
    'alpaca': ('US', 'USD', _ET),
}


def normalize_trading_scope(provider: str | None, market: str | None) -> tuple[str, str, str, ZoneInfo]:
    normalized_provider = str(provider or 'kis').strip().lower()
    if normalized_provider not in _PROVIDER_SCOPE:
        raise ValueError('unsupported_trading_provider')
    default_market, currency, tz = _PROVIDER_SCOPE[normalized_provider]
    normalized_market = str(market or default_market).strip().upper()
    if normalized_market not in {'KR', 'US'}:
        raise ValueError('unsupported_trading_market')
    return normalized_provider, normalized_market, currency, tz


def trading_date_for(
    provider: str | None = None,
    market: str | None = None,
    *,
    at: datetime | None = None,
) -> date:
    _provider, _market, _currency, tz = normalize_trading_scope(provider, market)
    current = at or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    return current.astimezone(tz).date()


def _settings_values(row: UserTradingSettings | None) -> dict[str, Any]:
    if row is None:
        return dict(_DEFAULTS)
    return {
        key: getattr(row, key)
        for key in _DEFAULTS
    }


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    return float(value)


def _order_payloads(row: OrderLog) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _json_object(row.request_payload),
        _json_object(row.response_payload),
        _json_object(row.last_sync_payload),
    )


def _first_payload_value(payloads: tuple[dict[str, Any], ...], *keys: str) -> Any:
    for payload in payloads:
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
    return None


def _order_provider(row: OrderLog, payloads: tuple[dict[str, Any], ...]) -> str:
    return str(_first_payload_value(payloads, 'provider') or row.broker or '').strip().lower()


def _order_market(row: OrderLog, payloads: tuple[dict[str, Any], ...], provider: str) -> str:
    value = _first_payload_value(payloads, 'market') or row.market
    if value:
        return str(value).strip().upper()
    return 'KR' if provider == 'kis' else 'US'


def _order_currency(row: OrderLog, payloads: tuple[dict[str, Any], ...], fallback: str) -> str:
    value = _first_payload_value(payloads, 'currency') or row.currency or fallback
    return str(value).strip().upper()


def _is_simulated(row: OrderLog, payloads: tuple[dict[str, Any], ...]) -> bool:
    status = str(row.internal_status or '').upper()
    if status == InternalOrderStatus.DRY_RUN_SIMULATED.value:
        return True
    for key in ('simulated', 'preview_only', 'dry_run'):
        value = _first_payload_value(payloads, key)
        if value is True or str(value).strip().lower() in {'true', '1', 'yes'}:
            return True
    return False


def _as_local_datetime(value: datetime | None, tz: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # SQLite CURRENT_TIMESTAMP and the existing auth helpers persist
        # naive timestamps as UTC. Convert them to the market timezone only
        # after assigning that storage convention.
        return value.replace(tzinfo=timezone.utc).astimezone(tz)
    return value.astimezone(tz)


def _order_event_time(row: OrderLog, tz: ZoneInfo) -> datetime | None:
    return (
        _as_local_datetime(row.filled_at, tz)
        or _as_local_datetime(row.submitted_at, tz)
        or _as_local_datetime(row.created_at, tz)
    )


def _is_filled(row: OrderLog) -> bool:
    status = str(row.internal_status or '').upper()
    if status in _FILLED_STATUSES:
        return True
    broker_status = str(row.broker_status or row.broker_order_status or '').strip().lower()
    return broker_status in {'filled', 'partially_filled', 'partially filled'}


def _matching_user_orders(
    db: Session,
    user: User,
    provider: str,
    market: str,
    trading_date: date,
    tz: ZoneInfo,
) -> list[tuple[OrderLog, tuple[dict[str, Any], ...]]]:
    rows = (
        db.query(OrderLog)
        .filter(OrderLog.owner_user_id == int(user.id))
        .order_by(OrderLog.id.asc())
        .all()
    )
    matched: list[tuple[OrderLog, tuple[dict[str, Any], ...]]] = []
    for row in rows:
        payloads = _order_payloads(row)
        if _order_provider(row, payloads) != provider:
            continue
        if _order_market(row, payloads, provider) != market:
            continue
        event_time = _order_event_time(row, tz)
        if event_time is None or event_time.date() != trading_date:
            continue
        matched.append((row, payloads))
    return matched


def _stored_state(
    db: Session,
    user: User,
    provider: str,
    market: str,
    trading_date: date,
) -> UserTradingRiskState | None:
    return (
        db.query(UserTradingRiskState)
        .filter(
            UserTradingRiskState.user_id == int(user.id),
            UserTradingRiskState.provider == provider,
            UserTradingRiskState.market == market,
            UserTradingRiskState.trading_date == trading_date,
        )
        .first()
    )


def _explicit_realized_pl(row: OrderLog, payloads: tuple[dict[str, Any], ...]) -> float | None:
    value = row.realized_pl
    if value is None:
        value = _first_payload_value(payloads, 'realized_pl', 'realized_pnl', 'net_realized_pl')
    return _number(value)


def _explicit_loss_pct(payloads: tuple[dict[str, Any], ...]) -> float | None:
    value = _first_payload_value(payloads, 'daily_loss_pct', 'realized_pl_pct', 'realized_pnl_pct')
    return _number(value)


class UserRiskStateService:
    '''Read-only user risk foundation; it never submits, cancels, or closes orders.'''

    def get_daily_trade_count(
        self,
        db: Session,
        user: User,
        *,
        provider: str = 'kis',
        market: str = 'KR',
        as_of: datetime | None = None,
    ) -> int:
        normalized_provider, normalized_market, _currency, tz = normalize_trading_scope(provider, market)
        trading_date = trading_date_for(normalized_provider, normalized_market, at=as_of)
        rows = _matching_user_orders(db, user, normalized_provider, normalized_market, trading_date, tz)
        count = sum(
            1
            for row, payloads in rows
            if _is_filled(row) and not _is_simulated(row, payloads)
        )
        if count == 0:
            stored = _stored_state(db, user, normalized_provider, normalized_market, trading_date)
            if stored is not None:
                return max(0, int(stored.daily_trade_count or 0))
        return count

    def get_daily_realized_pl_details(
        self,
        db: Session,
        user: User,
        *,
        provider: str = 'kis',
        market: str = 'KR',
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_provider, normalized_market, currency, tz = normalize_trading_scope(provider, market)
        trading_date = trading_date_for(normalized_provider, normalized_market, at=as_of)
        rows = _matching_user_orders(db, user, normalized_provider, normalized_market, trading_date, tz)
        realized_pl = 0.0
        explicit_count = 0
        loss_pct: float | None = None
        for row, payloads in rows:
            if not _is_filled(row) or _is_simulated(row, payloads):
                continue
            if _order_currency(row, payloads, currency) != currency:
                continue
            value = _explicit_realized_pl(row, payloads)
            if value is not None:
                realized_pl += value
                explicit_count += 1
            candidate_loss_pct = _explicit_loss_pct(payloads)
            if candidate_loss_pct is not None:
                loss_pct = candidate_loss_pct
        stored = _stored_state(db, user, normalized_provider, normalized_market, trading_date)
        if stored is not None:
            if explicit_count == 0:
                realized_pl = float(stored.daily_realized_pl or 0)
            if loss_pct is None:
                loss_pct = _number(stored.daily_loss_pct)
            if stored.currency:
                currency = str(stored.currency).strip().upper()
        return {
            'daily_realized_pl': realized_pl,
            'daily_loss_pct': loss_pct,
            'currency': currency,
            'data_available': explicit_count > 0 or stored is not None,
        }

    def get_daily_realized_pl(
        self,
        db: Session,
        user: User,
        *,
        provider: str = 'kis',
        market: str = 'KR',
        as_of: datetime | None = None,
    ) -> float:
        return float(self.get_daily_realized_pl_details(
            db, user, provider=provider, market=market, as_of=as_of,
        )['daily_realized_pl'])

    def get_open_position_count(
        self,
        db: Session,
        user: User,
        *,
        provider: str = 'kis',
        market: str = 'KR',
    ) -> int:
        normalized_provider, normalized_market, _currency, _tz = normalize_trading_scope(provider, market)
        rows = (
            db.query(PositionLifecycle)
            .filter(PositionLifecycle.owner_user_id == int(user.id))
            .all()
        )
        count = 0
        for row in rows:
            if str(row.status or '').strip().lower() not in {'open', 'active', 'managed'}:
                continue
            linked = db.get(OrderLog, row.entry_order_id) if row.entry_order_id else None
            if linked is None:
                count += 1
                continue
            payloads = _order_payloads(linked)
            if (
                _order_provider(linked, payloads) == normalized_provider
                and _order_market(linked, payloads, normalized_provider) == normalized_market
            ):
                count += 1
        return count

    def get_user_risk_state(
        self,
        db: Session,
        user: User,
        *,
        provider: str = 'kis',
        market: str = 'KR',
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_provider, normalized_market, currency, _tz = normalize_trading_scope(provider, market)
        trading_date = trading_date_for(normalized_provider, normalized_market, at=as_of)
        row = db.query(UserTradingSettings).filter(UserTradingSettings.user_id == int(user.id)).first()
        settings = _settings_values(row)
        daily_trade_count = self.get_daily_trade_count(
            db, user, provider=normalized_provider, market=normalized_market, as_of=as_of,
        )
        pnl = self.get_daily_realized_pl_details(
            db, user, provider=normalized_provider, market=normalized_market, as_of=as_of,
        )
        open_positions = self.get_open_position_count(
            db, user, provider=normalized_provider, market=normalized_market,
        )
        max_daily_trades = max(0, int(settings['max_daily_trades'] or 0))
        max_open_positions = max(0, int(settings['max_open_positions'] or 0))
        max_daily_loss_pct = abs(float(settings['max_daily_loss_pct'] or 0))
        daily_loss_pct = pnl['daily_loss_pct']
        daily_loss_limit_hit = (
            daily_loss_pct is not None
            and max_daily_loss_pct > 0
            and float(daily_loss_pct) <= -max_daily_loss_pct
        )
        risk_flags: list[str] = []
        if not settings['enabled']:
            risk_flags.append('user_trading_disabled')
        elif str(settings['trading_mode'] or 'paper').strip().lower() == 'live':
            if not settings['live_trading_enabled']:
                risk_flags.append('live_trading_disabled')
        elif not settings['paper_trading_enabled']:
            risk_flags.append('paper_trading_disabled')
        if daily_trade_count >= max_daily_trades:
            risk_flags.append('max_daily_trades_reached')
        if daily_loss_limit_hit:
            risk_flags.append('daily_loss_limit_reached')
        if open_positions >= max_open_positions:
            risk_flags.append('max_open_positions_reached')
        return {
            'owner_user_id': int(user.id),
            'provider': normalized_provider,
            'market': normalized_market,
            'currency': pnl['currency'] or currency,
            'trading_date': trading_date.isoformat(),
            'trading_enabled': bool(settings['enabled']),
            'paper_trading_enabled': bool(settings['paper_trading_enabled']),
            'live_trading_enabled': bool(settings['live_trading_enabled']),
            'kill_switch': bool(settings['kill_switch']),
            'trading_mode': str(settings['trading_mode'] or 'paper'),
            'daily_trade_count': daily_trade_count,
            'max_daily_trades': max_daily_trades,
            'daily_realized_pl': float(pnl['daily_realized_pl']),
            'daily_loss_pct': daily_loss_pct,
            'max_daily_loss_pct': max_daily_loss_pct,
            'daily_loss_limit_hit': daily_loss_limit_hit,
            'open_position_count': open_positions,
            'max_open_positions': max_open_positions,
            'max_position_pct': float(settings['max_position_pct'] or 0),
            'same_direction_reentry_limit': int(settings['same_direction_reentry_limit'] or 0),
            'no_new_entry_after': settings['no_new_entry_after'],
            'position_limit_hit': open_positions >= max_open_positions,
            'risk_allowed': not risk_flags,
            'risk_flags': risk_flags,
        }

    def evaluate_user_risk_limits(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.get_user_risk_state(*args, **kwargs)
