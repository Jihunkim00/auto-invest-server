from datetime import UTC, datetime
import hashlib
import json
import sqlite3

import pytest

from app.db.database import SessionLocal, engine
from app.db.models import (
    AutomationProfileAiCandidateResult, TradeRunLog, User, UserAutoTradingSlotClaim,
)
from scripts.diagnose_user_auto_trading import diagnose, open_readonly, render


def test_diagnostics_reads_existing_logs_without_writes_or_trading(tmp_path):
    with SessionLocal() as db:
        user = User(username='test01', role='user', enabled=True)
        db.add(user)
        db.flush()
        uid = user.id
        db.add(UserAutoTradingSlotClaim(user_id=uid, provider='kis', market='KR', trading_date='2026-10-21',
            scheduler_slot='11:30', run_key='incident', status='completed', result='HOLD'))
        db.add(TradeRunLog(owner_user_id=uid, run_key='incident', trigger_source='user_scheduler',
            symbol='NONE', mode='user_scheduler', stage='done', result='HOLD', reason='order_status_unverified',
            request_payload=json.dumps({'scheduler_slot': '11:30'}), response_payload=json.dumps({
                'position_management': {'action': 'hold', 'held_position_count': 0, 'entry_blocked': True,
                                        'blocked_stage': 'position_management'}})))
        other = User(username='test02', role='user', enabled=True)
        db.add(other)
        db.flush()
        db.add(TradeRunLog(owner_user_id=other.id, run_key='incident', trigger_source='user_scheduler',
            symbol='NONE', mode='user_scheduler', stage='done', result='failed',
            reason='other_account_only_reason', request_payload=json.dumps({'scheduler_slot': '11:30'})))
        db.commit()
    path = engine.url.database
    before = hashlib.sha256(open(path, 'rb').read()).digest()
    with open_readonly(path) as db:
        report = diagnose(db, 'test01', '2026-10-21')
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute('DELETE FROM trade_run_logs')
    after = hashlib.sha256(open(path, 'rb').read()).digest()
    assert before == after
    slot = report['slots'][0]
    assert slot['held_positions'] == 0
    assert slot['open_sell_orders'] is None
    assert slot['a_top5'] == slot['c_analyzed'] == slot['gpt_attempted'] == slot['final_score'] == 'NOT REACHED'
    assert slot['blocked_stage'] == 'position_management'
    text = render(report)
    assert 'Final Score: NOT REACHED' in text
    assert 'Order: NOT CALLED' in text
    assert 'Open Sell Orders: UNKNOWN' in text
    assert 'other_account_only_reason' not in text
    assert len(report['slots']) == 1


def test_diagnostics_never_creates_missing_database(tmp_path):
    missing = tmp_path / 'does_not_exist.db'
    with pytest.raises(FileNotFoundError):
        with open_readonly(missing):
            pytest.fail('must not create DB')
    assert not missing.exists()


def test_calculated_zero_scores_are_preserved():
    with SessionLocal() as db:
        user = User(username='zero', role='user', enabled=True)
        db.add(user)
        db.flush()
        db.add(AutomationProfileAiCandidateResult(owner_user_id=user.id, profile_id=1, run_id=1,
            snapshot_date='2026-10-21', scheduler_slot='11:30', symbol='005930', runtime_quant_buy_score=0,
            ai_buy_score=0, final_buy_score=0, gpt_analysis_status='completed', gpt_used=True,
            diagnostics_json=json.dumps({'candidate_score_gate': {'quant_c_score': 0}})))
        db.add(UserAutoTradingSlotClaim(user_id=user.id, provider='kis', market='KR', trading_date='2026-10-21',
            scheduler_slot='11:30', run_key='zero', status='completed', result='HOLD'))
        db.commit()
    with open_readonly(engine.url.database) as db:
        slot = diagnose(db, 'zero', '2026-10-21')['slots'][0]
    assert slot['final_score'] == 0
    assert slot['c_analyzed'] == 1 and slot['c65_passed'] == 0
    assert slot['scores'][0]['A'] == slot['scores'][0]['C'] == slot['scores'][0]['GPT'] == 0
