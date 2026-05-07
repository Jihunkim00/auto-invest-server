from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.brokers.base import KisApiError
from app.config import Settings
from app.core.enums import InternalOrderStatus
from app.db.database import get_db
from app.db.models import BrokerAuthToken, OrderLog
from app.main import app
from app.services.kis_order_mapper import find_kis_order_row, map_kis_order_row
from app.services.kis_order_sync_service import KR_TZ, KisOrderSyncService


def _settings(**overrides):
    values = {
        "alpaca_api_key": "test-key",
        "alpaca_secret_key": "test-secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "kis_enabled": True,
        "kis_env": "prod",
        "kis_app_key": "real-app-key",
        "kis_app_secret": "real-app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_base_url": "https://openapi.koreainvestment.com:9443",
        "kis_access_token": "secret-access-token",
        "kis_approval_key": "secret-approval-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@contextmanager
def _client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _seed_order(
    db_session,
    *,
    broker="kis",
    symbol="005930",
    status=InternalOrderStatus.SUBMITTED.value,
    odno="0001234567",
    qty=3,
    submitted_at=None,
):
    row = OrderLog(
        broker=broker,
        market="KR" if broker == "kis" else "US",
        symbol=symbol,
        side="buy",
        order_type="market",
        time_in_force="day",
        qty=float(qty),
        requested_qty=float(qty),
        remaining_qty=float(qty),
        broker_order_id=odno,
        kis_odno=odno if broker == "kis" else None,
        internal_status=status,
        broker_status="submitted",
        broker_order_status="submitted",
        submitted_at=submitted_at,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def _add_access_token(db_session, value="secret-cached-access-token"):
    row = BrokerAuthToken(
        provider="kis",
        token_type="access_token",
        token_value=value,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        issued_at=datetime.now(UTC),
        environment="prod",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_kis_mapper_maps_full_fill():
    mapped = map_kis_order_row(
        {
            "odno": "0001234567",
            "ord_qty": "3",
            "tot_ccld_qty": "3",
            "rmn_qty": "0",
            "avg_prvs": "72,000",
        }
    )

    assert mapped.internal_status == "FILLED"
    assert mapped.requested_qty == 3
    assert mapped.filled_qty == 3
    assert mapped.remaining_qty == 0
    assert mapped.avg_fill_price == 72000


def test_kis_mapper_maps_partial_fill():
    mapped = map_kis_order_row(
        {
            "odno": "0001234567",
            "ord_qty": "3",
            "tot_ccld_qty": "1",
            "rmn_qty": "2",
            "avg_prvs": "71,500",
        }
    )

    assert mapped.internal_status == "PARTIALLY_FILLED"
    assert mapped.filled_qty == 1
    assert mapped.remaining_qty == 2
    assert mapped.avg_fill_price == 71500


def test_kis_mapper_maps_no_fill_as_accepted():
    mapped = map_kis_order_row(
        {
            "odno": "0001234567",
            "ord_qty": "3",
            "tot_ccld_qty": "0",
            "rmn_qty": "3",
            "ordr_stat_name": "received",
        }
    )

    assert mapped.internal_status == "ACCEPTED"
    assert mapped.filled_qty == 0
    assert mapped.remaining_qty == 3
    assert mapped.avg_fill_price is None


def test_kis_mapper_missing_order_row_returns_none():
    row = find_kis_order_row(
        [
            {
                "odno": "0000000001",
                "ord_qty": "1",
            }
        ],
        "0001234567",
    )

    assert row is None


def test_kis_sync_missing_inquiry_row_marks_unknown_stale(db_session):
    order = _seed_order(db_session)

    class _Client:
        def inquire_daily_order_executions(self, **kwargs):
            return {"orders": [{"odno": "0000000001", "ord_qty": "1"}]}

    synced = KisOrderSyncService(_Client()).sync_order(db_session, order.id)

    assert synced.internal_status == "UNKNOWN_STALE"
    assert synced.sync_error == "kis_order_not_found_in_inquiry"
    assert synced.filled_qty is None


def test_kis_sync_failure_preserves_previous_status_and_records_error(db_session):
    order = _seed_order(db_session, status=InternalOrderStatus.ACCEPTED.value)

    class _Client:
        def inquire_daily_order_executions(self, **kwargs):
            raise RuntimeError("temporary KIS outage")

    synced = KisOrderSyncService(_Client()).sync_order(db_session, order.id)

    assert synced.internal_status == "ACCEPTED"
    assert "temporary KIS outage" in synced.sync_error
    assert synced.last_synced_at is not None
    assert synced.last_sync_payload


def test_kis_sync_first_attempt_uses_submitted_kst_date_without_weekend_buffer(
    db_session,
):
    order = _seed_order(
        db_session,
        symbol="091810",
        odno="0028641600",
        submitted_at=datetime(2026, 5, 4, 4, 10, 24, 698131),
    )
    calls = []

    class _Client:
        def inquire_daily_order_executions(self, *, order_no, start_date, end_date):
            calls.append(
                {
                    "order_no": order_no,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            return {
                "orders": [
                    {
                        "odno": "0028641600",
                        "ord_qty": "3",
                        "tot_ccld_qty": "0",
                        "rmn_qty": "3",
                    }
                ]
            }

    KisOrderSyncService(
        _Client(),
        now_provider=lambda: datetime(2026, 5, 4, 15, 0, tzinfo=KR_TZ),
    ).sync_order(db_session, order.id)

    assert calls == [
        {
            "order_no": "0028641600",
            "start_date": date(2026, 5, 4),
            "end_date": date(2026, 5, 4),
        }
    ]
    assert all(call["start_date"] != date(2026, 5, 3) for call in calls)


def test_kis_date_error_retries_submitted_date_only_without_weekend_buffer(
    db_session,
):
    msg1 = "\uc870\ud68c\uc77c\uc790\ub97c \ud655\uc778\ud558\uc2ed\uc2dc\uc624"
    order = _seed_order(
        db_session,
        symbol="091810",
        odno="0028641600",
        submitted_at=datetime(2026, 5, 4, 4, 10, 24, 698131),
    )
    calls = []

    class _Client:
        def inquire_daily_order_executions(self, *, order_no, start_date, end_date):
            calls.append(
                {
                    "order_no": order_no,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            raise KisApiError(
                "KIS read-only API failed: msg_cd=KIER2570, "
                f"msg1={msg1}, tr_id=TTTC8001R",
                details={
                    "rt_cd": "7",
                    "msg_cd": "KIER2570",
                    "msg1": msg1,
                    "tr_id": "TTTC8001R",
                    "path": "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                    "params": {
                        "ODNO": order_no,
                        "INQR_STRT_DT": start_date.strftime("%Y%m%d"),
                        "INQR_END_DT": end_date.strftime("%Y%m%d"),
                        "CANO": "12345678",
                        "appsecret": "real-app-secret",
                        "access_token": "secret-access-token",
                    },
                },
            )

    synced = KisOrderSyncService(
        _Client(),
        now_provider=lambda: datetime(2026, 5, 5, 9, 30, tzinfo=KR_TZ),
    ).sync_order(db_session, order.id)

    assert synced.internal_status == "SUBMITTED"
    assert "KIER2570" in synced.sync_error
    assert calls == [
        {
            "order_no": "0028641600",
            "start_date": date(2026, 5, 4),
            "end_date": date(2026, 5, 5),
        },
        {
            "order_no": "0028641600",
            "start_date": date(2026, 5, 4),
            "end_date": date(2026, 5, 4),
        },
    ]
    assert all(call["start_date"] != date(2026, 5, 3) for call in calls)

    payload = json.loads(synced.last_sync_payload)
    assert payload["first_attempt"]["params"]["INQR_STRT_DT"] == "20260504"
    assert payload["first_attempt"]["params"]["INQR_END_DT"] == "20260505"
    assert payload["fallback_attempt"]["params"]["INQR_STRT_DT"] == "20260504"
    assert payload["fallback_attempt"]["params"]["INQR_END_DT"] == "20260504"
    assert payload["final_error"]["msg_cd"] == "KIER2570"
    assert payload["final_error"]["msg1"] == msg1
    assert payload["final_error"]["rt_cd"] == "7"
    assert payload["final_error"]["tr_id"] == "TTTC8001R"

    combined = synced.sync_error + synced.last_sync_payload
    assert "20260503" not in combined
    assert "12345678" not in combined
    assert "real-app-secret" not in combined
    assert "secret-access-token" not in combined


def test_kis_sync_success_sanitizes_raw_payload_and_preserves_fill_mapping(
    db_session,
):
    order = _seed_order(
        db_session,
        symbol="091810",
        odno="0028641600",
        qty=3,
        submitted_at=datetime(2026, 5, 4, 4, 10, 24, 698131),
    )
    row = {
        "ord_dt": "20260504",
        "odno": "0028641600",
        "orgn_odno": "",
        "ord_dvsn_name": "market",
        "sll_buy_dvsn_cd": "02",
        "sll_buy_dvsn_cd_name": "buy",
        "pdno": "091810",
        "prdt_name": "TiumBio",
        "ord_qty": "3",
        "tot_ccld_qty": "3",
        "avg_prvs": "914",
        "tot_ccld_amt": "2742",
        "rmn_qty": "0",
        "rjct_qty": "0",
        "cncl_yn": "N",
        "excg_id_dvsn_cd": "KRX",
        "ctac_tlno": "010-1234-5678",
        "inqr_ip_addr": "203.0.113.24",
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "appkey": "real-app-key",
        "authorization": "Bearer secret-access-token",
        "memo": "contact 010-9999-8888 for account 87654321",
    }

    class _Client:
        def inquire_daily_order_executions(self, **kwargs):
            return {
                "orders": [row],
                "raw": {
                    "output1": [row],
                    "ctac_tlno": "010-2222-3333",
                    "inqr_ip_addr": "198.51.100.10",
                },
            }

    synced = KisOrderSyncService(
        _Client(),
        now_provider=lambda: datetime(2026, 5, 4, 15, 0, tzinfo=KR_TZ),
    ).sync_order(db_session, order.id)

    assert synced.internal_status == "FILLED"
    assert synced.filled_qty == 3
    assert synced.remaining_qty == 0
    assert synced.avg_fill_price == 914

    payload = json.loads(synced.last_sync_payload)
    matched = payload["matched_order"]
    inquiry_order = payload["inquiry"]["orders"][0]

    for item in (matched, inquiry_order):
        assert item["ctac_tlno"] == "***REDACTED***"
        assert item["inqr_ip_addr"] == "***REDACTED***"
        assert item["CANO"] == "12****78"
        assert item["ACNT_PRDT_CD"] == "***REDACTED***"
        assert item["appkey"] == "***"
        assert item["authorization"] == "***"
        assert item["ord_dt"] == "20260504"
        assert item["odno"] == "0028641600"
        assert item["orgn_odno"] == ""
        assert item["ord_dvsn_name"] == "market"
        assert item["sll_buy_dvsn_cd"] == "02"
        assert item["sll_buy_dvsn_cd_name"] == "buy"
        assert item["pdno"] == "091810"
        assert item["prdt_name"] == "TiumBio"
        assert item["ord_qty"] == "3"
        assert item["tot_ccld_qty"] == "3"
        assert item["avg_prvs"] == "914"
        assert item["tot_ccld_amt"] == "2742"
        assert item["rmn_qty"] == "0"
        assert item["rjct_qty"] == "0"
        assert item["cncl_yn"] == "N"
        assert item["excg_id_dvsn_cd"] == "KRX"

    combined = synced.last_sync_payload
    assert "010-1234-5678" not in combined
    assert "010-9999-8888" not in combined
    assert "010-2222-3333" not in combined
    assert "203.0.113.24" not in combined
    assert "198.51.100.10" not in combined
    assert "12345678" not in combined
    assert "87654321" not in combined
    assert "real-app-key" not in combined
    assert "secret-access-token" not in combined


def test_kis_sync_failure_stores_sanitized_kis_api_diagnostics(
    monkeypatch,
    db_session,
):
    _add_access_token(db_session)
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(
        db_session,
        symbol="091810",
        odno="0028641600",
        status=InternalOrderStatus.SUBMITTED.value,
    )

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/uapi/domestic-stock/v1/trading/inquire-daily-ccld")
        assert headers["tr_id"] == "TTTC8001R"
        assert params["ODNO"] == "0028641600"
        assert params["INQR_STRT_DT"]
        assert params["INQR_END_DT"]
        return _FakeResponse(
            {
                "rt_cd": "1",
                "msg_cd": "KIER2570",
                "msg1": (
                    "diagnostic for account 12345678 app real-app-key "
                    "secret real-app-secret token secret-access-token "
                    "phone 010-1234-5678 ip 203.0.113.24"
                ),
            }
        )

    monkeypatch.setattr("app.brokers.kis_client.requests.get", fake_get)

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["internal_status"] == "SUBMITTED"
    assert "KIER2570" in body["sync_error"]
    assert "msg1=diagnostic" in body["sync_error"]
    assert "tr_id=TTTC8001R" in body["sync_error"]

    synced = db_session.get(OrderLog, order.id)
    payload = json.loads(synced.last_sync_payload)
    assert payload["event"] == "kis_order_sync_failed"
    assert payload["order"]["symbol"] == "091810"
    assert payload["order"]["side"] == "buy"
    assert payload["order"]["kis_odno"] == "0028641600"
    assert payload["request"]["ODNO"] == "0028641600"
    assert payload["request"]["INQR_STRT_DT"]
    assert payload["request"]["INQR_END_DT"]
    assert payload["kis_error"]["msg_cd"] == "KIER2570"
    assert payload["kis_error"]["msg1"]
    assert payload["kis_error"]["tr_id"] == "TTTC8001R"
    assert payload["kis_error"]["path"].endswith("/inquire-daily-ccld")
    assert payload["kis_error"]["params"]["ODNO"] == "0028641600"
    assert payload["kis_error"]["params"]["CANO"] == "12****78"
    assert payload["kis_error"]["params"]["ACNT_PRDT_CD"] == "***REDACTED***"
    assert payload["kis_error"]["environment"] == "prod"
    assert payload["kis_error"]["is_virtual"] is False

    combined = body["sync_error"] + synced.last_sync_payload
    assert "12345678" not in combined
    assert "real-app-key" not in combined
    assert "real-app-secret" not in combined
    assert "secret-access-token" not in combined
    assert "secret-cached-access-token" not in combined
    assert "secret-approval-key" not in combined
    assert "010-1234-5678" not in combined
    assert "203.0.113.24" not in combined


def test_kis_sync_single_order_route_updates_local_status(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, qty=3)

    def fake_inquire(self, *, order_no, start_date, end_date):
        assert order_no == "0001234567"
        return {
            "orders": [
                {
                    "odno": "0001234567",
                    "ord_qty": "3",
                    "tot_ccld_qty": "1",
                    "rmn_qty": "2",
                    "avg_prvs": "71,500",
                    "ctac_tlno": "010-1234-5678",
                    "inqr_ip_addr": "203.0.113.24",
                }
            ]
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.inquire_daily_order_executions",
        fake_inquire,
    )

    with _client(db_session) as client:
        response = client.post(f"/kis/orders/{order.id}/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == order.id
    assert body["kis_odno"] == "0001234567"
    assert body["internal_status"] == "PARTIALLY_FILLED"
    assert body["filled_qty"] == 1
    assert body["remaining_qty"] == 2
    assert body["avg_fill_price"] == 71500
    assert body["last_synced_at"] is not None
    assert body["sync_error"] is None
    assert "last_sync_payload" not in body
    assert "010-1234-5678" not in response.text
    assert "203.0.113.24" not in response.text


def test_kis_sync_open_route_syncs_only_open_kis_orders(
    monkeypatch,
    db_session,
):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    kis_open = _seed_order(db_session, odno="0000000001")
    _seed_order(db_session, broker="alpaca", symbol="AAPL", odno="alpaca-1")
    _seed_order(
        db_session,
        status=InternalOrderStatus.FILLED.value,
        odno="0000000002",
    )
    calls = []

    def fake_inquire(self, *, order_no, start_date, end_date):
        calls.append(order_no)
        return {
            "orders": [
                {
                    "odno": order_no,
                    "ord_qty": "3",
                    "tot_ccld_qty": "3",
                    "rmn_qty": "0",
                    "avg_prvs": "72,000",
                }
            ]
        }

    monkeypatch.setattr(
        "app.brokers.kis_client.KisClient.inquire_daily_order_executions",
        fake_inquire,
    )

    with _client(db_session) as client:
        response = client.post("/kis/orders/sync-open")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["orders"][0]["order_id"] == kis_open.id
    assert body["orders"][0]["internal_status"] == "FILLED"
    assert calls == ["0000000001"]


def test_kis_orders_route_returns_recent_kis_orders_only(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    kis_order = _seed_order(db_session, odno="0000000001")
    _seed_order(db_session, broker="alpaca", symbol="AAPL", odno="alpaca-1")

    with _client(db_session) as client:
        response = client.get("/kis/orders")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["orders"][0]["order_id"] == kis_order.id
    assert body["orders"][0]["broker"] == "kis"


def test_kis_orders_route_excludes_safety_rejected_by_default(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    _seed_order(db_session, odno="0000000001", status=InternalOrderStatus.SUBMITTED.value)
    _seed_order(db_session, odno="0000000002", status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value)

    with _client(db_session) as client:
        response = client.get("/kis/orders")
    assert response.status_code == 200
    statuses = [row["internal_status"] for row in response.json()["orders"]]
    assert "REJECTED_BY_SAFETY_GATE" not in statuses


def test_kis_orders_route_can_include_safety_rejected(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    _seed_order(db_session, odno="0000000001", status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value)

    with _client(db_session) as client:
        response = client.get("/kis/orders?include_rejected=true")
    assert response.status_code == 200
    statuses = [row["internal_status"] for row in response.json()["orders"]]
    assert "REJECTED_BY_SAFETY_GATE" in statuses


def test_kis_order_detail_hides_payload_by_default(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, odno="0000000001")
    order.last_sync_payload = json.dumps({"ctac_tlno": "010-1234-5678"})
    db_session.commit()
    with _client(db_session) as client:
        response = client.get(f"/kis/orders/{order.id}")
    assert response.status_code == 200
    assert "last_sync_payload" not in response.json()


def test_kis_order_detail_includes_sanitized_payload(monkeypatch, db_session):
    monkeypatch.setattr("app.routes.kis.get_settings", lambda: _settings())
    order = _seed_order(db_session, odno="0000000001")
    order.last_sync_payload = json.dumps(
        {"ctac_tlno": "010-1234-5678", "inqr_ip_addr": "203.0.113.24", "CANO": "12345678"}
    )
    db_session.commit()
    with _client(db_session) as client:
        response = client.get(f"/kis/orders/{order.id}?include_sync_payload=true")
    assert response.status_code == 200
    body = response.json()
    payload = body["last_sync_payload"]
    assert payload["ctac_tlno"] == "***REDACTED***"
    assert payload["inqr_ip_addr"] == "***REDACTED***"
    assert payload["CANO"] != "12345678"


def test_kis_order_summary_route_returns_zero_counts(db_session):
    with _client(db_session) as client:
        response = client.get("/kis/orders/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "kis"
    assert body["open_orders"] == 0
    assert body["filled_today"] == 0
    assert body["canceled_today"] == 0
    assert body["rejected_today"] == 0
    assert body["last_order_at"] is None


def test_kis_order_summary_route_counts_today_and_ignores_alpaca(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    older = now - timedelta(days=1)

    open_order = _seed_order(
        db_session,
        status=InternalOrderStatus.SUBMITTED.value,
        odno="0000000101",
    )
    filled = _seed_order(
        db_session,
        status=InternalOrderStatus.FILLED.value,
        odno="0000000102",
    )
    canceled = _seed_order(
        db_session,
        status=InternalOrderStatus.CANCELED.value,
        odno="0000000103",
    )
    rejected = _seed_order(
        db_session,
        status=InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
        odno="0000000104",
    )
    old_filled = _seed_order(
        db_session,
        status=InternalOrderStatus.FILLED.value,
        odno="0000000105",
    )
    _seed_order(
        db_session,
        broker="alpaca",
        symbol="AAPL",
        status=InternalOrderStatus.FILLED.value,
        odno="alpaca-summary-1",
    )

    open_order.created_at = now
    filled.created_at = now - timedelta(minutes=4)
    filled.filled_at = now - timedelta(minutes=3)
    canceled.created_at = now - timedelta(minutes=2)
    canceled.canceled_at = now - timedelta(minutes=2)
    rejected.created_at = now - timedelta(minutes=1)
    old_filled.created_at = older
    old_filled.filled_at = older
    db_session.commit()

    with _client(db_session) as client:
        response = client.get("/kis/orders/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["open_orders"] == 1
    assert body["filled_today"] == 1
    assert body["canceled_today"] == 1
    assert body["rejected_today"] == 1
    assert body["last_order_at"] == now.isoformat()
