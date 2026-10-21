from datetime import datetime, timezone

import pytest

from app.services.automation_entry_safety import snapshot_block_reason
from app.services.user_broker_account_service import _normalize_kis_snapshot
from app.services.automation_entry_safety import global_buy_block_reason, account_buy_block_reason


def test_normalized_kis_balance_without_optional_orderable_amount_is_valid():
    snapshot = _normalize_kis_snapshot({'output1': [], 'output2': [
        {'dnca_tot_amt': '600000', 'tot_evlu_amt': '600000'}]}, {'output': []})
    assert snapshot['account']['buying_power'] is None
    assert snapshot_block_reason(snapshot, now=datetime.now(timezone.utc)) is None


@pytest.mark.parametrize('value', ['bad', float('nan'), float('inf'), -1, True])
def test_supplied_invalid_money_fails_closed(value):
    snapshot = {'account': {'cash': 600000, 'equity': 600000, 'buying_power': value}}
    assert snapshot_block_reason(snapshot, now=datetime.now(timezone.utc)) == 'account_snapshot_invalid'


def test_all_missing_finances_fail_closed():
    snapshot = {'account': {'cash': None, 'buying_power': None, 'equity': None, 'currency': 'KRW'}}
    assert snapshot_block_reason(snapshot, now=datetime.now(timezone.utc)) == 'account_snapshot_unavailable'


def test_final_global_kill_read_bypasses_an_earlier_cached_orm_row(db_session):
    from sqlalchemy.orm import Session
    from app.db.models import RuntimeSetting
    row = RuntimeSetting(kill_switch=False)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert global_buy_block_reason(db_session) is None
    with Session(bind=db_session.get_bind()) as other:
        other.query(RuntimeSetting).filter_by(id=row.id).update({'kill_switch': True}, synchronize_session=False)
        other.commit()
    assert row.kill_switch is False  # The first stage still holds this stale object.
    assert global_buy_block_reason(db_session) == 'global_kill_switch_enabled'


def test_final_account_kill_read_refreshes_an_earlier_cached_orm_row(db_session):
    from sqlalchemy.orm import Session
    from app.db.models import User, UserTradingSettings
    user = User(username='fresh-kill-owner', password_hash='test-only', role='user')
    db_session.add(user)
    db_session.flush()
    row = UserTradingSettings(user_id=user.id, kill_switch=False)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert account_buy_block_reason(db_session, owner_user_id=user.id) is None
    with Session(bind=db_session.get_bind()) as other:
        other.query(UserTradingSettings).filter_by(user_id=user.id).update({'kill_switch': True}, synchronize_session=False)
        other.commit()
    assert row.kill_switch is False
    assert account_buy_block_reason(db_session, owner_user_id=user.id) == 'user_kill_switch_enabled'
