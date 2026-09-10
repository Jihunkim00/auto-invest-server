from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import yaml
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import WatchlistSnapshotItem, WatchlistSnapshotRun
from app.main import app
from app.services.watchlist_snapshot_scheduler import (
    WATCHLIST_REFRESH_TIMES,
    WatchlistSnapshotScheduler,
)
from app.services.watchlist_snapshot_selection_service import (
    WatchlistSnapshotSelectionService,
)
from app.services.watchlist_snapshot_service import WatchlistSnapshotService


class FakeKisClient:
    def __init__(self, prices: dict[str, float] | None = None, *, fail_quotes: bool = False):
        self.prices = prices or {}
        self.fail_quotes = fail_quotes
        self.price_calls: list[str] = []
        self.bar_calls: list[str] = []

    def get_domestic_stock_price(self, symbol: str):
        self.price_calls.append(symbol)
        if self.fail_quotes:
            raise RuntimeError('quote failed')
        return {
            'symbol': symbol,
            'name': f'Name {symbol}',
            'current_price': self.prices.get(symbol, 100.0),
        }

    def get_domestic_daily_bars(self, symbol: str, limit: int = 120):
        self.bar_calls.append(symbol)
        base = self.prices.get(symbol, 100.0)
        return [
            {
                'timestamp': (datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)).isoformat(),
                'open': base + index * 0.1,
                'high': base + index * 0.1 + 1,
                'low': base + index * 0.1 - 1,
                'close': base + index * 0.1,
                'volume': 1000 + index,
            }
            for index in range(60)
        ]


class FakeIndicatorService:
    def calculate(self, bars, *, current_price=None):
        price = float(current_price or 0)
        payload = {
            'price': price,
            'ema20': price,
            'ema50': price,
            'rsi': 50.0,
            'vwap': price,
            'atr': 1.0,
            'volume_ratio': 1.0,
            'short_momentum': price,
            'recent_return': 0.0,
            'day_open': price,
            'previous_high': price + 1,
            'previous_low': price - 1,
        }
        return {'indicator_payload': payload, 'indicator_status': 'ok', 'bar_count': 60}


class FakeQuantService:
    def score(self, indicators, gate_level=None):
        buy = float(indicators['short_momentum'])
        return {
            'quant_buy_score': buy,
            'quant_sell_score': 100.0 - buy,
            'quant_reason': 'fake deterministic score',
            'quant_notes': [],
        }


def _write_universe(path, *, kospi: int = 100, kosdaq: int = 100):
    rows = []
    for index in range(kospi):
        rows.append({'symbol': f'{index + 1:06d}', 'name': f'KOSPI {index}', 'market': 'KOSPI'})
    for index in range(kosdaq):
        rows.append({'symbol': f'{500000 + index:06d}', 'name': f'KOSDAQ {index}', 'market': 'KOSDAQ'})
    path.write_text(yaml.safe_dump({'symbols': rows}, sort_keys=False), encoding='utf-8')
    return rows


def _service(path, client):
    return WatchlistSnapshotService(
        client=client,
        universe_path=path,
        indicator_service=FakeIndicatorService(),
        quant_signal_service=FakeQuantService(),
    )


def test_refresh_stores_200_snapshot_items_and_only_reads_market_data(tmp_path, db_session):
    universe_path = tmp_path / 'universe.yaml'
    rows = _write_universe(universe_path)
    client = FakeKisClient({row['symbol']: 70.0 for row in rows})

    result = _service(universe_path, client).refresh(db_session)

    assert result['status'] == 'success'
    assert result['source_count'] == 200
    assert result['scored_count'] == 200
    assert result['error_count'] == 0
    assert db_session.query(WatchlistSnapshotItem).count() == 200
    assert len(client.price_calls) == 200
    assert len(client.bar_calls) == 200
    assert all(hasattr(client, method) is False for method in ('submit_order', 'submit_domestic_cash_order'))


def test_selection_applies_price_cap_and_kospi_kosdaq_limits(tmp_path, db_session):
    universe_path = tmp_path / 'universe.yaml'
    rows = _write_universe(universe_path, kospi=45, kosdaq=15)
    prices = {row['symbol']: 100.0 + index for index, row in enumerate(rows)}
    result = _service(universe_path, FakeKisClient(prices)).refresh(db_session)
    assert result['status'] == 'success'

    selected = WatchlistSnapshotSelectionService().select_candidates(
        db_session,
        price_cap_krw=120,
        min_quant_buy_score=0,
        kospi_limit=40,
        kosdaq_limit=10,
    )

    assert selected['kospi_count'] == 21
    assert selected['kosdaq_count'] == 0
    assert selected['total_count'] == 21
    assert all(item['current_price'] <= 120 for item in selected['candidates'])

    capped = WatchlistSnapshotSelectionService().select_candidates(
        db_session,
        price_cap_krw=10000,
        min_quant_buy_score=0,
        kospi_limit=40,
        kosdaq_limit=10,
    )
    assert capped['kospi_count'] == 40
    assert capped['kosdaq_count'] == 10
    assert capped['total_count'] == 50


