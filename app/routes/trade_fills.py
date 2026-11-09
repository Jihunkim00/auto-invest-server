from typing import Literal
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.services.auth_dependencies import get_current_user
from app.services.trade_fill_history_service import list_trade_fills

router = APIRouter(prefix='/trading', tags=['trade-fills'])


@router.get('/fills')
def get_trade_fills(
    provider: Literal['kis', 'alpaca'] = 'kis',
    period: Literal['today', 'week', 'month', 'year'] = 'today',
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    as_of: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if as_of is not None and (as_of.tzinfo is None or as_of > datetime.now(UTC)):
        raise HTTPException(status_code=422, detail='invalid_history_boundary')
    return list_trade_fills(db, user=user, provider=provider, period=period,
                           limit=limit, offset=offset, now=as_of)
