from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db.models import MarketRegimeSnapshot, QuantABObservation, TradeRunLog
from app.services.kis_a_top5_score_gate import evaluate_a_top5_score_gate
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.kis_watchlist_preview_service import _record_preview_run, _record_quant_ab_observations
from app.services.market_regime_service import STAGES
from app.services.market_regime_trading_context import (
    MarketRegimeTradingContext, begin_market_regime_run, end_market_regime_run,
    get_market_regime_context, get_run_market_regime_context, market_regime_run,
)
from app.services.market_regime_trading_policy import (
    evaluate_shadow_candidate, get_market_regime_shadow_policy,
    market_regime_diagnostics, market_regime_observation_fields,
)


pytestmark = pytest.mark.usefixtures('fake_kis_admin_credentials')

KST = ZoneInfo("Asia/Seoul")
DECISION = datetime(2026, 10, 6, 12, tzinfo=KST)


def _snapshot(db, *, stage=4, at=None, calculation_date=None, confirmed=True, status="confirmed"):
    at = at or DECISION - timedelta(hours=4)
    row = MarketRegimeSnapshot(
        calculation_date=calculation_date or at.astimezone(KST).date(),
        calculated_at=at.astimezone(UTC), stage=stage,
        stage_key=STAGES.get(stage, (None, None))[0],
        stage_label=STAGES.get(stage, (None, None))[1],
        status=status, confirmed=confirmed, combined_score=68,
        kospi_score=66, nasdaq_score=71, score_change_3w=4.2,
        state_week_ending=date(2026, 10, 2),
        new_bullish_reversal=stage == 3, new_bearish_reversal=stage == 6,
    )
    db.add(row)
    db.commit()
    return row


def _payload(*, count=1, c_score=64, decision=DECISION):
    items = [{
        "symbol": f"{index:06d}", "current_price": 70000,
        "quant_buy_score": 72, "quant_sell_score": 10,
        "final_buy_score": 67, "ai_buy_score": 61,
        "gpt_used": True, "gpt_analysis_status": "completed",
        "shadow_c": {"reversal_score_c": c_score, "data_quality_c": 1},
    } for index in range(1, count + 1)]
    return {
        "quant_experiment": {
            "shadow_c_enabled": True, "decision_slot": decision.isoformat(),
            "c_shadow_ranked_symbols": [item["symbol"] for item in items],
        },
        "watchlist": items,
        "quant_ranked_candidates": [{"symbol": item["symbol"], "rank": index}
                                    for index, item in enumerate(items, 1)],
        "gpt_target_symbols": [item["symbol"] for item in items[:5]],
    }


def test_market_regime_context_uses_existing_snapshot_and_is_frozen(db_session):
    row = _snapshot(db_session)
    context = get_market_regime_context(db_session, DECISION)
    assert context.snapshot_id == row.id
    assert (context.stage, context.stage_key, context.combined_score) == (4, "rising", 68)
    assert (context.kospi_score, context.nasdaq_score, context.score_change_3w) == (66, 71, 4.2)
    assert context.calculated_at == row.calculated_at.replace(tzinfo=UTC)
    assert context.state_week_ending == date(2026, 10, 2)
    with pytest.raises(FrozenInstanceError):
        context.stage = 1
    row.stage, row.combined_score = 1, 20
    assert (context.stage, context.combined_score) == (4, 68)
    policy = get_market_regime_shadow_policy(context)
    assert (policy.shadow_c_min, policy.shadow_size_multiplier) == (62.5, 1.0)
    assert policy.applied_to_live_trading is False


@pytest.mark.parametrize("stage,c_min,multiplier", [
    (1, 70, .5), (2, 65, .75), (3, 65, 1),
    (4, 62.5, 1), (5, 68, .75), (6, 72, .5),
])
def test_market_regime_six_shadow_hypotheses(stage, c_min, multiplier):
    policy = get_market_regime_shadow_policy(MarketRegimeTradingContext(
        stage=stage, confirmed=True, status="confirmed",
    ))
    assert (policy.base_c_min, policy.shadow_c_min, policy.shadow_size_multiplier) == (65, c_min, multiplier)
    assert policy.version == "shadow_v1"
    assert policy.shadow_policy_active is True
    assert policy.applied_to_live_trading is False


