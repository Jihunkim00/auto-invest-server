from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import app.services.kis_watchlist_preview_service as kis_preview_module
import app.scripts.run_automation_shadow_once as shadow_cli
from app.db.models import (
    AutomationProfileAiCandidateResult,
    AutomationProfileWatchlistSnapshot,
    User,
    UserTradingSettings,
    WatchlistSnapshotItem,
    WatchlistSnapshotRun,
)
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.automation_profile_watchlist_service import AutomationProfileWatchlistService
from app.services.scheduler_service import SchedulerService
from app.services.automation_scheduler_service import AutomationSchedulerService
import app.services.automation_scheduler_service as automation_scheduler_module
from app.services.kis_watchlist_preview_service import KisGptPreview, KisWatchlistPreviewService
from app.services.profile_aware_dry_run_auto_buy_service import ProfileAwareDryRunAutoBuyService
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_profile_service import StrategyProfileService
from app.services.user_auto_trading_scheduler_service import UserAutoTradingCandidateService, UserAutoTradingSchedulerService
from app.services.user_trading_execution_service import UserTradingExecutionService

NOW = datetime(2026, 9, 16, 4, 30, tzinfo=UTC)
SLOT = "13:30"


class HardBlockedKisClient:
    def __init__(self, prices):
        self.prices = prices
        self.submit_calls = 0

    def list_positions(self):
        return []

    def list_open_orders(self):
        return []

    def get_account_balance(self):
        return {"cash": 1_000_000.0, "orderable_cash": 1_000_000.0, "total_asset_value": 1_000_000.0}

    def get_domestic_stock_price(self, symbol):
        return {"symbol": symbol, "name": f"Replay {symbol}", "current_price": self.prices[symbol]}

    def _blocked(self, **_kwargs):
        self.submit_calls += 1
        raise AssertionError("shadow replay must never submit a KIS order")

    submit_market_buy = _blocked
    submit_market_buy_qty = _blocked
    submit_market_sell = _blocked
    submit_market_sell_qty = _blocked


class ProfileMarket:
    def get_profile(self, _market):
        return SimpleNamespace(currency="KRW", timezone="Asia/Seoul")

    def load_watchlist(self, _market):
        return {"watchlist_file": "shadow-replay", "symbols": []}

    def load_reference_sites(self, _market):
        return {"reference_sites_file": "shadow-replay", "sources": []}

    @staticmethod
    def normalize_symbol(value, _market):
        return str(value or "").strip().upper()


class OpenMarket:
    def get_session_status(self, market, *, now=None):
        return {
            "market": market,
            "timezone": "Asia/Seoul",
            "is_market_open": True,
            "is_entry_allowed_now": True,
            "is_near_close": False,
            "date": (now or NOW).date().isoformat(),
            "regular_open": "09:00",
            "regular_close": "15:30",
            "effective_close": "15:30",
        }


class Snapshots:
    def __init__(self, prices):
        self.prices = prices

    def reset_run_stats(self):
        return None

    def snapshot(self, symbol, *, daily_limit=120):
        price = self.prices[symbol]
        return {
            "quote": {"symbol": symbol, "name": f"Replay {symbol}", "current_price": price, "previous_close": price - 10},
            "daily_bars": [], "quote_error": None, "daily_error": None,
            "captured_at": NOW.isoformat(), "daily_bars_source": "deterministic_replay",
        }

    def stats(self):
        return {key: 0 for key in (
            "price_request_count", "daily_bars_request_count", "intraday_request_count",
            "intraday_http_request_count", "intraday_page_count",
            "daily_cache_hit_count", "daily_cache_miss_count",
        )}


class Indicators:
    def calculate(self, _bars, *, current_price=None):
        price = float(current_price or 0)
        return {
            "indicator_status": "ok",
            "indicator_payload": {
                "price": price, "ema20": price, "ema50": price, "rsi": 55.0,
                "vwap": price, "atr": 100.0, "volume_ratio": 1.4,
                "short_momentum": 0.02, "day_open": price - 50,
                "previous_high": price + 100, "previous_low": price - 100,
            },
            "bar_count": 120,
        }


