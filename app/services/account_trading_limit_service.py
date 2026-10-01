from __future__ import annotations

import json
import math
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AccountBuyExecutionClaim, OrderLog, PositionLifecycle, User, UserBrokerCredential


class AccountTradingLimitError(ValueError):
    pass


@dataclass(frozen=True)
class AccountLimitContext:
    owner_user_id: int
    broker_account_id: str
    max_total: float | None
    max_position: float | None
    legacy_admin: bool = False


def money(value: Any) -> float:
    if isinstance(value, bool):
        raise AccountTradingLimitError('account_exposure_state_unavailable')
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise AccountTradingLimitError('account_exposure_state_unavailable') from exc
    if not math.isfinite(result) or result < 0:
        raise AccountTradingLimitError('account_exposure_state_unavailable')
    return result


def minimum_buy_cap(
    *, profile_order_cap: float, available_cash: float,
    profile_pct_cap: float | None = None,
    strategy_entry_budget_krw: float | None = None,
    position_remaining: float | None = None,
    account_remaining: float | None = None,
    risk_sizing_multiplier: float = 1.0,
) -> dict[str, Any]:
    """The one cap formula; unlimited dimensions are excluded, never inflated."""
    components = [('profile_order_cap', money(profile_order_cap))]
    for source, value in (
        ('profile_pct_cap', profile_pct_cap),
        ('strategy_budget', strategy_entry_budget_krw),
        ('account_position_cap', position_remaining),
        ('account_total_exposure_cap', account_remaining),
        ('available_cash', available_cash),
    ):
        if value is not None:
            components.append((source, money(value)))
    if available_cash is None:
        raise AccountTradingLimitError('account_exposure_state_unavailable')
    base = min(value for _, value in components)
    source = next(source for source, value in components if value == base)
    multiplier = min(1.0, money(risk_sizing_multiplier))
    return {
        'profile_max_order_notional_krw': money(profile_order_cap),
        'profile_pct_cap_krw': profile_pct_cap,
        'strategy_entry_budget_krw': strategy_entry_budget_krw,
        'available_cash_krw': money(available_cash),
        'base_order_cap_krw': base,
        'risk_sizing_multiplier': multiplier,
        'effective_order_cap_krw': base * multiplier,
        'base_cap_source': source,
        'cap_source': 'risk_reduced' if multiplier < 1 else source,
    }


