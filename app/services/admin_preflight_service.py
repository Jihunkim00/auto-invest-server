"""Read-only readiness snapshot for the selected Admin KIS automation account."""

from datetime import datetime
import math
from zoneinfo import ZoneInfo

from sqlalchemy import or_

from app.db.models import (
    AccountBuyExecutionClaim,
    PositionExitRetryJob,
    PositionLifecycle,
    User,
)
from app.services.account_trading_limit_service import AccountTradingLimitService
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_execution_authority_service import AutomationExecutionAuthorityService
from app.services.kis_daily_entry_accounting import daily_entry_counts
from app.services.kis_order_account_scope import position_management_block_reason, resolve_position_account_scope
from app.services.runtime_setting_service import RuntimeSettingService

KST = ZoneInfo('Asia/Seoul')


def _normalize_env(value):
    value = str(value or '').strip().lower()
    return {'real': 'live', 'prod': 'live', 'vps': 'paper', 'demo': 'paper', 'mock': 'paper'}.get(value, value)


def _safe_broker_snapshot(client, now):
    positions, open_orders = client.read_reconciliation_account_snapshot(now=now)
    if not isinstance(positions, list) or any(not isinstance(row, dict) for row in positions):
        raise ValueError('account_snapshot_unavailable')
    if not isinstance(open_orders, list) or any(not isinstance(row, dict) for row in open_orders):
        raise ValueError('account_snapshot_unavailable')
    for row in positions:
        try:
            quantity = float(row.get('qty', row.get('quantity', row.get('hldg_qty'))))
        except (TypeError, ValueError):
            raise ValueError('account_snapshot_unavailable') from None
        if not str(row.get('symbol') or row.get('pdno') or '').strip() or not math.isfinite(quantity) or quantity <= 0:
            raise ValueError('account_snapshot_unavailable')
    for row in open_orders:
        try:
            remaining = float(row.get('unfilled_qty', row.get('remaining_quantity')))
        except (TypeError, ValueError):
            raise ValueError('account_snapshot_unavailable') from None
        if (not str(row.get('order_id') or row.get('broker_order_id') or '').strip()
                or not str(row.get('symbol') or '').strip()
                or str(row.get('side') or '').strip().lower() not in {'buy', 'sell'}
                or not math.isfinite(remaining) or remaining <= 0):
            raise ValueError('account_snapshot_unavailable')
    return positions, open_orders