class Quant:
    def score(self, indicators, *, gate_level=None):
        index = int(round((float(indicators["price"]) - 10_000.0) / 100.0))
        return {
            "quant_buy_score": 90.0 - index,
            "quant_sell_score": 10.0 + index,
            "quant_reason": "deterministic runtime quant replay",
            "quant_notes": [],
        }


class Gpt:
    def analyze(self, *, symbol, **_kwargs):
        index = int(symbol) - 100001
        return KisGptPreview(
            gpt_used=True,
            action_hint="watch",
            gpt_reason=f"deterministic GPT advisory for {symbol}",
            warnings=[],
            ai_buy_score=75.0 - index * 0.5,
            ai_sell_score=20.0 + index * 0.5,
            confidence=0.60,
            gpt_analysis_status="completed",
        )


class Context:
    def snapshot(self, *, db=None, symbols=None, quote_snapshots=None):
        return {"as_of": NOW.isoformat(), "warnings": []}

    def summary(self, _context):
        return {"status": "deterministic_replay"}

    def get_disclosures(self, *_args, **_kwargs):
        return {"available": False, "items": [], "warnings": []}


class EventRisk:
    def get_event_risk(self, _db, *, symbol, market, as_of_date, intent):
        return {"symbol": symbol, "market": market, "has_near_event": False,
                "entry_blocked": False, "position_size_multiplier": 1.0, "warnings": []}


class ApprovedRisk:
    def evaluate_entry(self, _db, _payload, *, profile_name):
        return {"approved": True, "approved_notional_krw": 100_000.0,
                "recommended_notional_krw": 100_000.0, "sizing_multiplier": 1.0,
                "profile_thresholds": {"max_order_notional_pct": 10.0},
                "risk_flags": [], "gating_notes": []}


class ProfileBuy:
    def __init__(self, client):
        self.client = client
        self.positions_loader = lambda _db: []


class UserAccount:
    def get_broker_snapshot(self, _db, _user, provider):
        return {"provider": provider, "market": "KR", "environment": "paper", "connected": True,
                "account": {"currency": "KRW", "portfolio_value": 1_000_000.0,
                            "equity": 1_000_000.0, "buying_power": 1_000_000.0, "cash": 1_000_000.0},
                "positions": [], "open_orders": []}


def request(key, *, max_price, min_price=1.0, status="active"):
    return AutomationProfileWriteRequest(
        profile_key=key, name=key, provider="kis", market="KR", enabled=True, status=status,
        capital={"initial_budget_krw": 1_000_000.0, "fixed_budget": 1_000_000.0,
                 "max_order_notional_krw": 100_000.0},
        universe={"watchlist_size": 50, "min_price_krw": min_price, "max_price_krw": max_price,
                  "top_quant_candidates": 50, "top_ai_candidates": 5},
        entry={"analysis_times": [SLOT], "no_new_entry_after": "14:00",
               "min_final_score": 65.0, "max_new_entries_per_day": 1, "max_entries_per_scan": 1},
        operation={"start_date": "2026-08-01", "end_date": "2026-12-31",
                   "weekdays_only": False, "timezone": "Asia/Seoul"},
        max_open_positions=1,
    )


