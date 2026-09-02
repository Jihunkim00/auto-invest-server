from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.services.kis_watchlist_update_service import (
    KisWatchlistUpdateError,
    KisWatchlistUpdateService,
)
import app.services.scheduler_service
from app.services.automation_scheduler_service import (
    AUTOMATION_WATCHLIST_REFRESH_JOB_ID,
    AutomationSchedulerService,
)
import app.services.automation_scheduler_service as automation_scheduler_module
import app.services.kis_watchlist_update_service as watchlist_module


class FakePriceClient:
    def __init__(
        self,
        prices: dict[str, float],
        failures: set[str] | None = None,
    ) -> None:
        self.prices = prices
        self.failures = failures or set()
        self.calls: list[str] = []
        self.submit_calls = 0

    def get_domestic_stock_price(self, symbol: str) -> dict[str, Any]:
        self.calls.append(symbol)
        if symbol in self.failures:
            raise RuntimeError('quote unavailable')
        return {'symbol': symbol, 'current_price': self.prices.get(symbol, 100000.0)}


class FakeProfileService:
    def __init__(self, watchlist_path: Path) -> None:
        self.watchlist_path = watchlist_path

    def get_watchlist_path(self, market: str) -> str:
        assert market == 'KR'
        return str(self.watchlist_path)


def _source_rows(kospi: int = 150, kosdaq: int = 50) -> list[dict[str, str]]:
    return [
        {
            'symbol': str(100000 + index).zfill(6),
            'name': f'KOSPI {index}',
            'market': 'KOSPI',
        }
        for index in range(kospi)
    ] + [
        {
            'symbol': str(200000 + index).zfill(6),
            'name': f'KOSDAQ {index}',
            'market': 'KOSDAQ',
        }
        for index in range(kosdaq)
    ]


def _profile(
    *,
    sizing_mode: str = 'fixed_budget',
    fixed_budget: float | None = 300000.0,
    max_order_notional: float | None = 300000.0,
    configured_max: float | None = 500000.0,
) -> dict[str, Any]:
    return {
        'settings': {
            'capital': {
                'sizing_mode': sizing_mode,
                'fixed_budget': fixed_budget,
                'max_order_notional_krw': max_order_notional,
            },
            'universe': {
                'min_price_krw': 0,
                'max_price_krw': configured_max,
            },
        }
    }


def _install_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    source_path = tmp_path / 'watchlist_kr_test4_universe.yaml'
    source_path.write_text(
        yaml.safe_dump({'market': 'KR', 'symbols': rows}, sort_keys=False),
        encoding='utf-8',
    )
    monkeypatch.setattr(
        watchlist_module,
        'AUTOMATION_WATCHLIST_SOURCE_FILE',
        str(source_path),
    )
    return source_path


def _service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    prices: dict[str, float] | None = None,
    failures: set[str] | None = None,
    rows: list[dict[str, str]] | None = None,
) -> tuple[KisWatchlistUpdateService, FakePriceClient, Path]:
    source_path = _install_source(monkeypatch, tmp_path, rows or _source_rows())
    client = FakePriceClient(prices or {}, failures=failures)
    target_path = tmp_path / 'watchlist_kr.yaml'
    service = KisWatchlistUpdateService(
        client,
        profile_service=FakeProfileService(target_path),
    )
    return service, client, source_path


def test_automation_refresh_uses_broad_source_and_40_10_quotas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, client, source_path = _service(monkeypatch, tmp_path)

    result = service.build_automation_watchlist(_profile())

    assert result['source_universe_file'] == str(source_path)
    assert result['source_universe_count'] == 200
    assert result['source_kospi_count'] == 150
    assert result['source_kosdaq_count'] == 50
    assert result['selected_kospi_count'] == 40
    assert result['selected_kosdaq_count'] == 10
    assert result['final_watchlist_count'] == 50
    assert len(client.calls) == 200
    assert result['symbols'][0]['symbol'] == '100000'
    assert result['symbols'][39]['symbol'] == '100039'
    assert result['symbols'][40]['symbol'] == '200000'