@pytest.mark.parametrize("stage,c,base_pass,shadow_pass", [(1, 67, True, False), (4, 64, False, True)])
def test_market_regime_full_shadow_funnel_never_changes_live_gate(stage, c, base_pass, shadow_pass):
    candidate = {"quant_c_score": c, "quant_c_status": "analyzed", "gpt_used": True,
                 "gpt_analysis_status": "completed", "ai_buy_score": 61, "ai_sell_score": 10,
                 "final_buy_score": 67, "action": "buy"}
    original = copy.deepcopy(candidate)
    before = evaluate_a_top5_score_gate(candidate)
    policy = get_market_regime_shadow_policy(MarketRegimeTradingContext(
        stage=stage, status="confirmed", confirmed=True,
    ))
    diagnostics = evaluate_shadow_candidate(policy, a_rank=1, c_score=c, gpt_score=61, final_score=67,
                                            base_notional=300000)
    assert diagnostics["base_c_pass"] is base_pass
    assert diagnostics["shadow_regime_c_pass"] is shadow_pass
    assert diagnostics["base_entry_funnel_pass"] is base_pass
    assert diagnostics["shadow_regime_entry_funnel_pass"] is shadow_pass
    assert diagnostics["shadow_regime_notional"] == (150000 if stage == 1 else 300000)
    assert evaluate_a_top5_score_gate(candidate) == before
    assert candidate == original
    assert before["a_top5_score_gate_passed"] is base_pass
    assert (before["quant_c_threshold"], before["gpt_buy_score_threshold"]) == (65, 60)


@pytest.mark.parametrize("changes", [
    {"a_rank": 6}, {"gpt_score": 59.99}, {"final_score": 64.99},
    {"c_score": None}, {"gpt_score": None}, {"final_score": None},
    {"gpt_score": float("nan")}, {"final_score": True}, {"a_rank": 0},
])
def test_market_regime_shadow_keeps_rank_gpt60_final65_and_missing_scores(changes):
    policy = get_market_regime_shadow_policy(MarketRegimeTradingContext(
        stage=4, status="confirmed", confirmed=True,
    ))
    values = dict(a_rank=1, c_score=64, gpt_score=60, final_score=65)
    values.update(changes)
    result = evaluate_shadow_candidate(policy, **values)
    assert result["base_entry_funnel_pass"] is False
    assert result["shadow_regime_entry_funnel_pass"] is False
    assert result["shadow_regime_notional"] is None


@pytest.mark.parametrize("stage,status,confirmed", [
    (None, "insufficient_data", False), (4, "confirmed", False),
    (4, "pending", True), (None, "confirmed", True), (7, "confirmed", True),
])
def test_market_regime_missing_or_unconfirmed_shadow_defaults(stage, status, confirmed):
    policy = get_market_regime_shadow_policy(MarketRegimeTradingContext(
        stage=stage, status=status, confirmed=confirmed,
    ))
    assert (policy.base_c_min, policy.shadow_c_min, policy.shadow_size_multiplier) == (65, 65, 1)
    assert policy.shadow_policy_active is False
    assert policy.reason == "market_regime_not_confirmed"
    assert policy.applied_to_live_trading is False


def test_market_regime_missing_snapshot_is_nonblocking_and_persisted(db_session):
    context = get_market_regime_context(db_session, DECISION)
    assert context.stage is None and context.status == "insufficient_data" and not context.confirmed
    payload = _payload(c_score=67)
    _record_quant_ab_observations(db_session, payload=payload, gate_level=2, trigger_source="manual")
    row = db_session.query(QuantABObservation).one()
    assert row.market_regime_snapshot_id is None
    assert row.market_regime_status == "insufficient_data"
    assert (row.base_c_min, row.shadow_regime_c_min, row.shadow_regime_size_multiplier) == (65, 65, 1)
    assert row.base_entry_funnel_pass is row.shadow_regime_entry_funnel_pass is True


@pytest.mark.parametrize("decision", [DECISION, DECISION.astimezone(UTC), DECISION.replace(tzinfo=None)])
def test_market_regime_lookahead_excludes_future_snapshot(db_session, decision):
    # calculation_date is unique. Give fixture rows distinct calculation dates
    # while deliberately testing availability by actual calculated_at, not date.
    old = _snapshot(db_session, calculation_date=date(2026, 10, 5))
    future = _snapshot(db_session, stage=1, at=DECISION + timedelta(hours=3))
    context = get_market_regime_context(db_session, decision)
    assert (context.snapshot_id, context.stage) == (old.id, 4)
    assert get_market_regime_context(db_session, future.calculated_at.replace(tzinfo=UTC)).snapshot_id == future.id
    assert get_market_regime_context(db_session, DECISION - timedelta(hours=5)).snapshot_id is None
    payload = _payload(decision=decision)
    _record_quant_ab_observations(db_session, payload=payload, gate_level=2, trigger_source="test")
    row = db_session.query(QuantABObservation).one()
    assert (row.market_regime_snapshot_id, row.market_regime_stage) == (old.id, 4)