def check_admin_preflight(db, *, target_date, now, kis_client, scheduler_health=None):
    """Inspect but never change local state or submit a broker order."""
    now_kst = now.astimezone(KST)
    if isinstance(target_date, str):
        target_date = datetime.fromisoformat(target_date).date()
    reasons, unknown = [], []
    admins = db.query(User).filter(User.role == 'admin', User.enabled.is_(True)).all()
    if len(admins) != 1:
        return {
            'status': 'BLOCKED', 'target_date': target_date.isoformat(),
            'reason_codes': ['admin_account_scope_unavailable'],
            'selected_profile': None, 'schedule': [], 'kis': {'authenticated': 'UNKNOWN'},
        }
    admin_id = admins[0].id
    account = AccountTradingLimitService.resolve_account(db, require_enabled=False)
    if account.owner_user_id != admin_id or not account.legacy_admin:
        reasons.append('admin_account_scope_unavailable')

    schedule = AutomationProfileService().selected_profile_schedule(db, now=now_kst)
    profile = (schedule or {}).get('profile') or {}
    if not profile:
        reasons.append('selected_profile_unavailable')
    elif (profile.get('owner_user_id') not in {None, admin_id}
            or str(profile.get('provider') or '').lower() != 'kis'
            or str(profile.get('market') or '').upper() != 'KR'):
        reasons.append('selected_profile_scope_mismatch')
    elif profile.get('enabled') is not True or profile.get('status') not in {'active', 'scheduled'}:
        reasons.append('selected_profile_inactive')

    schedule_times = []
    if isinstance(profile.get('entry'), dict):
        schedule_times = sorted(str(value) for value in profile['entry'].get('analysis_times', [])
                                if isinstance(value, str))
    if not schedule_times:
        unknown.append('schedule_unavailable')

    env = _normalize_env(getattr(getattr(kis_client, 'settings', None), 'kis_env', None))
    if env not in {'live', 'paper'}:
        unknown.append('kis_environment_unavailable')
    elif env != 'live':
        reasons.append('kis_live_environment_required')

    positions, open_orders = None, None
    auth_status = 'UNKNOWN'
    read_error = None
    read_stage = 'account_scope'
    scope = None
    try:
        scope = resolve_position_account_scope(db, client=kis_client)
        read_stage = 'complete_account_snapshot'
        positions, open_orders = _safe_broker_snapshot(kis_client, now)
        auth_status = 'authenticated_by_successful_account_reads'
    except Exception as exc:
        unknown.append('account_snapshot_unavailable')
        code = getattr(exc, 'code', str(exc))
        read_error = {'stage': read_stage, 'reason': code if code in {
            'account_scope_unavailable', 'account_scope_mismatch', 'account_disabled',
            'account_not_configured', 'broker_read_failed', 'broker_authentication_failed',
            'read_deadline_exceeded', 'call_budget_exceeded', 'invalid_response_shape',
            'invalid_continuation_response', 'response_scope_mismatch', 'live_account_required',
        } else 'broker_read_failed'}
    try:
        priority = position_management_block_reason(db, owner_user_id=None,
            scope=scope)
        if priority:
            reasons.append(priority)
    except Exception:
        unknown.append('position_management_scope_unavailable')

    if positions is None or open_orders is None:
        position_count = open_order_count = None
        position_reliability = open_order_reliability = 'UNKNOWN'
    else:
        position_count = len(positions)
        open_order_count = len(open_orders)
        position_reliability = open_order_reliability = 'RELIABLE'
        if position_count:
            reasons.append('position_state_refresh_pending')
        if open_order_count:
            reasons.append('position_state_refresh_pending')

    entry = profile.get('settings', {}).get('entry', {}) if isinstance(profile.get('settings'), dict) else {}
    try:
        max_entries = int(entry['max_new_entries_per_day'])
        if max_entries < 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        max_entries = None
        unknown.append('daily_entry_limit_unavailable')
    filled, unresolved = daily_entry_counts(db, now=now_kst.replace(
        year=target_date.year, month=target_date.month, day=target_date.day), owner_user_id=None)
    remaining = None if max_entries is None else max(0, max_entries - filled - unresolved)
    if max_entries is not None and remaining <= 0:
        reasons.append('unresolved_entry_limit_hit' if unresolved else 'daily_entry_limit_reached')

    active_retry_count = db.query(PositionExitRetryJob.id).filter(
        PositionExitRetryJob.provider == 'kis', PositionExitRetryJob.market == 'KR',
        PositionExitRetryJob.status.in_(['pending', 'running']),
        or_(PositionExitRetryJob.owner_user_id.is_(None),
            PositionExitRetryJob.owner_user_id == admin_id),
    ).count()
    if active_retry_count:
        reasons.append('position_retry_exit_unresolved')

    claim = db.get(AccountBuyExecutionClaim, account.broker_account_id)
    lifecycle_count = db.query(PositionLifecycle.id).filter(
        PositionLifecycle.status.in_(['open', 'closing']),
        or_(PositionLifecycle.owner_user_id.is_(None),
            PositionLifecycle.owner_user_id == admin_id),
    ).count()
    if lifecycle_count and 'position_state_refresh_pending' not in reasons:
        reasons.append('position_state_refresh_pending')
    if claim is not None:
        reasons.append('account_buy_in_progress')

    runtime = RuntimeSettingService().get_settings_read_only(db)
    authority = AutomationExecutionAuthorityService().snapshot(db)
    if authority.get('broker_submit_allowed') is not True:
        reasons.append('execution_authority_blocked')
    runtime_flags = {
        key: runtime.get(key) for key in (
            'bot_enabled', 'dry_run', 'kill_switch', 'scheduler_enabled',
            'automation_profile_scheduler_enabled', 'automation_mode',
            'operation_mode_requested', 'kis_live_auto_enabled',
            'kis_live_auto_buy_enabled', 'strategy_live_auto_buy_enabled',
            'strategy_live_auto_buy_scheduler_enabled',
        )
    }
    if runtime.get('kill_switch') is True:
        reasons.append('kill_switch_enabled')
    if runtime.get('automation_mode') != 'live':
        reasons.append('runtime_safety_blocked')
    if runtime.get('bot_enabled') is not True or runtime.get('dry_run') is True:
        reasons.append('runtime_safety_blocked')
    if runtime.get('automation_profile_scheduler_enabled') is not True:
        reasons.append('runtime_safety_blocked')

    health = scheduler_health if isinstance(scheduler_health, dict) else None
    health_status = (str(health.get('scheduler_health_status') or 'unknown').lower()
                     if health else 'unknown')
    if health_status == 'unknown':
        unknown.append('scheduler_health_unavailable')
    elif health_status != 'healthy':
        reasons.append('scheduler_task_timeout' if health_status in {'stalled', 'degraded'}
                       else 'scheduler_stopped')

    if target_date > now_kst.date():
        unknown.append('future_account_state_not_observed')
    elif target_date < now_kst.date():
        unknown.append('historical_account_state_not_observed')
    elif schedule_times and not any(value > now_kst.strftime('%H:%M') for value in schedule_times):
        reasons.append('no_remaining_analysis_slot')

    reason_codes = list(dict.fromkeys(reasons + unknown))
    status = 'BLOCKED' if reasons else 'UNKNOWN' if unknown else 'READY'
    return {
        'status': status,
        'target_date': target_date.isoformat(),
        'checked_at': now_kst.isoformat(),
        'selected_profile': {
            'id': profile.get('id'), 'profile_key': profile.get('profile_key'),
            'owner_user_id': profile.get('owner_user_id'), 'provider': profile.get('provider'),
            'market': profile.get('market'), 'status': profile.get('status'),
        } if profile else None,
        'schedule': schedule_times,
        'scheduler_health': {'status': health_status,
            'source': 'injected_live_scheduler_health' if health else 'unavailable_in_standalone_cli'},
        'environment': env.upper() if env else 'UNKNOWN',
        'kis': {'authentication': auth_status,
            'read_error': read_error,
            'positions_reliability': position_reliability,
            'open_orders_reliability': open_order_reliability,
            'position_count': position_count, 'open_order_count': open_order_count},
        'entry_capacity': {
            'max_entries': max_entries, 'filled_entries': filled,
            'unresolved_entries': unresolved, 'remaining_entry_capacity': remaining,
        },
        'active_exit_retries': active_retry_count,
        'account_buy_execution_claim': claim is not None,
        'runtime_safety_settings': runtime_flags,
        'execution_authority': {key: authority.get(key) for key in (
            'execution_authority', 'automation_mode', 'scheduler_allowed', 'broker_submit_allowed')},
        'profile_safety_settings': {
            'min_entry_score': (entry.get('min_final_score') if isinstance(entry, dict) else None),
            'cash_only': ((profile.get('settings', {}).get('capital') or {}).get('cash_only')
                          if isinstance(profile.get('settings'), dict) else None),
            'max_positions': profile.get('max_open_positions'),
            'no_new_entry_after': (entry.get('no_new_entry_after') if isinstance(entry, dict) else None),
        },
        'ai_score': {'status': 'not_evaluated_until_scheduled_analysis'},
        'order_execution_guaranteed': False,
        'reason_codes': reason_codes,
    }
