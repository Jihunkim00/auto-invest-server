from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import OrderLog, SignalLog, TradeRunLog, User, UserTradingSettings
from app.routes.history import _serialize_order, _serialize_run, _serialize_signal
from app.schemas.user_data import UserTradingSettingsUpdateRequest
from app.services.auth_dependencies import require_regular_user
from app.services.user_risk_state_service import UserRiskStateService, normalize_trading_scope
from app.services.user_trading_execution_service import UserTradingExecutionService


router = APIRouter(prefix='/users/me/trading', tags=['user-trading-foundation'])


class UserTradingRunOnceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    provider: Literal['kis', 'alpaca'] = 'kis'
    symbol: str = Field(min_length=1, max_length=20)


def get_user_trading_execution_service() -> UserTradingExecutionService:
    return UserTradingExecutionService()


def _settings_payload(row: UserTradingSettings) -> dict[str, Any]:
    return {
        'id': int(row.id),
        'user_id': int(row.user_id),
        'enabled': bool(row.enabled),
        'paper_trading_enabled': bool(row.paper_trading_enabled),
        'live_trading_enabled': bool(row.live_trading_enabled),
        'trading_mode': str(row.trading_mode or 'paper'),
        'available_trading_modes': ['paper', 'live'],
        'max_daily_trades': int(row.max_daily_trades),
        'max_daily_loss_pct': float(row.max_daily_loss_pct),
        'max_position_pct': float(row.max_position_pct),
        'max_open_positions': int(row.max_open_positions),
        'same_direction_reentry_limit': int(row.same_direction_reentry_limit),
        'no_new_entry_after': row.no_new_entry_after,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _get_settings(db: Session, user: User) -> UserTradingSettings:
    row = db.query(UserTradingSettings).filter(UserTradingSettings.user_id == int(user.id)).first()
    if row is None:
        row = UserTradingSettings(user_id=int(user.id))
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _scope_or_400(provider: str, market: str) -> tuple[str, str]:
    try:
        normalized_provider, normalized_market, _currency, _tz = normalize_trading_scope(provider, market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized_provider, normalized_market


def _owned_row_or_404(
    db: Session,
    model: Any,
    row_id: int,
    user: User,
    detail: str,
) -> Any:
    row = (
        db.query(model)
        .filter(model.id == int(row_id), model.owner_user_id == int(user.id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=detail)
    return row


@router.get('/settings')
def get_my_trading_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    return _settings_payload(_get_settings(db, user))


@router.patch('/settings')
def update_my_trading_settings(
    payload: UserTradingSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    row = _get_settings(db, user)
    values = payload.values()
    selected_mode = values.pop('trading_mode', None)
    if selected_mode is not None:
        if selected_mode == 'paper':
            row.trading_mode = 'paper'
            row.enabled = True
            row.paper_trading_enabled = True
            row.live_trading_enabled = False
        elif selected_mode == 'live':
            row.trading_mode = 'live'
            row.enabled = True
            row.paper_trading_enabled = False
            # PR127 deliberately keeps this permission false. PR128 owns the
            # future live-execution unlock and its safety confirmation flow.
            row.live_trading_enabled = False
        else:
            raise HTTPException(status_code=422, detail='unsupported_trading_mode')
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _settings_payload(row)


@router.post('/run-once')
def run_my_trading_once(
    payload: UserTradingRunOnceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: UserTradingExecutionService = Depends(get_user_trading_execution_service),
):
    try:
        return service.run_once(
            db,
            user,
            provider=payload.provider,
            symbol=payload.symbol,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/risk-status')
def get_my_risk_status(
    provider: str = Query(default='kis', min_length=1, max_length=20),
    market: str = Query(default='KR', min_length=1, max_length=10),
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    normalized_provider, normalized_market = _scope_or_400(provider, market)
    return UserRiskStateService().get_user_risk_state(
        db,
        user,
        provider=normalized_provider,
        market=normalized_market,
    )


@router.get('/runs')
def list_my_trading_runs(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    query = db.query(TradeRunLog).filter(TradeRunLog.owner_user_id == int(user.id))
    if symbol:
        query = query.filter(TradeRunLog.symbol == symbol.upper())
    rows = query.order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc()).limit(limit).all()
    return {'items': [{**_serialize_run(row), 'owner_user_id': int(row.owner_user_id)} for row in rows]}


@router.get('/runs/{run_id}')
def get_my_trading_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    row = _owned_row_or_404(db, TradeRunLog, run_id, user, 'trading_run_not_found')
    return {**_serialize_run(row), 'owner_user_id': int(row.owner_user_id)}


@router.get('/signals')
def list_my_trading_signals(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    query = db.query(SignalLog).filter(SignalLog.owner_user_id == int(user.id))
    if symbol:
        query = query.filter(SignalLog.symbol == symbol.upper())
    rows = query.order_by(SignalLog.created_at.desc(), SignalLog.id.desc()).limit(limit).all()
    return {'items': [{**_serialize_signal(row, db), 'owner_user_id': int(row.owner_user_id)} for row in rows]}


@router.get('/signals/{signal_id}')
def get_my_trading_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    row = _owned_row_or_404(db, SignalLog, signal_id, user, 'trading_signal_not_found')
    return {**_serialize_signal(row, db), 'owner_user_id': int(row.owner_user_id)}


@router.get('/orders')
def list_my_trading_orders(
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    query = db.query(OrderLog).filter(OrderLog.owner_user_id == int(user.id))
    if symbol:
        query = query.filter(OrderLog.symbol == symbol.upper())
    rows = query.order_by(OrderLog.created_at.desc(), OrderLog.id.desc()).limit(limit).all()
    return {'items': [{**_serialize_order(row), 'owner_user_id': int(row.owner_user_id)} for row in rows]}


@router.get('/orders/{order_id}')
def get_my_trading_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
):
    row = _owned_row_or_404(db, OrderLog, order_id, user, 'trading_order_not_found')
    return {**_serialize_order(row), 'owner_user_id': int(row.owner_user_id)}
