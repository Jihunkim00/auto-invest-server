from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import (
    AutomationProfileWatchlistItem,
    AutomationProfileWatchlistSnapshot,
    OrderLog,
    SignalLog,
    TradeRunLog,
    User,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.scripts import run_automation_shadow_once as cli
from app.services.automation_profile_service import AutomationProfileService


NOW = datetime(2026, 9, 16, 4, 30, tzinfo=UTC)
SLOT = "13:30"


def _request(key: str) -> AutomationProfileWriteRequest:
    return AutomationProfileWriteRequest(
        profile_key=key,
        name=key,
        provider="kis",
        market="KR",
        enabled=True,
        status="active",
        capital={
            "initial_budget_krw": 1_000_000,
            "fixed_budget": 1_000_000,
            "max_order_notional_krw": 100_000,
        },
        universe={
            "watchlist_size": 5,
            "min_price_krw": 1_000,
            "max_price_krw": 20_000,
            "top_quant_candidates": 5,
            "top_ai_candidates": 5,
        },
        entry={
            "analysis_times": [SLOT],
            "no_new_entry_after": "14:00",
            "min_final_score": 65,
            "max_new_entries_per_day": 1,
            "max_entries_per_scan": 1,
        },
        operation={
            "start_date": "2026-08-01",
            "end_date": "2026-12-31",
            "weekdays_only": False,
            "timezone": "Asia/Seoul",
        },
        max_open_positions=1,
    )


def _scope(db_session):
    admin = User(
        username="admin",
        role="admin",
        enabled=True,
        setup_completed=True,
    )
    regular = User(
        username="test01",
        role="user",
        enabled=True,
        setup_completed=True,
    )
    db_session.add_all([admin, regular])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(regular)

    profiles = AutomationProfileService()
    profile = profiles.create(
        db_session,
        _request("shadow-cli-profile"),
        owner_user_id=admin.id,
    )

    raw = WatchlistSnapshotRun(
        market="KR",
        started_at=NOW,
        completed_at=NOW,
        source_count=5,
        scored_count=5,
        status="success",
    )
    db_session.add(raw)
    db_session.commit()
    symbols = [f"{100001 + index:06d}" for index in range(5)]
    db_session.add_all(
        [
            WatchlistSnapshotItem(
                run_id=raw.id,
                symbol=symbol,
                name=f"Replay {symbol}",
                market="KOSPI",
                current_price=10_000 + index * 100,
                quant_buy_score=90 - index,
                quant_sell_score=10 + index,
                indicators_json='{"volume_ratio": 1.4}',
                captured_at=NOW,
            )
            for index, symbol in enumerate(symbols)
        ]
    )
    db_session.commit()
    return admin, regular, profile, symbols


class _FakeAnalysis:
    def __init__(self, db, *, completed_count: int):
        self.db = db
        self.completed_count = completed_count
        self.request = None

    def run_once(self, db, request, *, now, execution_mode):
        self.request = request
        assert now == NOW
        assert execution_mode == "test"

        # These rows stand in for any accidental audit persistence. The CLI
        # transaction must remove them before returning.
        db.add(SignalLog(symbol="100001", action="hold", reason="shadow"))
        db.add(
            OrderLog(
                broker="kis",
                market="KR",
                symbol="100001",
                side="buy",
                order_type="market",
                qty=1,
                internal_status="DRY_RUN_SIMULATED",
            )
        )
        db.add(
            TradeRunLog(
                run_key="shadow-cli-test",
                trigger_source="automation_shadow_cli",
                symbol="100001",
                mode="automation_scheduler_profile_analysis",
                stage="done",
                result="preview_only",
            )
        )
        db.flush()

        symbols = [f"{100001 + index:06d}" for index in range(5)]
        candidates = [
            {
                "symbol": symbol,
                "name": f"Replay {symbol}",
                "runtime_quant_buy_score": 90 - index,
                "runtime_quant_sell_score": 10 + index,
                "ai_buy_score": 80 - index,
                "ai_sell_score": 20 + index,
                "confidence": 0.7,
                "gpt_analysis_status": (
                    "completed" if index < self.completed_count else "failed"
                ),
                "gpt_used": index < self.completed_count,
                "final_buy_score": 80 - index if index < self.completed_count else None,
                "final_sell_score": 20 + index if index < self.completed_count else None,
                "final_rank": index + 1 if index < self.completed_count else None,
                "final_selected": index == 0 and self.completed_count > 0,
            }
            for index, symbol in enumerate(symbols)
        ]
        completed = symbols[: self.completed_count]
        return {
            "status": "ok",
            "action": "would_buy" if completed else "hold",
            "reason": "target_aware_risk_approved" if completed else "no_candidates",
            "runtime_quant_top5_symbols": symbols,
            "gpt_target_symbols": symbols,
            "gpt_requested_count": 5,
            "gpt_completed_symbols": completed,
            "gpt_failed_symbols": symbols[self.completed_count :],
            "gpt_replacement_count": 0,
            "final_candidate_symbols": completed,
            "final_ranked_top5": candidates[: self.completed_count],
            "gpt_top5_candidates": candidates[: self.completed_count],
            "selected_final_symbol": completed[0] if completed else None,
            "selected_symbol": completed[0] if completed else None,
            "selected_symbol_name": (
                f"Replay {completed[0]}" if completed else None
            ),
            "selected_final_buy_score": 80 if completed else None,
            "final_buy_score": 80 if completed else None,
            "required_entry_score": 65,
            "target_risk_result": {
                "approved": bool(completed),
                "action": "approve" if completed else "block",
                "block_reason": None if completed else "no_candidates",
            },
            "candidates": candidates,
            "safety": {
                "broker_submit_called": False,
                "real_order_submitted": False,
            },
        }


class _FakeAnalysisFactory:
    def __init__(self, *, completed_count: int):
        self.completed_count = completed_count
        self.analysis = None
        self.client_factory = None

    def __call__(self, db, *, client_factory):
        self.client_factory = client_factory
        self.analysis = _FakeAnalysis(
            db,
            completed_count=self.completed_count,
        )
        return self.analysis


def test_no_submit_is_required(capsys, monkeypatch):
    monkeypatch.setattr(
        cli,
        "SessionLocal",
        lambda: pytest.fail("database must not open without --no-submit"),
    )

    assert (
        cli.main(
            [
                "--profile-id",
                "5",
                "--owner-user-id",
                "1",
                "--slot",
                SLOT,
            ]
        )
        == 2
    )
    assert "ERROR: --no-submit is required for shadow automation CLI" in capsys.readouterr().err


def test_owner_profile_scope_is_exact(db_session):
    admin, regular, profile, _ = _scope(db_session)
    with pytest.raises(cli.ShadowCliError, match="profile/owner mismatch"):
        cli.run_shadow_once(
            db_session,
            profile_id=profile["id"],
            owner_user_id=regular.id,
            slot=SLOT,
            now=NOW,
        )
    assert db_session.query(AutomationProfileWatchlistSnapshot).count() == 0
    assert admin.id == 1


def test_shadow_reuses_canonical_service_and_rolls_back_audits(
    db_session,
    capsys,
):
    admin, _, profile, symbols = _scope(db_session)
    factory = _FakeAnalysisFactory(completed_count=5)

    result = cli.run_shadow_once(
        db_session,
        profile_id=profile["id"],
        owner_user_id=admin.id,
        slot=SLOT,
        now=NOW,
        analysis_service_factory=factory,
    )

    assert factory.analysis is not None
    assert factory.analysis.request.save_logs is False
    assert factory.analysis.request.trigger_source == cli.CLI_TRIGGER_SOURCE
    assert result["profile_id"] == profile["id"]
    assert result["owner_user_id"] == admin.id
    assert result["snapshot"]["source_count"] == 5
    assert result["snapshot"]["eligible_count"] == 5
    assert result["snapshot"]["selected_count"] == 5
    assert result["runtime_quant_top5_symbols"] == symbols
    assert result["gpt_target_symbols"] == symbols
    assert result["gpt_completed_symbols"] == result["final_candidate_symbols"]
    assert result["broker_submit_called"] is False
    assert result["real_order_submitted"] is False
    assert result["would_submit"] is True

    assert db_session.query(AutomationProfileWatchlistSnapshot).count() == 0
    assert db_session.query(AutomationProfileWatchlistItem).count() == 0
    assert db_session.query(SignalLog).count() == 0
    assert db_session.query(OrderLog).count() == 0
    assert db_session.query(TradeRunLog).count() == 0

    cli.print_shadow_result(result)
    output = capsys.readouterr().out
    assert "runtime_top5 == gpt_targets : PASS" in output
    assert "gpt_completed == final_candidates : PASS" in output
    assert "gpt_not_run_in_final : PASS" in output
    assert "final_selected_count == 1 : PASS" in output
    assert "broker_submit_called=false" in output
    assert "real_order_submitted=false" in output


def test_incomplete_gpt_is_reported_and_excluded_from_final(db_session, capsys):
    admin, _, profile, symbols = _scope(db_session)
    factory = _FakeAnalysisFactory(completed_count=3)

    result = cli.run_shadow_once(
        db_session,
        profile_id=profile["id"],
        owner_user_id=admin.id,
        slot=SLOT,
        now=NOW,
        analysis_service_factory=factory,
    )

    assert result["gpt_completed_symbols"] == symbols[:3]
    assert result["final_candidate_symbols"] == symbols[:3]
    assert result["gpt_failed_symbols"] == symbols[3:]
    assert [item["symbol"] for item in result["final_ranked_top5"]] == symbols[:3]

    cli.print_shadow_result(result)
    output = capsys.readouterr().out
    assert "GPT FAILURE SUMMARY" in output
    assert "gpt_requested=5" in output
    assert "gpt_completed=3" in output
    assert "gpt_failed=2" in output
    assert "failed_symbols=100004,100005" in output