def test_automation_refresh_applies_inclusive_price_boundary_and_budget_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prices = {
        '100000': 299999,
        '100001': 300000,
        '100002': 300001,
    }
    service, _client, _source_path = _service(
        monkeypatch,
        tmp_path,
        prices=prices,
    )

    result = service.build_automation_watchlist(_profile())
    selected_symbols = {item['symbol'] for item in result['symbols']}

    assert result['configured_max_price_krw'] == 500000
    assert result['budget_max_price_krw'] == 300000
    assert result['effective_max_price_krw'] == 300000
    assert '100000' in selected_symbols
    assert '100001' in selected_symbols
    assert '100002' not in selected_symbols
    assert result['max_price_in_final_watchlist'] <= 300000
    assert result['over_budget_price_count'] == 0


def test_next_automation_refresh_reflects_changed_automation_max(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, _client, _source_path = _service(
        monkeypatch,
        tmp_path,
        prices={'100000': 250000},
    )

    high_budget = service.build_automation_watchlist(
        _profile(fixed_budget=300000.0, max_order_notional=300000.0)
    )
    lower_budget = service.build_automation_watchlist(
        _profile(fixed_budget=300000.0, max_order_notional=200000.0)
    )

    assert high_budget['effective_max_price_krw'] == 300000
    assert lower_budget['effective_max_price_krw'] == 200000
    assert high_budget['symbols'][0]['symbol'] == '100000'
    assert lower_budget['symbols'][0]['symbol'] == '100001'
    assert high_budget['final_watchlist_count'] == 50
    assert lower_budget['final_watchlist_count'] == 50
    assert lower_budget['max_price_in_final_watchlist'] <= 200000


def test_automation_refresh_preserves_order_and_does_not_cross_fill_shortage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = _source_rows(kospi=35, kosdaq=25)
    service, _client, _source_path = _service(
        monkeypatch,
        tmp_path,
        rows=rows,
    )

    result = service.build_automation_watchlist(_profile())

    assert result['selected_kospi_count'] == 35
    assert result['selected_kosdaq_count'] == 10
    assert result['final_watchlist_count'] == 45
    assert [item['symbol'] for item in result['symbols'][:35]] == [
        str(100000 + index).zfill(6) for index in range(35)
    ]
    assert [item['symbol'] for item in result['symbols'][35:]] == [
        str(200000 + index).zfill(6) for index in range(10)
    ]


def test_automation_refresh_isolates_price_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, client, _source_path = _service(
        monkeypatch,
        tmp_path,
        failures={'100000', '200000'},
    )

    result = service.build_automation_watchlist(_profile())

    assert len(client.calls) == 200
    assert result['price_lookup_success_count'] == 198
    assert result['price_lookup_failure_count'] == 2
    assert result['selected_kospi_count'] == 40
    assert result['selected_kosdaq_count'] == 10
    assert '100000' not in {item['symbol'] for item in result['symbols']}
    assert '200000' not in {item['symbol'] for item in result['symbols']}


def test_automation_refresh_backups_and_replaces_only_after_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, _client, source_path = _service(monkeypatch, tmp_path)
    target_path = tmp_path / 'watchlist_kr.yaml'
    original = 'market: KR\ncurrency: KRW\ntimezone: Asia/Seoul\nsymbols: []\n'
    target_path.write_text(original, encoding='utf-8')

    result = service.update_automation_watchlist(_profile())

    assert result['updated'] is True
    assert result['backup_file']
    assert list(tmp_path.glob('watchlist_kr.backup.*.yaml'))
    saved = yaml.safe_load(target_path.read_text(encoding='utf-8'))
    assert len(saved['symbols']) == 50
    assert all('current_price' not in item for item in saved['symbols'])
    assert not list(tmp_path.glob('.watchlist_kr.yaml.tmp.*'))

    source_path.write_text('symbols: [malformed', encoding='utf-8')
    before_failed_refresh = target_path.read_text(encoding='utf-8')
    with pytest.raises(KisWatchlistUpdateError):
        service.update_automation_watchlist(_profile())
    assert target_path.read_text(encoding='utf-8') == before_failed_refresh


def test_manual_balanced_update_does_not_use_automation_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, client, _source_path = _service(monkeypatch, tmp_path)
    rankings = {
        'KOSPI': [
            {'symbol': '005930', 'name': 'Samsung', 'market': 'KOSPI'},
            {'symbol': '035420', 'name': 'NAVER', 'market': 'KOSPI'},
            *[
                {
                    'symbol': str(300000 + index),
                    'name': f'KOSPI {index}',
                    'market': 'KOSPI',
                }
                for index in range(28)
            ],
        ],
        'KOSDAQ': [
            {
                'symbol': str(400000 + index),
                'name': f'KOSDAQ {index}',
                'market': 'KOSDAQ',
            }
            for index in range(20)
        ],
    }
    monkeypatch.setattr(
        service,
        '_fetch_balanced_rankings',
        lambda: rankings,
    )

    result = service.update_balanced_kr_watchlist()

    assert result['mode'] == 'kr_watchlist_balanced_update_applied'
    assert result['count'] == 50
    assert result['groups'][0]['count'] == 30
    assert result['groups'][1]['count'] == 20
    assert result['backup_file'] is None
    assert client.submit_calls == 0


def test_automation_scheduler_is_idempotent_non_trading_and_separate_from_trade_job(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tests.integration.test_kis_automation_scheduler_replay import build_harness

    harness = build_harness(db_session, monkeypatch)
    scheduler = AutomationSchedulerService()
    scheduler.runtime_settings = harness.runtime
    scheduler.automation_profiles = harness.profiles
    calls: list[dict[str, Any]] = []

    class FakeUpdater:
        def update_automation_watchlist(self, profile: dict[str, Any], *, now: Any) -> dict[str, Any]:
            calls.append({'profile_key': profile['profile_key'], 'now': now})
            return {
                'source_universe_file': 'config/watchlist_kr_test4_universe.yaml',
                'source_universe_count': 200,
                'source_kospi_count': 150,
                'source_kosdaq_count': 50,
                'configured_max_price_krw': 500000,
                'budget_max_price_krw': 300000,
                'effective_max_price_krw': 300000,
                'price_lookup_success_count': 200,
                'price_lookup_failure_count': 0,
                'eligible_kospi_count': 150,
                'eligible_kosdaq_count': 50,
                'selected_kospi_count': 40,
                'selected_kosdaq_count': 10,
                'final_watchlist_count': 50,
                'max_price_in_final_watchlist': 300000,
                'over_budget_price_count': 0,
                'watchlist_file': 'config/watchlist_kr.yaml',
                'backup_file': 'config/watchlist_kr.backup.test.yaml',
                'result': 'success',
                'status': 'success',
                'reason': 'automation_watchlist_refreshed',
                'updated': True,
                'real_order_submitted': False,
                'broker_submit_called': False,
            }

    scheduler.automation_watchlist_update_service = FakeUpdater()
    monkeypatch.setattr(
        automation_scheduler_module,
        'SessionLocal',
        lambda: db_session,
    )

    maintenance_now = harness.clock.now().replace(hour=9, minute=5)
    first = scheduler.run_automation_watchlist_refresh_once(
        now=maintenance_now,
    )
    second = scheduler.run_automation_watchlist_refresh_once(
        now=maintenance_now,
    )

    assert first['job_id'] == AUTOMATION_WATCHLIST_REFRESH_JOB_ID
    assert first['job_type'] == 'maintenance'
    assert first['slot'] == '09:05'
    assert first['real_order_submitted'] is False
    assert first['broker_submit_called'] is False
    assert second['reason'] == 'automation_watchlist_refresh_already_run'
    assert len(calls) == 1
    assert harness.broker.buy_calls == []
    assert harness.broker.sell_calls == []
    assert harness.client.external_kis_submit_count == 0
    assert harness.validation.calls == []
    jobs = scheduler.production_trading_jobs()
    assert len(jobs) == 1
    assert jobs[0]['authority'] == 'AutomationSchedulerService'
    assert jobs[0]['provider'] == 'kis'
    assert jobs[0]['market'] == 'KR'
    assert scheduler.runtime_status()['production_trading_job_count'] == 1
    assert scheduler.runtime_status()['maintenance_job_count'] == 1
    assert scheduler.runtime_status()['last_watchlist_refresh_result'] == 'success'