class AccountTradingLimitService:
    """KIS/KR policy for the canonical user-owned or legacy admin account."""

    @staticmethod
    def resolve_account(db: Session, *, owner_user_id: int | None = None,
                        provider: str = 'kis', market: str = 'KR', require_enabled: bool = True) -> AccountLimitContext:
        if provider.lower() != 'kis' or market.upper() != 'KR':
            raise AccountTradingLimitError('account_scope_mismatch')
        if owner_user_id is None:
            # NULL ownership is the existing trusted environment-backed admin
            # execution path. Never use it as fallback for a regular user.
            admins = db.query(User).filter(User.role == 'admin').populate_existing().all()
            if not admins:
                # Same bootstrap as application startup, only for the trusted
                # legacy admin path. Regular owners never enter this branch.
                from app.services.auth_service import ensure_admin_user
                bootstrap = ensure_admin_user(db)
                admins = [bootstrap] if bootstrap.role == 'admin' else []
            if len(admins) != 1:
                raise AccountTradingLimitError('account_scope_unavailable')
            user = admins[0]
            account_id = 'admin:kis:KR'
            legacy_admin = True
        else:
            user = db.query(User).filter(User.id == int(owner_user_id)).populate_existing().one_or_none()
            if user is None or user.role == 'admin':
                raise AccountTradingLimitError('account_scope_mismatch')
            credential = db.query(UserBrokerCredential).filter(
                UserBrokerCredential.user_id == user.id,
                UserBrokerCredential.provider == 'kis',
            ).populate_existing().one_or_none()
            # One canonical provider account per user (credential uniqueness).
            # Configuration exists before credentials; broker readers separately
            # require the exact owner credential and never fall back.
            account_id = f'user:{user.id}:kis:KR'
            legacy_admin = False
        if require_enabled and not user.enabled:
            raise AccountTradingLimitError('account_disabled')
        total = user.account_max_total_exposure_krw
        position = user.account_max_position_notional_krw
        return AccountLimitContext(
            owner_user_id=int(user.id), broker_account_id=account_id,
            max_total=None if total is None else money(total),
            max_position=None if position is None else money(position),
            legacy_admin=legacy_admin,
        )

    @staticmethod
    def exposure(positions: Any, *, symbol: str = '') -> dict[str, float]:
        if not isinstance(positions, list):
            raise AccountTradingLimitError('account_exposure_state_unavailable')
        values: dict[str, tuple[float, float]] = {}
        for item in positions:
            if not isinstance(item, dict):
                raise AccountTradingLimitError('account_exposure_state_unavailable')
            quantity = next((item[k] for k in ('quantity', 'qty', 'hldg_qty') if item.get(k) is not None), None)
            quantity = money(quantity)
            if quantity == 0:
                continue
            key = str(item.get('symbol') or item.get('pdno') or '').strip().upper()
            if not key:
                raise AccountTradingLimitError('account_exposure_state_unavailable')
            price = next((item[k] for k in ('current_price', 'price', 'prpr', 'stck_prpr') if item.get(k) is not None), None)
            market_value = next((item[k] for k in ('market_value', 'evaluation_amount', 'evlu_amt') if item.get(k) is not None), None)
            if price is not None and money(price) > 0:
                value = money(price) * quantity
            elif market_value is not None:
                value = money(market_value)
            else:
                # Average/cost price is not a reliable current market value.
                raise AccountTradingLimitError('account_exposure_state_unavailable')
            if value <= 0:
                raise AccountTradingLimitError('account_exposure_state_unavailable')
            if key in values and values[key] != (quantity, value):
                raise AccountTradingLimitError('account_exposure_state_unavailable')
            values[key] = (quantity, value)  # identical repeated rows count once
        return {
            'current_account_exposure_krw': sum(value for _, value in values.values()),
            'current_symbol_exposure_krw': values.get(symbol.strip().upper(), (0.0, 0.0))[1],
            'current_symbol_quantity': values.get(symbol.strip().upper(), (0.0, 0.0))[0],
        }

    def calculate(self, db: Session, *, symbol: str, positions: Any,
                  profile_order_cap: float, available_cash: float,
                  owner_user_id: int | None = None,
                  profile_pct_cap: float | None = None,
                  strategy_entry_budget_krw: float | None = None,
                  risk_sizing_multiplier: float = 1.0,
                  provider: str = 'kis', market: str = 'KR',
                  exclude_order_id: int | None = None,
                  include_pending_orders: bool = True,
                  broker_account_id: str | None = None) -> dict[str, Any]:
        account = self.resolve_account(db, owner_user_id=owner_user_id, provider=provider, market=market)
        if broker_account_id is not None and broker_account_id != account.broker_account_id:
            raise AccountTradingLimitError('account_scope_mismatch')
        exposure = self.exposure(positions, symbol=symbol)
        pending_total = pending_symbol = 0.0
        if include_pending_orders:
            # Requested/unresolved BUYs reserve capacity even when the broker
            # has not yet reflected them in its positions snapshot.
            orders = db.query(OrderLog).filter(
                OrderLog.owner_user_id == (None if account.legacy_admin else account.owner_user_id),
                OrderLog.broker == 'kis', OrderLog.market == 'KR', OrderLog.side == 'buy',
                OrderLog.internal_status.in_([
                    'REQUESTED', 'SUBMITTED', 'ACCEPTED', 'PENDING',
                    'PARTIALLY_FILLED', 'UNKNOWN_STALE', 'FILLED',
                ]),
            ).all()
            for order in orders:
                if order.id == exclude_order_id:
                    continue
                limits = None
                if order.internal_status == 'FILLED':
                    try:
                        response = json.loads(order.response_payload or '{}')
                        request = json.loads(order.request_payload or '{}')
                        limits = ((response.get('guard') or {}).get('account_trading_limits')
                                  or (request.get('sizing') or {}).get('account_trading_limits'))
                    except (TypeError, ValueError, AttributeError):
                        pass
                    if not isinstance(limits, dict) or 'current_symbol_quantity' not in limits:
                        continue
                amount = money(order.notional)
                quantity = money(order.requested_qty if order.requested_qty is not None else order.qty)
                filled = money(order.filled_qty or 0)
                if order.internal_status == 'FILLED':
                    # Filled acknowledgements can precede the broker holdings
                    # update. Reserve only the quantity not yet visible, using
                    # the baseline saved by this policy at submission.
                    closed = db.query(PositionLifecycle.id).filter(
                        PositionLifecycle.entry_order_id == order.id,
                        PositionLifecycle.status.in_(['closed', 'cancelled', 'canceled']),
                    ).first()
                    if closed:
                        continue
                    held = self.exposure(positions, symbol=str(order.symbol))['current_symbol_quantity']
                    lagging_quantity = max(0.0, money(limits['current_symbol_quantity']) + (filled or quantity) - held)
                    amount = amount * min(quantity, lagging_quantity) / quantity if quantity else 0.0
                elif filled and quantity:
                    remaining = (money(order.remaining_qty) if order.remaining_qty is not None
                                 else max(0.0, quantity - filled))
                    # Reflected fills are already included in held exposure.
                    held = self.exposure(positions, symbol=str(order.symbol))['current_symbol_quantity']
                    unseen_fills = max(0.0, filled - held)
                    amount *= min(quantity, remaining + unseen_fills) / quantity
                pending_total += amount
                if str(order.symbol).strip().upper() == symbol.strip().upper():
                    pending_symbol += amount
        total_remaining = None if account.max_total is None else max(
            0.0, account.max_total - exposure['current_account_exposure_krw'] - pending_total,
        )
        position_remaining = None if account.max_position is None else max(
            0.0, account.max_position - exposure['current_symbol_exposure_krw'] - pending_symbol,
        )
        result = {
            'owner_user_id': account.owner_user_id,
            'broker_account_id': account.broker_account_id,
            'provider': 'kis', 'market': 'KR',
            'account_max_total_exposure_krw': account.max_total,
            'account_max_position_notional_krw': account.max_position,
            'account_total_exposure_unlimited': account.max_total is None,
            'account_position_unlimited': account.max_position is None,
            **exposure,
            'pending_buy_exposure_krw': pending_total,
            'pending_symbol_buy_exposure_krw': pending_symbol,
            'remaining_account_exposure_krw': total_remaining,
            'remaining_symbol_exposure_krw': position_remaining,
            **minimum_buy_cap(
                profile_order_cap=profile_order_cap, available_cash=available_cash,
                profile_pct_cap=profile_pct_cap, strategy_entry_budget_krw=strategy_entry_budget_krw,
                position_remaining=position_remaining,
                account_remaining=total_remaining, risk_sizing_multiplier=risk_sizing_multiplier,
            ),
            'reason': None,
        }
        if total_remaining == 0:
            result['reason'] = 'account_total_exposure_limit_reached'
        elif position_remaining == 0:
            result['reason'] = 'account_position_limit_reached'
        return result

    @contextmanager
    def buy_execution_claim(self, db: Session, *, owner_user_id: int | None = None,
                            allow_disabled: bool = False):
        """Hold an account DB mutex across fresh reads, reservation and POST."""
        account = self.resolve_account(db, owner_user_id=owner_user_id, require_enabled=not allow_disabled)
        token = secrets.token_hex(24)
        try:
            # The savepoint preserves caller state when another worker owns it.
            with db.begin_nested():
                db.add(AccountBuyExecutionClaim(broker_account_id=account.broker_account_id, token=token))
                db.flush()
            db.commit()
        except IntegrityError as exc:
            raise AccountTradingLimitError('account_buy_in_progress') from exc
        try:
            yield account
        finally:
            db.query(AccountBuyExecutionClaim).filter(
                AccountBuyExecutionClaim.broker_account_id == account.broker_account_id,
                AccountBuyExecutionClaim.token == token,
            ).delete(synchronize_session=False)
            db.commit()
