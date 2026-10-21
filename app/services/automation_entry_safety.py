"""Shared BUY-only safety checks. Exit authorization remains independent."""
from datetime import datetime, timezone
import math

from app.services.automation_run_diagnostics import record_gate
from app.services.runtime_setting_service import RuntimeSettingService

ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS = 10.0


def global_buy_block_reason(db):
    from app.db.models import RuntimeSetting
    # A final safety check must not reuse an ORM row held by an earlier stage.
    row = db.query(RuntimeSetting.kill_switch).order_by(RuntimeSetting.id.asc()).first()
    enabled = bool(row[0]) if row else RuntimeSettingService().get_settings_read_only(db).get('kill_switch') is True
    reason = 'global_kill_switch_enabled' if enabled else None
    record_gate('GLOBAL_SAFETY', actual={'kill_switch': enabled},
                required={'kill_switch': False}, reason=reason)
    return reason


def account_buy_block_reason(db, *, owner_user_id=None):
    from app.db.models import User, UserTradingSettings
    owners = db.query(User).filter(User.role == 'admin').all() if owner_user_id is None else []
    owner = owners[0].id if len(owners) == 1 else owner_user_id
    settings = db.query(UserTradingSettings).filter_by(user_id=owner).populate_existing().first() if owner else None
    reason = 'user_kill_switch_enabled' if settings is not None and settings.kill_switch else None
    record_gate('ACCOUNT_AUTHORITY', actual={'settings_user_id': owner,
                'kill_switch': bool(settings.kill_switch) if settings is not None else False},
                required={'kill_switch': False}, reason=reason)
    return reason


def snapshot_block_reason(snapshot, *, now):
    """A timestamp supplied by a broker snapshot must be valid and fresh.

    Legacy synchronous adapters without a timestamp are checked at acquisition;
    UserBrokerAccountService always supplies fetched_at in production.
    """
    if snapshot.get('positions_reliable') is False or snapshot.get('open_orders_reliable') is False:
        return 'account_snapshot_unreliable'
    timestamp = snapshot.get('fetched_at') or snapshot.get('read_at')
    if timestamp is not None:
        try:
            checked = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
            checked = checked.replace(tzinfo=timezone.utc) if checked.tzinfo is None else checked
            age = (now - checked).total_seconds()
            if not -2 <= age <= ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS:
                return 'account_snapshot_stale'
        except (TypeError, ValueError):
            return 'account_snapshot_timestamp_invalid'
    account = snapshot.get('account') or snapshot.get('balance') or {}
    if not isinstance(account, dict) or not account:
        return 'account_snapshot_unavailable'
    money_fields = ('cash', 'buying_power', 'equity', 'portfolio_value', 'total_asset_value',
                    'ord_psbl_cash', 'tot_evlu_amt', 'orderable_cash', 'available_cash')
    if not any(account.get(key) is not None for key in money_fields):
        return 'account_snapshot_unavailable'
    for key in money_fields:
        # Balance inquiry can omit candidate-specific possible-order amounts.
        # Missing optional values are not malformed numbers; cash/risk checks
        # and the fresh possible-order preflight still decide executable size.
        if account.get(key) is not None:
            try:
                if isinstance(account[key], bool) or not math.isfinite(float(account[key])) or float(account[key]) < 0:
                    return 'account_snapshot_invalid'
            except (TypeError, ValueError):
                return 'account_snapshot_invalid'
    return None
