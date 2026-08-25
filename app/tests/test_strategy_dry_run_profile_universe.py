from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.routes.strategy_dry_run import get_profile_aware_dry_run_auto_buy_service
from app.schemas.automation_profile import AutomationProfileWriteRequest
from app.services.automation_profile_service import AutomationProfileService
from app.services.kis_watchlist_preview_service import KisGptPreview, KisWatchlistPreviewService
from app.services.market_profile_service import MarketProfileService
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)
from app.services.quant_signal_service import QuantSignalService
from app.services.technical_indicator_service import TechnicalIndicatorService


PROFILE_KEY = 'route-universe-profile'
PRICES = {
    '055550': 107300.0,
    '086790': 132300.0,
    '000810': 644000.0,
    '207940': 1572000.0,
}
SCORES = {
    107300: 70.0,
    132300: 68.0,
    644000: 80.0,
    1572000: 90.0,
}


class RouteFakeKisClient:
    def __init__(self) -> None:
        self.submit_calls = 0

    def list_positions(self) -> list[dict[str, Any]]:
        return []

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []

    def get_account_balance(self) -> dict[str, Any]:
        return {
            'cash': 10_000_000.0,
            'orderable_cash': 10_000_000.0,
            'total_asset_value': 10_000_000.0,
        }

    def get_domestic_stock_price(self, symbol: str) -> dict[str, Any]:
        return {
            'symbol': symbol,
            'name': f'Test {symbol}',
            'current_price': PRICES[symbol],
        }

    def get_domestic_daily_bars(self, symbol: str, limit: int = 120) -> list[dict[str, Any]]:
        return []

    def submit_market_buy(self, **kwargs: Any) -> dict[str, Any]:
        self.submit_calls += 1
        raise AssertionError('route regression must never submit a KIS order')


def test_real_dry_run_route_enforces_active_profile_price_universe(
    db_session,
    monkeypatch,
):
    profile_service = AutomationProfileService()
    profile_service.create(
        db_session,
        AutomationProfileWriteRequest(
            profile_key=PROFILE_KEY,
            name='Route universe profile',
            provider='kis',
            market='KR',
            enabled=True,
            status='active',
            universe={
                'min_price_krw': 5000,
                'max_price_krw': 500000,
            },
            entry={'min_final_score': 65},
            operation={
                'start_date': '2026-08-01',
                'end_date': '2026-09-30',
                'weekdays_only': False,
                'timezone': 'Asia/Seoul',
            },
        ),
    )
    profile_service.activate(db_session, PROFILE_KEY)

    symbols = [
        {'symbol': symbol, 'name': f'Test {symbol}', 'market': 'KR'}
        for symbol in PRICES
    ]
    monkeypatch.setattr(
        MarketProfileService,
        'load_watchlist',
        lambda self, market=None: {
            'market': 'KR',
            'currency': 'KRW',
            'timezone': 'Asia/Seoul',
            'watchlist_file': 'route-test',
            'count': len(symbols),
            'symbols': symbols,
        },
    )
    monkeypatch.setattr(
        MarketProfileService,
        'load_reference_sites',
        lambda self, market=None: {
            'reference_sites_file': 'route-test',
            'sources': [],
        },
    )

    def fake_indicators(
        self,
        bars: list[dict[str, Any]],
        *,
        current_price: float | None = None,
    ) -> dict[str, Any]:
        price = float(current_price or 0)
        return {
            'indicator_status': 'ok',
            'indicator_payload': {
                'price': price,
                'ema20': price,
                'ema50': price,
                'rsi': 50.0,
                'vwap': price,
                'atr': 100.0,
                'volume_ratio': 1.2,
                'short_momentum': 0.01,
                'day_open': price,
                'previous_high': price,
                'previous_low': price,
            },
            'bar_count': 120,
        }

    monkeypatch.setattr(TechnicalIndicatorService, 'calculate', fake_indicators)

    def fake_quant_score(
        self,
        indicators: dict[str, Any],
        gate_level: int | None = None,
    ) -> dict[str, Any]:
        score = SCORES[int(round(float(indicators['price'])))]
        return {
            'quant_buy_score': score,
            'quant_sell_score': 20.0,
            'quant_reason': 'route regression score',
            'quant_notes': [],
        }

    monkeypatch.setattr(QuantSignalService, 'score', fake_quant_score)
    monkeypatch.setattr(
        'app.services.kis_watchlist_preview_service.KisPreviewGptAdvisor.analyze',
        lambda *args, **kwargs: KisGptPreview(
            gpt_used=False,
            action_hint='watch',
            gpt_reason=None,
            warnings=['gpt_disabled_for_route_regression'],
            gpt_analysis_status='failed',
            gpt_analysis_reason='deterministic route regression',
        ),
    )

    fake_client = RouteFakeKisClient()

    def override_service():
        return build_profile_aware_dry_run_auto_buy_service(
            db_session,
            client_factory=lambda session: fake_client,
        )

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[
        get_profile_aware_dry_run_auto_buy_service
    ] = override_service
    try:
        response = TestClient(app).post(
            '/strategy/dry-run/auto-buy-once',
            json={
                'automation_profile_key': PROFILE_KEY,
                'max_candidates': 5,
                'use_watchlist': True,
                'save_logs': False,
            },
        )
    finally:
        app.dependency_overrides.pop(get_profile_aware_dry_run_auto_buy_service, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    body = response.json()
    candidates = body['candidates']
    symbols_in_response = {item['symbol'] for item in candidates}
    assert '000810' not in symbols_in_response
    assert '207940' not in symbols_in_response
    assert all(float(item['price']) <= 500000 for item in candidates)
    assert body['profile_price_filtered_count'] >= 2
    assert body['profile_eligible_symbol_count'] == 2
    assert body['configured_symbol_count'] == 4
    assert body['analyzed_symbol_count'] == 2
    assert body['quant_scored_count'] == 2
    assert body['gpt_candidate_count'] == 2
    assert body['final_ranked_count'] == 2
    assert body['execution_candidate_count'] == 2
    assert body['profile_exclusion_counts']['profile_max_price_exceeded'] == 2
    assert body['selected_symbol'] in {'055550', '086790'}
    assert float(body['simulated_price']) <= 500000
    assert fake_client.submit_calls == 0