def test_market_regime_one_query_for_50_candidates_and_trade_run(db_session):
    snapshot = _snapshot(db_session)
    snapshot_id = snapshot.id
    queries = []
    def count_query(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM market_regime_snapshots" in statement:
            queries.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        payload = _payload(count=50)
        before_items = copy.deepcopy(payload["watchlist"])
        run = _record_preview_run(db_session, payload=payload, gate_level=2, trigger_source="automation_scheduler")
    finally:
        event.remove(engine, "before_cursor_execute", count_query)
    assert len(queries) == 1
    rows = db_session.query(QuantABObservation).all()
    assert len(rows) == 50
    assert {(r.market_regime_snapshot_id, r.market_regime_stage, r.market_regime_score)
            for r in rows} == {(snapshot_id, 4, 68)}
    assert payload["watchlist"] == before_items
    log = json.loads(run.response_payload)
    assert (log["market_regime"]["snapshot_id"], log["market_regime"]["stage_key"]) == (snapshot_id, "rising")
    assert log["market_regime_shadow_policy"]["applied_to_live_trading"] is False
    assert len(log["market_regime_shadow_candidates"]) == 50
    assert log["market_regime_shadow_candidates"][0]["shadow_regime_entry_funnel_pass"] is True
    assert log["market_regime_shadow_candidates"][5]["shadow_regime_entry_funnel_pass"] is False


def test_market_regime_scoped_run_freezes_updates_and_resets_after_exception(db_session):
    old = _snapshot(db_session, calculation_date=date(2026, 10, 5))
    old_id = old.id
    @market_regime_run
    def failing_run(db, *, now):
        first = get_run_market_regime_context(db, now)
        newer = _snapshot(db, stage=1, at=now - timedelta(hours=1))
        assert newer.id != first.snapshot_id
        @market_regime_run
        def nested_preview(db, *, decision_timestamp):
            return get_run_market_regime_context(db, decision_timestamp)
        assert nested_preview(db, decision_timestamp=now) is first
        _record_quant_ab_observations(db, payload=_payload(count=2), gate_level=2, trigger_source="test")
        assert {r.market_regime_snapshot_id for r in db.query(QuantABObservation)} == {old_id}
        raise RuntimeError("test scope cleanup")
    with pytest.raises(RuntimeError, match="scope cleanup"):
        failing_run(db_session, now=DECISION)
    assert get_run_market_regime_context(db_session, DECISION).stage == 1


def test_market_regime_invalid_historical_time_never_uses_current_snapshot(db_session):
    _snapshot(db_session)
    payload = _payload()
    payload["quant_experiment"]["decision_slot"] = "invalid"
    _record_quant_ab_observations(db_session, payload=payload, gate_level=2, trigger_source="test")
    assert db_session.query(QuantABObservation).one().market_regime_snapshot_id is None


def test_market_regime_duplicate_observation_is_immutable(db_session):
    _snapshot(db_session, calculation_date=date(2026, 10, 5))
    payload = _payload()
    _record_quant_ab_observations(db_session, payload=payload, gate_level=2, trigger_source="test", run_key="immutable")
    row = db_session.query(QuantABObservation).one()
    before = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    _snapshot(db_session, stage=1, at=DECISION - timedelta(hours=1))
    assert _record_quant_ab_observations(db_session, payload=_payload(c_score=99), gate_level=2,
                                        trigger_source="test", run_key="immutable") == 0
    db_session.refresh(row)
    assert {column.name: getattr(row, column.name) for column in row.__table__.columns} == before


def test_market_regime_migration_is_idempotent_and_history_remains_null(monkeypatch):
    from app.db import init_db as migration
    engine = create_engine("sqlite:///:memory:")
    QuantABObservation.__table__.create(engine)
    fields = set(market_regime_observation_fields(MarketRegimeTradingContext())) | set(
        evaluate_shadow_candidate(get_market_regime_shadow_policy(MarketRegimeTradingContext()),
                                  a_rank=None, c_score=None, gpt_score=None, final_score=None)
    )
    with engine.begin() as conn:
        for name in fields:
            conn.execute(text(f"ALTER TABLE quant_ab_observations DROP COLUMN {name}"))
        conn.execute(text("""INSERT INTO quant_ab_observations
            (observation_key, run_key, trigger_source, provider, market, symbol, authoritative_variant,
             shadow_variant, selected_by_a, selected_by_b_shadow, selected_by_c_shadow,
             gpt_selected_by_a, outcome_status, c_reversal_score)
            VALUES ('old', 'old', 'replay', 'kis', 'KR', '005930', 'A', 'B', 0, 0, 0, 0, 'pending', 64)"""))
        before = dict(conn.execute(text("SELECT * FROM quant_ab_observations")).mappings().one())
    monkeypatch.setattr(migration, "engine", engine)
    monkeypatch.setattr(migration, "SessionLocal", sessionmaker(bind=engine))
    try:
        migration.init_db()
        migration.init_db()
        columns = {c["name"]: c for c in inspect(engine).get_columns("quant_ab_observations")}
        with engine.connect() as conn:
            after = dict(conn.execute(text("SELECT * FROM quant_ab_observations")).mappings().one())
        assert {name: after[name] for name in before} == before
        for name in fields:
            assert columns[name]["nullable"] is True
            assert after[name] is None
    finally:
        engine.dispose()


def test_market_regime_diagnostics_never_include_credentials_or_redact_stage_key():
    payload = market_regime_diagnostics(MarketRegimeTradingContext(stage=4, stage_key="rising"))
    clean = sanitize_kis_payload({**payload, "appkey": "private", "appsecret": "private", "access_token": "private"})
    assert clean["market_regime"]["stage_key"] == "rising"
    assert clean["appkey"] == clean["appsecret"] == clean["access_token"] == "***"
    for name in ("account_number", "appkey", "appsecret", "access_token", "approval_key"):
        assert name not in json.dumps(payload)


@pytest.mark.parametrize("stage,c_score,expected_buy", [(1, 67, True), (4, 64, False)])
def test_market_regime_regular_user_live_selection_and_quantity_unchanged(db_session, stage, c_score, expected_buy):
    from app.tests.test_user_auto_trading_scheduler_pr129 import (
        RUN_AT, _canonical_live_harness, _final_candidate, _run_user_scheduler_slot, _set_possible_order,
    )
    _snapshot(db_session, stage=stage, at=RUN_AT - timedelta(hours=1))
    scheduler, user, profile, preview, account, analysis, broker, kis_client = _canonical_live_harness(
        db_session, candidates=[_final_candidate("005930", c_score=c_score, ai_buy_score=61, final_score=67)],
    )
    _set_possible_order(kis_client, "005930", 1)
    result = _run_user_scheduler_slot(db_session, scheduler, user)
    assert bool(kis_client.buy_calls) is expected_buy
    assert broker.buy_calls == []
    if expected_buy:
        assert len(kis_client.buy_calls) == 1
        assert kis_client.buy_calls[0] == ("005930", 1)
    logs = db_session.query(TradeRunLog).filter_by(owner_user_id=user.id).all()
    assert logs
    for log in logs:
        payload = json.loads(log.response_payload)
        assert payload["market_regime"]["stage"] == stage
        assert payload["market_regime_shadow_policy"]["applied_to_live_trading"] is False


@pytest.mark.parametrize("stage,c_score,expected_buy", [(1, 67, True), (4, 64, False)])
def test_market_regime_admin_live_selection_and_quantity_unchanged(db_session, monkeypatch, stage, c_score, expected_buy):
    from app.tests.integration.test_kis_automation_scheduler_replay import (
        UTC_NOW, build_harness, candidate, run_scheduler,
    )
    _snapshot(db_session, stage=stage, at=UTC_NOW - timedelta(hours=1))
    harness = build_harness(db_session, monkeypatch, candidates=[candidate(
        score=67, quant_c_score=c_score, ai_buy_score=61,
    )])
    harness.runtime.update_settings(db_session, {"quant_selection_mode": "A_TOP5_C_GPT"})
    result = run_scheduler(harness)
    assert bool(harness.broker.buy_calls) is expected_buy
    assert harness.client.external_kis_submit_count == 0
    if expected_buy:
        assert result["profile_buy"]["quantity"] == 1
        payload = json.loads(db_session.query(TradeRunLog).filter_by(mode="automation_profile_scheduler_buy").one().response_payload)
        assert payload["market_regime"]["stage"] == stage
        assert payload["market_regime_shadow_policy"]["shadow_size_multiplier"] == .5
        assert payload["market_regime_shadow_policy"]["applied_to_live_trading"] is False
    else:
        assert harness.validation.calls == []


def test_market_regime_production_scheduler_scope_uses_one_snapshot_through_analysis(db_session, monkeypatch):
    from app.tests.test_position_exit_retry_policy import _entry_recovery_scheduler
    scheduler, events, deferred, clock = _entry_recovery_scheduler(db_session, monkeypatch)
    old = _snapshot(db_session, stage=4, at=clock[0] - timedelta(hours=1),
                    calculation_date=clock[0].date() - timedelta(days=1))
    old_id = old.id
    def fake_analysis(db, **kwargs):
        captured = get_run_market_regime_context(db, kwargs["now"])
        assert captured.snapshot_id == old_id
        _snapshot(db, stage=1, at=clock[0] - timedelta(minutes=1))
        payload = _payload(decision=clock[0], count=2)
        run = _record_preview_run(db, payload=payload, gate_level=2, trigger_source="automation_scheduler")
        return {"action": "hold", "reason": "test_shadow_only", "trade_run_id": run.id,
                **market_regime_diagnostics(captured)}
    scheduler._run_profile_analysis = fake_analysis
    result = scheduler._run_automation_tick("09:50", clock[0])
    assert result["market_regime"]["snapshot_id"] == old_id
    assert result["market_regime_shadow_policy"]["applied_to_live_trading"] is False
    assert [item[0] for item in events] == ["position_management", "account_preflight"]
    assert deferred == []
    assert {r.market_regime_snapshot_id for r in db_session.query(QuantABObservation)} == {old_id}
    assert get_market_regime_context(db_session, clock[0]).stage == 1



def test_market_regime_run_scope_does_not_leak_into_another_worker(db_session):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    old = _snapshot(db_session, calculation_date=date(2026, 10, 5))
    old_id = old.id
    token = begin_market_regime_run(db_session, DECISION)
    try:
        _snapshot(db_session, stage=1, at=DECISION - timedelta(hours=1))
        def other_worker():
            with Session(db_session.get_bind()) as worker_db:
                return get_run_market_regime_context(worker_db, DECISION)
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(other_worker).result().stage == 1
        assert get_run_market_regime_context(db_session, DECISION).snapshot_id == old_id
    finally:
        end_market_regime_run(token)
    assert get_run_market_regime_context(db_session, DECISION).stage == 1


def test_market_regime_unmigrated_snapshot_table_is_nonblocking():
    from sqlalchemy.orm import Session
    engine = create_engine("sqlite:///:memory:")
    try:
        with Session(engine) as db:
            context = get_market_regime_context(db, DECISION)
            assert context.status == "insufficient_data" and context.snapshot_id is None
            assert db.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()



def test_market_regime_scoped_historical_observation_cannot_borrow_future_context(db_session):
    _snapshot(db_session)
    token = begin_market_regime_run(db_session, DECISION)
    try:
        historical = _payload(decision=DECISION - timedelta(days=1))
        run = _record_preview_run(db_session, payload=historical, gate_level=2, trigger_source="test")
        row = db_session.query(QuantABObservation).one()
        assert row.market_regime_snapshot_id is None
        assert json.loads(run.response_payload)["market_regime"]["snapshot_id"] is None
    finally:
        end_market_regime_run(token)



def test_market_regime_admin_skip_logs_same_decision_context_without_execution(db_session, monkeypatch):
    from app.services.runtime_setting_service import RuntimeSettingService
    from app.tests.test_position_exit_retry_policy import _canonical_scheduler_for_tick
    now = datetime(2026, 7, 30, 9, 30, tzinfo=KST)
    _snapshot(db_session, at=now - timedelta(hours=1))
    events = []
    scheduler = _canonical_scheduler_for_tick(db_session, monkeypatch, positions_loader=lambda db: [], events=events)
    RuntimeSettingService().update_settings(db_session, {"automation_profile_scheduler_enabled": False})
    scheduler._run_automation_tick("09:30", now)
    log = db_session.query(TradeRunLog).one()
    payload = json.loads(log.response_payload)
    assert payload["reason"] == "automation_disabled"
    assert payload["market_regime"]["stage"] == 4
    assert payload["market_regime_shadow_policy"]["applied_to_live_trading"] is False
    assert events == []
