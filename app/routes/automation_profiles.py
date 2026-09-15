from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import get_db
from app.schemas.automation_profile import (
    AutomationProfileActionRequest,
    AutomationProfileSizingRequest,
    AutomationProfileWriteRequest,
)
from app.services.automation_profile_service import (
    AutomationProfileConflict,
    AutomationProfileNotFound,
    AutomationProfileService,
    AutomationProfileValidationError,
)
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService
from app.services.auth_dependencies import require_admin_or_uninitialized_legacy_access
from app.db.models import User
from app.services.symbol_search_service import SymbolSearchService


router = APIRouter(
    prefix='/strategy-profiles',
    tags=['strategy-profiles'],
    dependencies=[Depends(require_admin_or_uninitialized_legacy_access)],
)
symbol_router = APIRouter(prefix='/symbols', tags=['symbols'])


def get_automation_profile_service() -> AutomationProfileService:
    return AutomationProfileService()


def _admin_id(user: User | None) -> int | None:
    return int(user.id) if user is not None else None


def _get_admin_profile(service: AutomationProfileService, db: Session, profile_id: str, user: User | None):
    admin_id = _admin_id(user)
    return service.get_admin(db, profile_id, admin_id) if admin_id is not None else service.get_system(db, profile_id)


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AutomationProfileNotFound):
        return HTTPException(status_code=404, detail={'code': 'profile_not_found'})
    if isinstance(exc, AutomationProfileConflict):
        return HTTPException(status_code=409, detail={'code': str(exc)})
    if isinstance(exc, AutomationProfileValidationError):
        return HTTPException(status_code=422, detail={'code': 'validation_failed', 'errors': exc.errors})
    return HTTPException(status_code=500, detail={'code': 'profile_operation_failed'})


@router.get('')
def list_profiles(
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    return service.list_profiles(db, admin_user_id=_admin_id(user))


@router.post('', status_code=201)
def create_profile(
    payload: AutomationProfileWriteRequest,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.create(db, payload, owner_user_id=_admin_id(user))
    except (AutomationProfileValidationError, AutomationProfileConflict) as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/watchlist-diagnostics')
def profile_watchlist_diagnostics(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        profile = service.serialize(_get_admin_profile(service, db, profile_id, user))
        return AutomationProfileWatchlistService().latest(
            db,
            profile_id=int(profile['id']),
            owner_user_id=profile.get('owner_user_id'),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc

@router.get('/{profile_id}/capital-state')
def profile_capital_state(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        row = _get_admin_profile(service, db, profile_id, user)
        broker_cash = None
        if str(row.provider or '').lower() == 'kis' and str(row.market or '').upper() == 'KR':
            try:
                client = KisClient(get_settings(), KisAuthManager(get_settings(), db))
                balance = client.get_account_balance() or {}
                if isinstance(balance, dict):
                    for cash_key in ('orderable_cash', 'available_cash', 'cash'):
                        if cash_key in balance and balance.get(cash_key) is not None:
                            broker_cash = balance.get(cash_key)
                            break
            except Exception:
                broker_cash = None
        return {'capital_state': service.capital_state(db, profile_id, broker_orderable_cash_krw=broker_cash, admin_user_id=_admin_id(user))}
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc

@router.get('/{profile_id}')
def get_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.serialize(_get_admin_profile(service, db, profile_id, user))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.put('/{profile_id}')
def update_profile(
    profile_id: str,
    payload: AutomationProfileWriteRequest,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.update(db, profile_id, payload, admin_user_id=_admin_id(user))
    except (AutomationProfileNotFound, AutomationProfileValidationError, AutomationProfileConflict) as exc:
        raise _service_error(exc) from exc


@router.delete('/{profile_id}')
def archive_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.archive(db, profile_id, admin_user_id=_admin_id(user))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/validate')
def validate_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.validate_profile(db, profile_id, admin_user_id=_admin_id(user))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/activate')
def activate_profile(
    profile_id: str,
    payload: AutomationProfileActionRequest,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    if not payload.confirm_operator_ack:
        raise HTTPException(status_code=409, detail={'code': 'operator_ack_required'})
    try:
        return service.activate(db, profile_id, admin_user_id=_admin_id(user))
    except (AutomationProfileNotFound, AutomationProfileValidationError, AutomationProfileConflict) as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/pause')
def pause_profile(
    profile_id: str,
    payload: AutomationProfileActionRequest,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    if not payload.confirm_operator_ack:
        raise HTTPException(status_code=409, detail={'code': 'operator_ack_required'})
    try:
        return service.pause(db, profile_id, admin_user_id=_admin_id(user))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/readiness')
def profile_readiness(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.readiness(db, profile_id, admin_user_id=_admin_id(user))
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/watchlist')
def get_profile_watchlist(
    profile_id: str,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.watchlist(db, profile_id, admin_user_id=_admin_id(user))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.put('/{profile_id}/watchlist')
def update_profile_watchlist(
    profile_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        universe = payload.get('universe', payload)
        if not isinstance(universe, dict):
            raise AutomationProfileValidationError([{'field': 'universe', 'message': 'must be an object'}])
        return service.update_watchlist(db, profile_id, universe, admin_user_id=_admin_id(user))
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/sizing-preview')
def profile_sizing_preview(
    profile_id: str,
    payload: AutomationProfileSizingRequest,
    db: Session = Depends(get_db),
    service: AutomationProfileService = Depends(get_automation_profile_service),
    user: User | None = Depends(require_admin_or_uninitialized_legacy_access),
):
    try:
        return service.sizing(db, profile_id, payload.model_dump(), admin_user_id=_admin_id(user))
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc


@symbol_router.get('/search')
def search_symbols(
    q: str = Query('', max_length=80),
    market: str | None = Query(None, max_length=10),
    limit: int = Query(20, ge=1, le=100),
):
    return SymbolSearchService().search(q, market=market, limit=limit)
