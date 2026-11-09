from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.routes.user_brokers import get_user_broker_account_service
from app.services.auth_dependencies import require_admin, require_regular_user
from app.services.kis_account_execution_history_service import KisAccountExecutionHistoryService
from app.services.user_broker_account_service import UserBrokerAccountService

router = APIRouter(tags=['kis-account-executions'])
Period = Literal['day', 'week', 'month', 'year']


def get_execution_history_service(
    account_service: UserBrokerAccountService = Depends(get_user_broker_account_service),
):
    return KisAccountExecutionHistoryService(account_service=account_service)


def _read(response, service, db, user, period, limit, offset, as_of):
    response.headers['Cache-Control'] = 'no-store, private'
    if as_of is not None and (as_of.tzinfo is None or as_of > datetime.now(UTC)):
        raise HTTPException(status_code=422, detail='invalid_history_boundary')
    return service.read(db, user, period=period, limit=limit, offset=offset, as_of=as_of)


@router.get('/kis/account/executions')
def admin_account_executions(
    response: Response, period: Period = 'day',
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    as_of: datetime | None = None, db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    service: KisAccountExecutionHistoryService = Depends(get_execution_history_service),
):
    return _read(response, service, db, user, period, limit, offset, as_of)


@router.get('/users/me/trading/executions')
def user_account_executions(
    response: Response, period: Period = 'day',
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    as_of: datetime | None = None, db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: KisAccountExecutionHistoryService = Depends(get_execution_history_service),
):
    return _read(response, service, db, user, period, limit, offset, as_of)