def seed(db):
    admin = User(username="admin", role="admin", enabled=True, setup_completed=True)
    regular = User(username="test01", role="user", enabled=True, setup_completed=True)
    db.add_all([admin, regular])
    db.commit()
    db.refresh(admin)
    db.refresh(regular)
    profiles = AutomationProfileService()
    for index in range(4):
        profiles.create(db, request(f"dummy-before-{index}", max_price=100_000, status="disabled"))
    admin_profile = profiles.create(db, request("admin-shadow", max_price=100_000), owner_user_id=admin.id)
    for index in range(2):
        profiles.create(db, request(f"dummy-middle-{index}", max_price=100_000, status="disabled"))
    regular_profile = profiles.create(db, request("test01-shadow", max_price=14_900, min_price=12_000),
                                      owner_user_id=regular.id)
    assert (admin.id, regular.id, admin_profile["id"], regular_profile["id"]) == (1, 2, 5, 8)
    profiles.activate(db, str(admin_profile["id"]), admin_user_id=admin.id)
    profiles.activate(db, str(regular_profile["id"]), owner_user_id=regular.id)
    db.add(UserTradingSettings(
        user_id=regular.id, enabled=True, paper_trading_enabled=True, trading_mode="paper",
        auto_trading_enabled=True, auto_trading_provider="kis", kill_switch=True,
        max_daily_trades=2, max_daily_loss_pct=0.02, max_position_pct=10.0,
        max_open_positions=1, same_direction_reentry_limit=0, no_new_entry_after="14:00",
    ))
    db.commit()
    prices = {f"{100001 + index:06d}": 10_000.0 + index * 100.0 for index in range(50)}
    raw = WatchlistSnapshotRun(market="KR", started_at=NOW, completed_at=NOW,
                               source_count=50, scored_count=50, status="success")
    db.add(raw)
    db.commit()
    db.add_all([
        WatchlistSnapshotItem(
            run_id=raw.id, symbol=symbol, name=f"Replay {symbol}", market="KOSPI",
            current_price=price, quant_buy_score=90.0 - index, quant_sell_score=10.0 + index,
            indicators_json='{"volume_ratio": 1.4}', captured_at=NOW,
        )
        for index, (symbol, price) in enumerate(prices.items())
    ])
    db.commit()
    return admin, regular, admin_profile, regular_profile, prices


def make_preview(prices):
    return KisWatchlistPreviewService(
        HardBlockedKisClient(prices), profile_service=ProfileMarket(), session_service=OpenMarket(),
        gpt_advisor=Gpt(), indicator_service=Indicators(), quant_signal_service=Quant(),
        event_risk_service=EventRisk(), market_context_service=Context(),
        market_data_snapshot_service=Snapshots(prices), gpt_candidate_limit=5,
    )


