from __future__ import annotations

import yaml
import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


class _FakeRankingClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_domestic_market_cap_ranking(self, *, market: str = "KOSDAQ", limit: int = 50):
        self.calls.append({"market": market, "limit": limit})
        return self.rows[:limit]


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_kosdaq_top50_preview_is_read_only(monkeypatch, client):
    fake_client = _FakeRankingClient(_ranking_rows(50))
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake_client)

    response = client.get("/kis/watchlist/kosdaq-top50/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "watchlist_update_preview"
    assert body["source_market"] == "KOSDAQ"
    assert body["count"] == 50
    assert body["updated"] is False
    assert body["symbols"][0]["symbol"] == "100001"
    assert body["symbols"][0]["market"] == "KOSDAQ"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert fake_client.calls == [{"market": "KOSDAQ", "limit": 50}]


def test_kosdaq_top50_update_replaces_watchlist_and_creates_backup(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "market": "KR",
                "currency": "KRW",
                "timezone": "Asia/Seoul",
                "symbols": [
                    {"symbol": "005930", "name": "Samsung", "market": "KOSPI"}
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fake_client = _FakeRankingClient(_ranking_rows(50))
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake_client)
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )
    _fail_order_paths(monkeypatch)

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "watchlist_update_applied"
    assert body["updated"] is True
    assert body["count"] == 50
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["backup_file"]
    assert body["watchlist_file"] == str(watchlist_path)
    assert fake_client.calls == [{"market": "KOSDAQ", "limit": 50}]

    saved = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    assert saved["market"] == "KR"
    assert saved["currency"] == "KRW"
    assert saved["timezone"] == "Asia/Seoul"
    assert len(saved["symbols"]) == 50
    assert all(item["market"] == "KOSDAQ" for item in saved["symbols"])
    assert saved["symbols"][0] == {
        "symbol": "100001",
        "name": "KOSDAQ 1",
        "market": "KOSDAQ",
    }
    backups = list(tmp_path.glob("watchlist_kr.backup.*.yaml"))
    assert len(backups) == 1
    backup = yaml.safe_load(backups[0].read_text(encoding="utf-8"))
    assert backup["symbols"][0]["symbol"] == "005930"


def test_kosdaq_top50_update_aborts_when_too_few_symbols(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    original = "market: KR\ncurrency: KRW\ntimezone: Asia/Seoul\nsymbols: []\n"
    watchlist_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(_ranking_rows(9)),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 400
    assert "aborted" in response.json()["detail"]
    assert watchlist_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("watchlist_kr.backup.*.yaml")) == []


def test_kosdaq_top50_update_does_not_call_order_paths(monkeypatch, client, tmp_path):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    watchlist_path.write_text(
        "market: KR\ncurrency: KRW\ntimezone: Asia/Seoul\nsymbols: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(_ranking_rows(50)),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )
    _fail_order_paths(monkeypatch)

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200


def _ranking_rows(count: int):
    return [
        {
            "symbol": str(100000 + index).zfill(6),
            "name": f"KOSDAQ {index}",
            "market": "KOSDAQ",
            "market_cap": 10_000_000_000 - index,
            "rank": index,
        }
        for index in range(1, count + 1)
    ]


def _fail_order_paths(monkeypatch):
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("watchlist update must not submit orders"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_domestic_cash_order",
        lambda *args, **kwargs: pytest.fail("watchlist update must not submit orders"),
    )
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.build_domestic_order_payload",
        lambda *args, **kwargs: pytest.fail("watchlist update must not build orders"),
    )
    monkeypatch.setattr(
        "app.services.kis_manual_order_service.KisManualOrderService.submit_manual",
        lambda *args, **kwargs: pytest.fail("watchlist update must not submit manual orders"),
    )
