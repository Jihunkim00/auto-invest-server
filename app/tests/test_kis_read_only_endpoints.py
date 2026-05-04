from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.brokers.kis_client import normalize_domestic_daily_bars
from app.db.database import get_db
from app.db.models import BrokerAuthToken
from app.main import app


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": False,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _add_access_token(
    db_session,
    value="secret-cached-access-token",
    environment="prod",
    expires_at=None,
):
    row = BrokerAuthToken(
        provider="kis",
        token_type="access_token",
        token_value=value,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
        issued_at=datetime.now(UTC),
        environment=environment,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _find_candidate(payload, symbol):
    for item in payload.get("items") or []:
        if item.get("symbol") == symbol:
            return item
    pytest.fail(f"Expected KIS preview candidate for {symbol}.")


def test_kis_price_endpoint_returns_normalized_current_price(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    settings = _settings(openai_api_key=None)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.get_settings",
        lambda: settings,
    )

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/quotations/inquire-price")
        assert headers["tr_id"] == "FHKST01010100"
        assert params["FID_INPUT_ISCD"] == "005930"
        assert "secret-cached-access-token" in headers["authorization"]
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output": {
                    "hts_kor_isnm": "삼성전자",
                    "stck_prpr": "72,000",
                    "prdy_vrss": "500",
                    "prdy_ctrt": "0.70",
                    "stck_cntg_hour": "093015",
                },
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["environment"] == "prod"
    assert body["symbol"] == "005930"
    assert body["name"] == "삼성전자"
    assert body["current_price"] == 72000.0
    assert body["change"] == 500.0
    assert body["change_rate"] == 0.7
    assert "secret-cached-access-token" not in response.text


def test_kis_daily_bar_normalization_parses_and_sorts_rows():
    bars = normalize_domestic_daily_bars(
        "005930",
        [
            {
                "stck_bsop_date": "20260502",
                "stck_oprc": "72,000",
                "stck_hgpr": "73,000",
                "stck_lwpr": "71,000",
                "stck_clpr": "72,500",
                "acml_vol": "12,345,678",
            },
            {
                "stck_bsop_date": "20260501",
                "stck_oprc": "70,000",
                "stck_hgpr": "71,000",
                "stck_lwpr": "69,000",
                "stck_clpr": "70,500",
                "acml_vol": "10,000",
            },
            {
                "stck_bsop_date": "20260502",
                "stck_oprc": "73,000",
                "stck_hgpr": "74,000",
                "stck_lwpr": "72,000",
                "stck_clpr": "73,500",
                "acml_vol": "13,000",
            },
            {
                "stck_bsop_date": "20260503",
                "stck_oprc": "",
                "stck_hgpr": "0",
                "stck_lwpr": "0",
                "stck_clpr": "",
                "acml_vol": None,
            },
        ],
    )

    assert [bar["timestamp"] for bar in bars] == ["2026-05-01", "2026-05-02"]
    assert bars[0]["open"] == 70000.0
    assert bars[0]["volume"] == 10000.0
    assert bars[1]["close"] == 73500.0


def test_kis_bars_endpoint_returns_normalized_daily_bars(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice")
        assert headers["tr_id"] == "FHKST03010100"
        assert params["FID_INPUT_ISCD"] == "005930"
        assert params["FID_PERIOD_DIV_CODE"] == "D"
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output2": [
                    {
                        "stck_bsop_date": "20260502",
                        "stck_oprc": "72,000",
                        "stck_hgpr": "73,000",
                        "stck_lwpr": "71,000",
                        "stck_clpr": "72,500",
                        "acml_vol": "12,345",
                    },
                    {
                        "stck_bsop_date": "20260501",
                        "stck_oprc": "70,000",
                        "stck_hgpr": "71,000",
                        "stck_lwpr": "69,000",
                        "stck_clpr": "70,500",
                        "acml_vol": "10,000",
                    },
                ],
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/bars/005930?limit=120")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["environment"] == "prod"
    assert body["symbol"] == "005930"
    assert body["count"] == 2
    assert [bar["timestamp"] for bar in body["bars"]] == ["2026-05-01", "2026-05-02"]
    assert "secret-cached-access-token" not in response.text


