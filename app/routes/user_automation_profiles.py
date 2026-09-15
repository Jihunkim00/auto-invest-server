from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.schemas.automation_profile import (
    AutomationProfileActionRequest,
    AutomationProfileSizingRequest,
    AutomationProfileWriteRequest,
)
from app.services.auth_dependencies import require_regular_user
from app.services.automation_profile_service import (
    AutomationProfileConflict,
    AutomationProfileNotFound,
    AutomationProfileService,
    AutomationProfileValidationError,
)
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService


router = APIRouter(
    prefix='/users/me/automation-profiles',
    tags=['user-automation-profiles'],
)


def get_user_automation_profile_service() -> AutomationProfileService:
    return AutomationProfileService()


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AutomationProfileNotFound):
        return HTTPException(status_code=404, detail={'code': 'profile_not_found'})
    if isinstance(exc, AutomationProfileConflict):
        return HTTPException(status_code=409, detail={'code': str(exc)})
    if isinstance(exc, AutomationProfileValidationError):
        return HTTPException(
            status_code=422,
            detail={'code': 'validation_failed', 'errors': exc.errors},
        )
    return HTTPException(status_code=500, detail={'code': 'profile_operation_failed'})


@router.get('')
def list_my_profiles(
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    return service.list_profiles(db, owner_user_id=int(user.id))


@router.post('', status_code=201)
def create_my_profile(
    payload: AutomationProfileWriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.create(db, payload, owner_user_id=int(user.id))
    except (AutomationProfileValidationError, AutomationProfileConflict) as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}')
def get_my_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.serialize(
            service.get_owned(db, profile_id, int(user.id)),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/watchlist-diagnostics')
def my_profile_watchlist_diagnostics(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        profile = service.serialize(service.get_owned(db, profile_id, int(user.id)))
        return AutomationProfileWatchlistService().latest(
            db,
            profile_id=int(profile['id']),
            owner_user_id=int(user.id),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc

@router.get('/{profile_id}/capital-state')
def my_profile_capital_state(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return {
            'capital_state': service.capital_state(
                db,
                profile_id,
                owner_user_id=int(user.id),
            ),
        }
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.put('/{profile_id}')
def update_my_profile(
    profile_id: str,
    payload: AutomationProfileWriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.update(
            db,
            profile_id,
            payload,
            owner_user_id=int(user.id),
        )
    except (
        AutomationProfileNotFound,
        AutomationProfileValidationError,
        AutomationProfileConflict,
    ) as exc:
        raise _service_error(exc) from exc


@router.delete('/{profile_id}')
def archive_my_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.archive(db, profile_id, owner_user_id=int(user.id))
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/validate')
def validate_my_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.validate_profile(
            db,
            profile_id,
            owner_user_id=int(user.id),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/activate')
def activate_my_profile(
    profile_id: str,
    payload: AutomationProfileActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    if not payload.confirm_operator_ack:
        raise HTTPException(status_code=409, detail={'code': 'operator_ack_required'})
    try:
        return service.activate(
            db,
            profile_id,
            owner_user_id=int(user.id),
        )
    except (
        AutomationProfileNotFound,
        AutomationProfileValidationError,
        AutomationProfileConflict,
    ) as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/pause')
def pause_my_profile(
    profile_id: str,
    payload: AutomationProfileActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    if not payload.confirm_operator_ack:
        raise HTTPException(status_code=409, detail={'code': 'operator_ack_required'})
    try:
        return service.pause(
            db,
            profile_id,
            owner_user_id=int(user.id),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/readiness')
def my_profile_readiness(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.readiness(
            db,
            profile_id,
            owner_user_id=int(user.id),
        )
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc


@router.get('/{profile_id}/watchlist')
def get_my_profile_watchlist(
    profile_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.watchlist(
            db,
            profile_id,
            owner_user_id=int(user.id),
        )
    except AutomationProfileNotFound as exc:
        raise _service_error(exc) from exc


@router.put('/{profile_id}/watchlist')
def update_my_profile_watchlist(
    profile_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        universe = payload.get('universe', payload)
        if not isinstance(universe, dict):
            raise AutomationProfileValidationError(
                [{'field': 'universe', 'message': 'must be an object'}],
            )
        return service.update_watchlist(
            db,
            profile_id,
            universe,
            owner_user_id=int(user.id),
        )
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc


@router.post('/{profile_id}/sizing-preview')
def my_profile_sizing_preview(
    profile_id: str,
    payload: AutomationProfileSizingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_regular_user),
    service: AutomationProfileService = Depends(get_user_automation_profile_service),
):
    try:
        return service.sizing(
            db,
            profile_id,
            payload.model_dump(),
            owner_user_id=int(user.id),
        )
    except (AutomationProfileNotFound, AutomationProfileValidationError) as exc:
        raise _service_error(exc) from exc
