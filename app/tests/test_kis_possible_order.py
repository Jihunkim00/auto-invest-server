from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.brokers.base import KisApiError
from app.brokers.kis_client import (
    KIS_POSSIBLE_ORDER_PATH,
    KIS_POSSIBLE_ORDER_TR_ID_REAL,
    KisClient,
)
from app.db.database import get_db
from app.main import app


def _client():
    client = KisClient.__new__(KisClient)
    client.settings = SimpleNamespace(
        kis_env="prod",
        kis_account_no="12345678",
        kis_account_product_code="01",
    )
    return client


def test_possible_order_uses_official_market_params_and_parses_cash_qty():
    client = _client()
    calls = []

    def request_get(path, *, tr_id, params):
        calls.append((path, tr_id, params))
        return {
            "rt_cd": "0",
            "output": {
                "ord_psbl_cash": "1,001,456",
                "nrcvb_buy_amt": "996,274",
                "nrcvb_buy_qty": "25",
                "ruse_psbl_amt": "960,737",
            },
        }

    client.request_get = request_get

    result = client.get_domestic_possible_order(
        symbol="001450",
        order_type="market",
        order_price=38_650,
    )

    assert result["raw_status"] == "ok"
    assert result["orderable_cash"] == 996_274
    assert result["orderable_cash_field"] == "nrcvb_buy_amt"
    assert result["orderable_quantity"] == 25
    assert result["reference_price"] == 38_650
    assert calls == [
        (
            KIS_POSSIBLE_ORDER_PATH,
            KIS_POSSIBLE_ORDER_TR_ID_REAL,
            {
                "CANO": "12345678",
                "ACNT_PRDT_CD": "01",
                "PDNO": "001450",
                "ORD_UNPR": "",
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N",
            },
        )
    ]


def test_possible_order_preserves_real_zero_and_missing_as_distinct():
    client = _client()
    client.request_get = lambda *args, **kwargs: {
        "rt_cd": "0",
        "output": {"nrcvb_buy_amt": "0", "nrcvb_buy_qty": "0"},
    }
    zero = client.get_domestic_possible_order(symbol="001450")
    assert zero["orderable_cash"] == 0
    assert zero["orderable_quantity"] == 0

    client.request_get = lambda *args, **kwargs: {"rt_cd": "0", "output": {}}
    missing = client.get_domestic_possible_order(symbol="001450")
    assert missing["orderable_cash"] is None
    assert missing["orderable_quantity"] is None


def test_possible_order_error_is_fail_closed_without_submit():
    client = _client()

    def fail(*args, **kwargs):
        raise KisApiError("KIS API failed", details={"msg_cd": "EGW00123"})

    client.request_get = fail
    result = client.get_domestic_possible_order(symbol="001450")

    assert result["raw_status"] == "error"
    assert result["orderable_cash"] is None
    assert result["orderable_quantity"] is None
    assert result["error"]


def test_possible_order_read_only_route(monkeypatch, db_session):
    client = _client()
    calls = []

    def possible(**kwargs):
        calls.append(kwargs)
        return {
            "raw_status": "ok",
            "symbol": kwargs["symbol"],
            "orderable_cash": 996_274,
            "orderable_quantity": 25,
            "real_order_submitted": False,
            "broker_submit_called": False,
        }

    client.get_domestic_possible_order = possible
    monkeypatch.setattr("app.routes.kis._client", lambda db: client)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get(
            "/kis/account/possible-order?symbol=001450&order_type=market&price=38650"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["orderable_cash"] == 996_274
    assert response.json()["real_order_submitted"] is False
    assert calls[0]["symbol"] == "001450"