def test_kis_current_price_matches_across_preview_endpoints(
    monkeypatch,
    client,
    db_session,
):
    _add_access_token(db_session)
    settings = _settings(openai_api_key=None)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.kis_watchlist_preview_service.get_settings",
        lambda: settings,
    )

    requested_symbols = []

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/quotations/inquire-price")
        assert headers["tr_id"] == "FHKST01010100"
        symbol = params["FID_INPUT_ISCD"]
        requested_symbols.append(symbol)
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output": {
                    "hts_kor_isnm": "Samsung Electronics",
                    "stck_prpr": "220,500",
                    "stck_hgpr": "1,286,000",
                    "stck_mxpr": "1,286,000",
                    "stck_sdpr": "1,286,000",
                    "hts_avls": "1,286,000",
                    "prdy_vrss": "0",
                    "prdy_ctrt": "0",
                },
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    market_response = client.get("/kis/market/price/005930")
    watchlist_response = client.post("/kis/watchlist/preview")
    scheduler_response = client.post("/kis/scheduler/run-preview-once")

    assert market_response.status_code == 200
    assert watchlist_response.status_code == 200
    assert scheduler_response.status_code == 200

    market_price = market_response.json()["current_price"]
    watchlist_body = watchlist_response.json()
    scheduler_body = scheduler_response.json()
    watchlist_candidate = _find_candidate(watchlist_body, "005930")
    scheduler_candidate = _find_candidate(scheduler_body, "005930")

    assert market_price == 220500.0
    assert watchlist_candidate["current_price"] == 220500.0
    assert scheduler_candidate["current_price"] == 220500.0
    assert watchlist_candidate["current_price"] != 1286000.0
    assert scheduler_candidate["current_price"] != 1286000.0
    assert requested_symbols.count("005930") == 3

    for payload, candidate in (
        (watchlist_body, watchlist_candidate),
        (scheduler_body, scheduler_candidate),
    ):
        assert payload["preview_only"] is True
        assert payload["trading_enabled"] is False
        assert payload["should_trade"] is False
        assert candidate["action"] == "hold"
        assert candidate["entry_ready"] is False
        assert candidate["trade_allowed"] is False
        assert candidate["approved_by_risk"] is False

    assert scheduler_body["scheduler_preview_only"] is True
    assert scheduler_body["real_order_submitted"] is False


