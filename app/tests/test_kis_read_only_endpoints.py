from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
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


def test_kis_price_endpoint_returns_normalized_current_price(
    monkeypatch, client, db_session
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())

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
    assert response.json()["detail"] == "KIS read-only API returned error code EGW00001."
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
