from types import SimpleNamespace

from app.services.gpt_market_service import GPTMarketService, MarketGateContext
from app.services.risk_service import RiskService


def _runtime(**overrides):
    values = {
        "global_daily_entry_limit": 10,
        "per_symbol_daily_entry_limit": 10,
    }
    values.update(overrides)
    return values


class _FakeBroker:
    def get_position(self, symbol):
        return None

    def get_account(self):
        return SimpleNamespace(equity=100000.0)


def _service(monkeypatch):
    svc = RiskService()
    svc.broker = _FakeBroker()
    monkeypatch.setattr(svc, "_is_near_market_close", lambda now_utc: False)
    monkeypatch.setattr(svc.runtime_settings, "get_settings", lambda db: _runtime())
    return svc


def _event_risk(**overrides):
    payload = {
        "symbol": "AAPL",
        "market": "US",
        "has_near_event": True,
        "event_type": "earnings",
        "event_date": "2026-05-04",
        "event_time_label": "after_close",
        "days_to_event": 1,
        "risk_level": "high",
        "entry_blocked": True,
        "scale_in_blocked": True,
        "position_size_multiplier": 0.0,
        "force_gate_level": 1,
        "reason": "earnings within restricted window",
        "source": "investing",
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_alpaca_risk_blocks_buy_on_d_minus_one_earnings(monkeypatch, db_session):
    svc = _service(monkeypatch)

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
        event_risk=_event_risk(days_to_event=1),
    )

    assert result["approved"] is False
    assert "event_risk_entry_block" in result["risk_flags"]
    assert result["reason"] == "near_earnings_event"
    assert result["event_risk"]["source"] == "investing"


def test_alpaca_risk_reduces_size_on_d_minus_two_earnings(monkeypatch, db_session):
    svc = _service(monkeypatch)

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
        event_risk=_event_risk(
            days_to_event=2,
            risk_level="medium",
            entry_blocked=False,
            position_size_multiplier=0.5,
            force_gate_level=None,
        ),
    )

    assert result["approved"] is True
    assert "event_risk_position_size_reduced" in result["risk_flags"]
    assert result["position_size_pct"] == 0.05


def test_alpaca_risk_missing_event_data_warns_without_blocking(
    monkeypatch,
    db_session,
):
    svc = _service(monkeypatch)

    result = svc.evaluate(
        db_session,
        symbol="AAPL",
        action="buy",
        final_buy_score=80,
        event_risk=_event_risk(
            has_near_event=False,
            entry_blocked=False,
            scale_in_blocked=False,
            position_size_multiplier=1.0,
            warnings=["event_data_unavailable"],
        ),
    )

    assert result["approved"] is True
    assert result["warnings"] == ["event_data_unavailable"]
    assert "event_data_unavailable" not in result["risk_flags"]


def test_sell_exit_management_is_not_blocked_by_event_risk():
    svc = RiskService()
    position = SimpleNamespace(unrealized_plpc=-0.02)

    result = svc.evaluate_exit(
        position=position,
        final_sell_score=72,
        final_buy_score=50,
    )

    assert result["should_exit"] is True
    assert "stop_loss_triggered" in result["reasons"]


def test_gpt_market_prompt_includes_event_context_and_uncertainty_rule():
    service = GPTMarketService()
    context = MarketGateContext(cached_site_summaries=[], used_cache=False)

    system_prompt, user_prompt = service._build_prompt(
        symbol="AAPL",
        indicators={"price": 100, "ema20": 101, "ema50": 99},
        context=context,
        gate_level=2,
        gate_profile_name="conservative",
        event_context=_event_risk(days_to_event=1),
    )

    assert "Earnings or earnings-call events are uncertainty risks" in system_prompt
    assert "Do not treat upcoming earnings as a reason to buy" in system_prompt
    assert '"event_context"' in user_prompt
    assert '"risk_policy": "block_new_entry"' in user_prompt