def test_kis_preview_uses_normalized_price_not_raw_quote_fields(
    monkeypatch,
    client,
    db_session,
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_price(self, symbol):
        return {
            "provider": "kis",
            "symbol": symbol,
            "name": "Samsung Electronics",
            "current_price": 220500.0,
            "stck_hgpr": 1286000.0,
            "stck_mxpr": 1286000.0,
            "stck_sdpr": 1286000.0,
            "hts_avls": 1286000.0,
            "raw": {
                "output": {
                    "stck_prpr": "220500",
                    "stck_hgpr": "1286000",
                    "stck_mxpr": "1286000",
                    "stck_sdpr": "1286000",
                    "hts_avls": "1286000",
                }
            },
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.get_domestic_stock_price",
        fake_price,
    )

    watchlist_response = client.post("/kis/watchlist/preview")
    scheduler_response = client.post("/kis/scheduler/run-preview-once")

    assert watchlist_response.status_code == 200
    assert scheduler_response.status_code == 200
    assert (
        _find_candidate(watchlist_response.json(), "005930")["current_price"]
        == 220500.0
    )
    assert (
        _find_candidate(scheduler_response.json(), "005930")["current_price"]
        == 220500.0
    )


def test_kis_balance_endpoint_returns_normalized_summary(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/trading/inquire-balance")
        assert headers["tr_id"] == "TTTC8434R"
        assert params["CANO"] == "12345678"
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output1": [],
                "output2": [
                    {
                        "dnca_tot_amt": "1,000,000",
                        "tot_evlu_amt": "1,200,000",
                        "scts_evlu_amt": "200,000",
                        "pchs_amt_smtl_amt": "180,000",
                        "evlu_pfls_smtl_amt": "20,000",
                        "asst_icdc_erng_rt": "11.11",
                    }
                ],
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/account/balance")

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "KRW"
    assert body["cash"] == 1000000.0
    assert body["total_asset_value"] == 1200000.0
    assert body["stock_evaluation_amount"] == 200000.0
    assert body["purchase_amount"] == 180000.0
    assert body["unrealized_pl"] == 20000.0
    assert body["unrealized_plpc"] == pytest.approx(0.1111)


def test_kis_positions_endpoint_returns_normalized_positions(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_get(url, params, headers, timeout):
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output1": [
                    {
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "hldg_qty": "3",
                        "pchs_avg_pric": "70,000",
                        "pchs_amt": "210,000",
                        "prpr": "72,000",
                        "evlu_amt": "216,000",
                        "evlu_pfls_amt": "6,000",
                        "evlu_pfls_rt": "2.86",
                    },
                    {
                        "pdno": "000000",
                        "prdt_name": "zero",
                        "hldg_qty": "0",
                    },
                ],
                "output2": [{}],
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/account/positions")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    position = body["positions"][0]
    assert position["symbol"] == "005930"
    assert position["name"] == "삼성전자"
    assert position["qty"] == 3.0
    assert position["avg_entry_price"] == 70000.0
    assert position["cost_basis"] == 210000.0
    assert position["current_price"] == 72000.0
    assert position["market_value"] == 216000.0
    assert position["unrealized_pl"] == 6000.0
    assert position["unrealized_plpc"] == pytest.approx(0.0286)


def test_kis_open_orders_endpoint_returns_normalized_pending_orders(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl")
        assert headers["tr_id"] == "TTTC0084R"
        assert params["INQR_DVSN_2"] == "0"
        return _FakeResponse(
            {
                "rt_cd": "0",
                "output": [
                    {
                        "odno": "0000012345",
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "sll_buy_dvsn_name": "매수",
                        "ord_qty": "1",
                        "psbl_qty": "1",
                        "ord_unpr": "71,000",
                        "ord_tmd": "093000",
                    }
                ],
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/account/open-orders")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    order = body["orders"][0]
    assert order["order_id"] == "0000012345"
    assert order["symbol"] == "005930"
    assert order["name"] == "삼성전자"
    assert order["side"] == "buy"
    assert order["qty"] == 1.0
    assert order["unfilled_qty"] == 1.0
    assert order["price"] == 71000.0
    assert order["estimated_amount"] == 71000.0
    assert order["status"] == "pending"
    assert order["submitted_at"] == "09:30:00"


def test_kis_read_only_missing_credentials_returns_safe_400(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_app_key=None, kis_app_secret=None),
    )

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 400
    assert "KIS configuration is incomplete" in response.json()["detail"]


def test_kis_api_error_returns_safe_message_without_token(
    monkeypatch, client, db_session
):
    _add_access_token(db_session, value="secret-error-token")
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

    def fake_get(url, params, headers, timeout):
        return _FakeResponse(
            {
                "rt_cd": "1",
                "msg_cd": "EGW00001",
                "msg1": "bad token secret-error-token",
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "KIS read-only API failed" in detail
    assert "msg_cd=EGW00001" in detail
    assert "msg1=bad token ***" in detail
    assert "tr_id=FHKST01010100" in detail
    assert "secret-error-token" not in response.text


def test_kis_read_only_does_not_call_submit_order(monkeypatch, client, db_session):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.submit_order",
        lambda *args, **kwargs: pytest.fail("read-only endpoint must not submit orders"),
    )

    def fake_get(url, params, headers, timeout):
        return _FakeResponse({"rt_cd": "0", "output": {"stck_prpr": "72000"}})

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 200


def test_kis_read_only_refreshes_expired_token_lazily(
    monkeypatch,
    client,
    db_session,
):
    _add_access_token(
        db_session,
        value="expired-read-token",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    auth_calls = []

    def fake_post(url, data, headers, timeout):
        auth_calls.append(url)
        return _FakeResponse(
            {
                "access_token": "fresh-read-token",
                "expires_in": 3600,
            }
        )

    def fake_get(url, params, headers, timeout):
        assert headers["authorization"] == "Bearer fresh-read-token"
        return _FakeResponse({"rt_cd": "0", "output": {"stck_prpr": "72000"}})

    monkeypatch.setattr("app.brokers.kis_auth_manager.requests.post", fake_post)
    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 200
    assert response.json()["current_price"] == 72000.0
    assert len(auth_calls) == 1
    assert "fresh-read-token" not in response.text


def test_kis_enabled_false_still_allows_read_only_with_valid_credentials(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr(
        "app.routes.kis.get_settings",
        lambda: _settings(kis_enabled=False),
    )

    def fake_get(url, params, headers, timeout):
        return _FakeResponse({"rt_cd": "0", "output": {"stck_prpr": "72000"}})

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    response = client.get("/kis/market/price/005930")

    assert response.status_code == 200
    assert response.json()["current_price"] == 72000.0


def test_brokers_status_still_does_not_expose_secrets(monkeypatch, client, db_session):
    _add_access_token(db_session, value="secret-status-token")
    monkeypatch.setattr("app.routes.brokers.get_settings", lambda: _settings())

    response = client.get("/brokers/status")

    assert response.status_code == 200
    assert response.json()["kis_account_no_masked"] == "12****78"
    assert response.json()["kis_has_access_token"] is True
    assert "12345678" not in response.text
    assert "real-app-key" not in response.text
    assert "real-app-secret" not in response.text
    assert "secret-status-token" not in response.text