def test_pr129_admin_and_test01_shadow_replay(db_session, monkeypatch):
    monkeypatch.setattr(kis_preview_module, "get_settings",
                        lambda: SimpleNamespace(kis_enabled=False, watchlist_min_entry_score=65,
                                                watchlist_min_score_gap=0, openai_api_key=None))
    admin, regular, admin_profile, regular_profile, prices = seed(db_session)
    runtime = RuntimeSettingService()
    runtime.update_settings(db_session, {"automation_mode": "test", "dry_run": True,
                                         "automation_profile_scheduler_enabled": True,
                                         "per_slot_new_entry_limit": 1, "max_open_positions": 3})
    preview = make_preview(prices)
    profile_watchlists = AutomationProfileWatchlistService()
    profile_aware = ProfileAwareDryRunAutoBuyService(
        preview_service=preview, strategy_profiles=StrategyProfileService(),
        target_risk_service=ApprovedRisk(), market_sessions=OpenMarket(),
        profile_watchlists=profile_watchlists,
    )
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = runtime
    scheduler.automation_profiles = AutomationProfileService(runtime_settings=runtime)
    scheduler.profile_aware_dry_run_auto_buy_service = profile_aware
    scheduler.automation_profile_buy_scheduler_service = ProfileBuy(preview.client)
    monkeypatch.setattr(automation_scheduler_module, "SessionLocal", lambda: db_session)
    admin_result = scheduler.run_once(slot=SLOT, now=NOW)
    admin_dry = admin_result["dry_run"]["dry_run_result"]
    assert admin_result["scheduler"] == "AutomationSchedulerService"
    assert admin_result["profile_key"] == "admin-shadow"
    assert (admin_dry["profile_id"], admin_dry["owner_user_id"]) == (5, 1)
    snap = db_session.query(AutomationProfileWatchlistSnapshot).filter_by(profile_id=5, owner_user_id=1).one()
    assert admin_dry["runtime_quant_candidate_count"] == 50, {"preview_status": admin_dry.get("preview_status"), "preview_error": admin_dry.get("preview_error"), "snapshot_id": admin_dry.get("snapshot_id"), "profile_snapshot": admin_dry.get("profile_snapshot"), "configured": admin_dry.get("configured_symbol_count"), "analyzed": admin_dry.get("analyzed_symbol_count"), "snapshot_row": {"source": snap.source_count, "eligible": snap.eligible_count, "selected": snap.selected_count, "budget": snap.effective_entry_budget_krw, "max_price": snap.effective_max_candidate_price}}
    assert admin_dry["runtime_quant_top5_symbols"] == admin_dry["gpt_target_symbols"]
    assert len(admin_dry["gpt_target_symbols"]) == 5
    assert len(admin_dry["gpt_completed_symbols"]) == 5
    assert admin_dry["gpt_failed_symbols"] == []
    assert admin_dry["final_candidate_symbols"] == admin_dry["gpt_completed_symbols"]
    assert len(admin_dry["final_ranked_top5"]) == 5
    assert sum(bool(item["final_selected"]) for item in admin_dry["final_ranked_top5"]) == 1
    assert all(item["gpt_used"] and item["gpt_analysis_status"] == "completed"
               for item in admin_dry["final_ranked_top5"])
    assert admin_result["profile_buy"]["broker_submit_called"] is False
    assert admin_result["profile_buy"]["real_external_kis_submit_count"] == 0

    user_session = OpenMarket()
    user_account = UserAccount()
    user_execution = UserTradingExecutionService(
        account_service=user_account,
        analysis_service=SimpleNamespace(kis_preview_service=preview),
        session_service=user_session,
        now_provider=lambda: NOW,
    )
    user_scheduler = UserAutoTradingSchedulerService(
        execution_service=user_execution, account_service=user_account, session_service=user_session,
        automation_profiles=AutomationProfileService(runtime_settings=runtime),
        candidate_service=UserAutoTradingCandidateService(
            profile_watchlists=profile_watchlists, runtime_preview_service=preview),
        now_provider=lambda: NOW,
    )
    user_result = user_scheduler.run_provider_once(db_session, provider="kis", scheduler_slot=SLOT, now=NOW)
    user_item = next(item for item in user_result["items"] if item.get("owner_user_id") == 2)
    pipeline = user_item["pipeline_diagnostics"]
    assert user_item["result"] == "simulated"
    assert (pipeline["profile_id"], pipeline["owner_user_id"]) == (8, 2)
    assert (pipeline["selected_count"], pipeline["runtime_quant_candidate_count"]) == (30, 30)
    assert pipeline["runtime_quant_top5_symbols"] == pipeline["gpt_target_symbols"]
    assert pipeline["final_candidate_symbols"] == pipeline["gpt_completed_symbols"]
    assert len(pipeline["final_ranked_top5"]) == 5
    assert user_item["real_order_submitted"] is False
    assert user_item["broker_submit_called"] is False
    assert preview.client.submit_calls == 0

    snapshots = db_session.query(AutomationProfileWatchlistSnapshot).all()
    assert {(row.profile_id, row.owner_user_id, row.selected_count) for row in snapshots} == {(5, 1, 50), (8, 2, 30)}
    audit = db_session.query(AutomationProfileAiCandidateResult).all()
    assert {row.profile_id for row in audit} == {5, 8}
    assert {row.owner_user_id for row in audit} == {1, 2}
    assert sum(bool(row.final_selected) for row in audit) == 2
    assert all(row.gpt_used and row.gpt_analysis_status == "completed"
               for row in audit if row.final_rank is not None)

    print(json.dumps({
        "ADMIN": {"profile_id": 5, "owner_user_id": 1, "source_count": 50, "eligible_count": 50,
                  "selected_count": 50, "runtime_quant_count": 50,
                  "runtime_quant_top5": admin_dry["runtime_quant_top5_symbols"],
                  "gpt_top5": admin_dry["gpt_target_symbols"],
                  "gpt_completed": 5, "gpt_failed": 0,
                  "final_top5": admin_dry["final_candidate_symbols"],
                  "final_selected": admin_dry["selected_final_symbol"],
                  "action": admin_dry["action"], "reason": admin_dry["reason"]},
        "TEST01": {"profile_id": 8, "owner_user_id": 2, "source_count": 50, "eligible_count": 30,
                   "selected_count": 30, "runtime_quant_count": 30,
                   "runtime_quant_top5": pipeline["runtime_quant_top5_symbols"],
                   "gpt_top5": pipeline["gpt_target_symbols"],
                   "gpt_completed": 5, "gpt_failed": 0,
                   "final_top5": [item["symbol"] for item in pipeline["final_ranked_top5"]],
                   "final_selected": pipeline["selected_final_symbol"],
                   "action": user_item["result"], "reason": user_item["reason"]},
        "ASSERTIONS": {"runtime_top5_equals_gpt_targets": True,
                       "gpt_completed_equals_final": True,
                       "gpt_not_run_in_final": True,
                       "final_selected_one_per_scope": True,
                       "broker_submit_called": False, "real_order_submitted": False},
    }, ensure_ascii=False))


