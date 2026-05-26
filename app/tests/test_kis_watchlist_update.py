from __future__ import annotations

import yaml
import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


class _FakeRankingClient:
    def __init__(self, *, kospi_rows=None, kosdaq_rows=None):
        self.rows_by_market = {
            "KOSPI": list(kospi_rows or []),
            "KOSDAQ": list(kosdaq_rows or []),
        }
        self.calls = []

    def get_domestic_market_cap_ranking(self, *, market: str = "KOSDAQ", limit: int = 50):
        normalized_market = market.upper()
        self.calls.append({"market": normalized_market, "limit": limit})
        return self.rows_by_market.get(normalized_market, [])[:limit]


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_balanced_preview_fetches_kospi_30_and_kosdaq_20(monkeypatch, client):
    fake_client = _FakeRankingClient(
        kospi_rows=_kospi_rows(30),
        kosdaq_rows=_kosdaq_rows(20),
    )
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake_client)

    response = client.get("/kis/watchlist/kosdaq-top50/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kr_watchlist_balanced_update_preview"
    assert body["source_market"] == "KR"
    assert body["source_market_label"] == "한국"
    assert body["group_label"] == "코스피 Top 30 + 코스닥 Top 20"
    assert body["count"] == 50
    assert body["target_count"] == 50
    assert body["required_symbols_present"] is True
    assert body["updated"] is False
    assert body["groups"] == [
        {
            "market": "KOSPI",
            "market_label": "코스피",
            "target_count": 30,
            "count": 30,
            "ranking_symbol_count": 30,
        },
        {
            "market": "KOSDAQ",
            "market_label": "코스닥",
            "target_count": 20,
            "count": 20,
            "ranking_symbol_count": 20,
        },
    ]
    assert body["symbols"][0]["symbol"] == "005930"
    assert body["symbols"][0]["market"] == "KOSPI"
    assert body["symbols"][0]["market_label"] == "코스피"
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert fake_client.calls == [
        {"market": "KOSPI", "limit": 30},
        {"market": "KOSDAQ", "limit": 20},
    ]


def test_balanced_update_writes_exact_30_kospi_20_kosdaq_and_backup(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    _write_watchlist(
        watchlist_path,
        [
            {"symbol": "005930", "name": "Samsung", "market": "KOSPI"},
            {"symbol": "035420", "name": "NAVER", "market": "KOSPI"},
            {"symbol": "999999", "name": "Manual", "market": "KOSDAQ"},
        ],
    )
    fake_client = _FakeRankingClient(
        kospi_rows=_kospi_rows(30),
        kosdaq_rows=_kosdaq_rows(20),
    )
    monkeypatch.setattr("app.routes.kis._client", lambda db: fake_client)
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )
    _fail_order_paths(monkeypatch)

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "kr_watchlist_balanced_update_applied"
    assert body["updated"] is True
    assert body["count"] == 50
    assert body["target_count"] == 50
    assert body["source_market"] == "KR"
    assert body["source_market_label"] == "한국"
    assert body["group_label"] == "코스피 Top 30 + 코스닥 Top 20"
    assert body["required_symbols_present"] is True
    assert body["real_order_submitted"] is False
    assert body["broker_submit_called"] is False
    assert body["manual_submit_called"] is False
    assert body["backup_file"]
    assert body["watchlist_file"] == str(watchlist_path)
    assert fake_client.calls == [
        {"market": "KOSPI", "limit": 30},
        {"market": "KOSDAQ", "limit": 20},
    ]
    assert "035420" in {item["symbol"] for item in body["kept_symbols"]}
    assert "999999" in {item["symbol"] for item in body["removed_symbols"]}

    saved = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    assert saved["market"] == "KR"
    assert saved["currency"] == "KRW"
    assert saved["timezone"] == "Asia/Seoul"
    assert len(saved["symbols"]) == 50
    assert _market_counts(saved["symbols"]) == {"KOSPI": 30, "KOSDAQ": 20}
    assert saved["symbols"][0] == {
        "symbol": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
    }
    assert saved["symbols"][1] == {
        "symbol": "035420",
        "name": "NAVER",
        "market": "KOSPI",
    }
    assert all("market_label" not in item for item in saved["symbols"])
    backups = list(tmp_path.glob("watchlist_kr.backup.*.yaml"))
    assert len(backups) == 1
    backup = yaml.safe_load(backups[0].read_text(encoding="utf-8"))
    assert backup["symbols"][0]["symbol"] == "005930"


def test_balanced_update_dedupes_and_preserves_leading_zeroes(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    _write_watchlist(
        watchlist_path,
        [
            {"symbol": "000001", "name": "Old One", "market": "KOSPI"},
            {"symbol": "299999", "name": "Fallback KOSPI", "market": "KOSPI"},
        ],
    )
    kospi_rows = [
        {"symbol": "1", "name": "KOSPI 1", "market": "KOSPI", "rank": 1},
        {"symbol": "000001", "name": "KOSPI duplicate", "market": "KOSPI", "rank": 2},
        *_kospi_rows(28, start=10),
    ]
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=kospi_rows,
            kosdaq_rows=_kosdaq_rows(20),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    body = response.json()
    saved = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    symbols = [item["symbol"] for item in saved["symbols"]]
    assert len(symbols) == len(set(symbols)) == 50
    assert "000001" in symbols
    assert "299999" in symbols
    assert any(item["symbol"] == "000001" for item in body["deduped_symbols"])


def test_balanced_update_uses_current_symbols_as_same_market_fallback(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    current_rows = [
        {"symbol": str(300000 + index), "name": f"KOSPI Fallback {index}", "market": "KOSPI"}
        for index in range(1, 4)
    ] + [
        {"symbol": str(900000 + index), "name": f"KOSDAQ Fallback {index}", "market": "KOSDAQ"}
        for index in range(1, 3)
    ]
    _write_watchlist(watchlist_path, current_rows)
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=_kospi_rows(27),
            kosdaq_rows=_kosdaq_rows(18),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    body = response.json()
    saved = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    assert len(saved["symbols"]) == 50
    assert _market_counts(saved["symbols"]) == {"KOSPI": 30, "KOSDAQ": 20}
    assert body["count"] == 50
    kept_symbols = {item["symbol"] for item in body["kept_symbols"]}
    assert {"300001", "300002", "300003", "900001", "900002"} <= kept_symbols


def test_balanced_update_injects_required_symbols_when_ranking_misses_them(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    _write_watchlist(watchlist_path, [])
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=_kospi_rows(30, include_required=False),
            kosdaq_rows=_kosdaq_rows(20),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    saved = yaml.safe_load(watchlist_path.read_text(encoding="utf-8"))
    symbols = {item["symbol"] for item in saved["symbols"]}
    assert {"005930", "035420"} <= symbols
    assert _market_counts(saved["symbols"]) == {"KOSPI": 30, "KOSDAQ": 20}


def test_balanced_update_reports_removed_symbols_when_old_file_had_59_symbols(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    current_rows = [
        {"symbol": str(400000 + index), "name": f"Old KOSPI {index}", "market": "KOSPI"}
        for index in range(1, 31)
    ] + [
        {"symbol": str(800000 + index), "name": f"Old KOSDAQ {index}", "market": "KOSDAQ"}
        for index in range(1, 30)
    ]
    _write_watchlist(watchlist_path, current_rows)
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=_kospi_rows(30),
            kosdaq_rows=_kosdaq_rows(20),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 50
    assert body["removed_symbols"]
    assert "800001" in {item["symbol"] for item in body["removed_symbols"]}


def test_balanced_update_aborts_when_too_few_symbols(
    monkeypatch,
    client,
    tmp_path,
):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    original = "market: KR\ncurrency: KRW\ntimezone: Asia/Seoul\nsymbols: []\n"
    watchlist_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=_kospi_rows(1),
            kosdaq_rows=_kosdaq_rows(1),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 400
    assert "Balanced KR watchlist update aborted" in response.json()["detail"]
    assert watchlist_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("watchlist_kr.backup.*.yaml")) == []


def test_balanced_update_does_not_call_order_paths(monkeypatch, client, tmp_path):
    watchlist_path = tmp_path / "watchlist_kr.yaml"
    watchlist_path.write_text(
        "market: KR\ncurrency: KRW\ntimezone: Asia/Seoul\nsymbols: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.routes.kis._client",
        lambda db: _FakeRankingClient(
            kospi_rows=_kospi_rows(30),
            kosdaq_rows=_kosdaq_rows(20),
        ),
    )
    monkeypatch.setattr(
        "app.services.kis_watchlist_update_service.MarketProfileService.get_watchlist_path",
        lambda self, market: str(watchlist_path),
    )
    _fail_order_paths(monkeypatch)

    response = client.post("/kis/watchlist/kosdaq-top50/update")

    assert response.status_code == 200


def _kospi_rows(count: int, *, include_required: bool = True, start: int = 1):
    rows = []
    if include_required and count >= 1:
        rows.append(
            {
                "symbol": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "market_cap": 50_000_000_000,
                "rank": 1,
            }
        )
    if include_required and count >= 2:
        rows.append(
            {
                "symbol": "035420",
                "name": "NAVER",
                "market": "KOSPI",
                "market_cap": 49_000_000_000,
                "rank": 2,
            }
        )
    index = start
    while len(rows) < count:
        symbol = str(200000 + index).zfill(6)
        if symbol not in {"005930", "035420"}:
            rows.append(
                {
                    "symbol": symbol,
                    "name": f"KOSPI {index}",
                    "market": "KOSPI",
                    "market_cap": 40_000_000_000 - index,
                    "rank": len(rows) + 1,
                }
            )
        index += 1
    return rows


def _kosdaq_rows(count: int, *, start: int = 1):
    return [
        {
            "symbol": str(100000 + index).zfill(6),
            "name": f"KOSDAQ {index}",
            "market": "KOSDAQ",
            "market_cap": 10_000_000_000 - index,
            "rank": index,
        }
        for index in range(start, start + count)
    ]


def _write_watchlist(path, symbols):
    path.write_text(
        yaml.safe_dump(
            {
                "market": "KR",
                "currency": "KRW",
                "timezone": "Asia/Seoul",
                "symbols": symbols,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _market_counts(symbols):
    counts: dict[str, int] = {}
    for item in symbols:
        counts[item["market"]] = counts.get(item["market"], 0) + 1
    return counts


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