def test_selection_orders_by_buy_score_sell_score_then_symbol(db_session):
    now = datetime.now(UTC)
    run = WatchlistSnapshotRun(
        market='KR', started_at=now, completed_at=now,
        source_count=3, scored_count=3, error_count=0,
        elapsed_seconds=0.1, status='success',
    )
    db_session.add(run)
    db_session.flush()
    for symbol, buy, sell in [('000003', 80, 10), ('000002', 80, 5), ('000001', 80, 5)]:
        db_session.add(WatchlistSnapshotItem(
            run_id=run.id, symbol=symbol, name=symbol, market='KOSPI',
            current_price=100, quant_buy_score=buy, quant_sell_score=sell,
            indicators_json='{}', quant_reason='test', captured_at=now,
        ))
    db_session.commit()

    result = WatchlistSnapshotSelectionService().select_candidates(
        db_session, kospi_limit=3, kosdaq_limit=0,
    )
    assert [item['symbol'] for item in result['candidates']] == ['000001', '000002', '000003']


def test_refresh_overlap_is_rejected_without_a_second_run(tmp_path, db_session):
    universe_path = tmp_path / 'universe.yaml'
    _write_universe(universe_path, kospi=1, kosdaq=0)
    service = _service(universe_path, FakeKisClient())
    service._refresh_lock.acquire()
    try:
        result = service.refresh(db_session)
    finally:
        service._refresh_lock.release()
    assert result['status'] == 'already_running'
    assert db_session.query(WatchlistSnapshotRun).count() == 0


def test_failed_refresh_preserves_last_successful_snapshot(tmp_path, db_session):
    universe_path = tmp_path / 'universe.yaml'
    _write_universe(universe_path, kospi=2, kosdaq=0)
    first = _service(universe_path, FakeKisClient()).refresh(db_session)
    failed = _service(universe_path, FakeKisClient(fail_quotes=True)).refresh(db_session)

    assert first['status'] == 'success'
    assert failed['status'] == 'failed'
    assert WatchlistSnapshotSelectionService().select_candidates(db_session)['snapshot_id'] == first['snapshot_id']


def test_scheduler_refresh_times_are_independent_of_trading_configuration():
    assert WATCHLIST_REFRESH_TIMES == ('08:50', '09:50', '10:50', '11:50', '12:50', '13:50')

    class NoopService:
        def latest_successful_run(self, db, *, market):
            return object()

    scheduler = WatchlistSnapshotScheduler(NoopService(), session_factory=lambda: _DummySession())
    assert scheduler.service is not None


def test_scheduler_bootstraps_missing_snapshot_in_background_service():
    class RecordingService:
        def __init__(self):
            self.calls = []

        def latest_successful_run(self, db, *, market):
            return None

        def refresh(self, db, *, market):
            self.calls.append(market)
            return {'status': 'success'}

    service = RecordingService()
    scheduler = WatchlistSnapshotScheduler(
        service,
        session_factory=lambda: _DummySession(),
        now_provider=lambda: datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
    )
    scheduler._bootstrap_if_needed()
    assert service.calls == ['KR']


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_watchlist_snapshot_endpoints_do_not_depend_on_trading_scheduler(tmp_path, db_session):
    universe_path = tmp_path / 'universe.yaml'
    _write_universe(universe_path, kospi=1, kosdaq=0)
    snapshot_service = __import__('app.routes.market_analysis', fromlist=['watchlist_snapshot_service']).watchlist_snapshot_service
    old_client = snapshot_service.client
    old_path = snapshot_service.universe_path
    snapshot_service.client = FakeKisClient()
    snapshot_service.universe_path = universe_path

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post('/market-analysis/watchlist/snapshot/refresh')
        assert response.status_code == 200
        assert response.json()['status'] == 'success'
        selected = client.get('/market-analysis/watchlist/snapshot/select').json()
        assert selected['snapshot_id'] == response.json()['snapshot_id']
    finally:
        snapshot_service.client = old_client
        snapshot_service.universe_path = old_path
        app.dependency_overrides.clear()