def test_pr129_shadow_cli_profile_lineage_and_final_invariants(db_session, monkeypatch):
    monkeypatch.setattr(
        kis_preview_module,
        "get_settings",
        lambda: SimpleNamespace(
            kis_enabled=False,
            watchlist_min_entry_score=65,
            watchlist_min_score_gap=0,
            openai_api_key=None,
        ),
    )
    admin, regular, admin_profile, regular_profile, prices = seed(db_session)
    runtime = RuntimeSettingService()
    runtime.update_settings(
        db_session,
        {
            "automation_mode": "test",
            "dry_run": True,
            "automation_profile_scheduler_enabled": True,
            "per_slot_new_entry_limit": 1,
            "max_open_positions": 3,
        },
    )
    preview = make_preview(prices)
    profile_aware = ProfileAwareDryRunAutoBuyService(
        preview_service=preview,
        strategy_profiles=StrategyProfileService(),
        target_risk_service=ApprovedRisk(),
        market_sessions=OpenMarket(),
        profile_watchlists=AutomationProfileWatchlistService(),
    )

    def factory(_db, *, client_factory):
        del client_factory
        return profile_aware

    admin_result = shadow_cli.run_shadow_once(
        db_session,
        profile_id=admin_profile["id"],
        owner_user_id=admin.id,
        slot=SLOT,
        now=NOW,
        analysis_service_factory=factory,
    )
    user_result = shadow_cli.run_shadow_once(
        db_session,
        profile_id=regular_profile["id"],
        owner_user_id=regular.id,
        slot=SLOT,
        now=NOW,
        analysis_service_factory=factory,
    )

    admin_snapshot_symbols = {
        shadow_cli.normalize_symbol_identity(item["symbol"])
        for item in admin_result["snapshot_items"]
    }
    user_snapshot_symbols = {
        shadow_cli.normalize_symbol_identity(item["symbol"])
        for item in user_result["snapshot_items"]
    }
    assert admin_result["snapshot"]["source_run_id"] == user_result["snapshot"]["source_run_id"]
    assert admin_snapshot_symbols != user_snapshot_symbols

    for result in (admin_result, user_result):
        snapshot_symbols = set(result["profile_snapshot_selected_symbols"])
        runtime_input_symbols = set(result["runtime_input_symbols"])
        assert snapshot_symbols == runtime_input_symbols
        assert result["runtime_quant_candidate_count"] <= len(snapshot_symbols)
        assert result["unaffordable_runtime_candidates"] == []
        assert result["runtime_quant_top5_symbols"] == result["gpt_target_symbols"]

        final_symbols = {
            shadow_cli.normalize_symbol_identity(item["symbol"])
            for item in result["final_ranked_top5"]
            if item.get("final_rank") is not None
        }
        assert set(result["gpt_completed_symbols"]) == final_symbols
        assert all(
            item["gpt_used"]
            and item["gpt_analysis_status"] == "completed"
            and item["ai_buy_score"] is not None
            and item["ai_sell_score"] is not None
            for item in result["final_ranked_top5"]
        )
        selected = [
            item for item in result["final_ranked_top5"] if item["final_selected"]
        ]
        rank_one = next(
            item for item in result["final_ranked_top5"] if item["final_rank"] == 1
        )
        assert len(selected) == 1
        assert selected[0]["symbol"] == rank_one["symbol"]
        assert selected[0]["symbol"] == result["selected_final_symbol"]
        assert result["broker_submit_called"] is False
        assert result["real_order_submitted"] is False
        assert result["safety"]["broker_submit_called"] is False
        assert result["safety"]["real_order_submitted"] is False
        assert preview.client.submit_calls == 0

    assert user_result["snapshot"]["effective_max_candidate_price"] == 14_900
    assert all(
        item["current_price"] <= user_result["snapshot"]["effective_max_candidate_price"]
        for item in user_result["snapshot_items"]
    )
