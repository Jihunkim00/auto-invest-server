from __future__ import annotations

from datetime import UTC, datetime, timedelta
import types
import time

import pytest

from app.brokers.kis_client import KisClient
from app.brokers.base import KisApiError
from app.services.kis_account_state_cache_service import KisAccountStateCacheService


class DummySettings(types.SimpleNamespace):
    pass


class DummyResponse:
    def __init__(self, data, status_code=200, text=None):
        self._data = data
        self.status_code = status_code
        self.text = text or str(data)

    def json(self):
        return self._data


def test_egw00201_maps_to_kis_rate_limited(monkeypatch):
    # Build a KisClient but bypass auth headers
    client = KisClient()
    monkeypatch.setattr(client, "build_headers", lambda *args, **kwargs: {})

    # Simulate KIS returning EGW00201 payload
    def fake_get(url, params=None, headers=None, timeout=None):
        return DummyResponse({"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "원장에서 허용 가능한 초당 거래건수를 초과하였습니다."}, status_code=200)

    monkeypatch.setattr("requests.get", fake_get)

    with pytest.raises(KisApiError) as excinfo:
        client.request_get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=client._balance_tr_id())

    details = getattr(excinfo.value, "details", {}) or {}
    assert details.get("kis_rate_limited") is True or details.get("reason") == "kis_rate_limited"


def test_account_state_cache_hit_and_ttl_and_fallback(monkeypatch):
    # Create dummy client that counts calls
    class CountClient:
        def __init__(self):
            self.settings = DummySettings(kis_account_state_cache_ttl_seconds=2.0, kis_account_state_max_stale_seconds=5.0)
            self.balance_calls = 0
            self.open_orders_calls = 0

        def _request_balance(self):
            self.balance_calls += 1
            return {"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "2000000"}], "output1": [{"pdno": "005930", "hldg_qty": "1", "prpr": "96000", "pchs_avg_pric": "100000"}]}

        def list_open_orders(self):
            self.open_orders_calls += 1
            return []

    client = CountClient()
    svc = KisAccountStateCacheService.get_or_create(client)

    # first fetch: fresh
    s1 = svc.get_account_state()
    assert s1["source"] == "fresh"
    assert client.balance_calls == 1

    # second fetch within TTL -> cache hit (no new balance call)
    s2 = svc.get_account_state()
    assert s2["source"] == "cache"
    assert client.balance_calls == 1

    # force TTL expiry by requiring a fresh fetch
    client.settings.kis_account_state_cache_ttl_seconds = 0.0
    s3 = svc.get_account_state(require_fresh=True)
    assert s3["source"] == "fresh"
    assert client.balance_calls == 2


def test_rate_limit_with_recent_cache_uses_cache_after_rate_limit(monkeypatch):
    class Client:
        def __init__(self):
            self.settings = DummySettings(kis_account_state_cache_ttl_seconds=2.0, kis_account_state_max_stale_seconds=5.0)
            self.balance_calls = 0

        def _request_balance(self):
            self.balance_calls += 1
            # First call returns good data
            if self.balance_calls == 1:
                return {"output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "2000000"}], "output1": [{"pdno": "005930", "hldg_qty": "1", "prpr": "96000", "pchs_avg_pric": "100000"}]}
            # Subsequent calls simulate rate limit via KisApiError details produced by client layer
            raise KisApiError("rate limited", details={"kis_rate_limited": True})

        def list_open_orders(self):
            return []

    client = Client()
    svc = KisAccountStateCacheService.get_or_create(client)

    first = svc.get_account_state()
    assert first["source"] == "fresh"

    # Now a rate limit occurs; force a fresh fetch so the rate-limit is triggered
    second = svc.get_account_state(require_fresh=True)
    assert second.get("source") in ("cache_after_rate_limit", "cache")
    assert second.get("rate_limited") is True or "kis_rate_limited" in second.get("warnings", [])


def test_rate_limit_no_cache_blocks_live_sell(monkeypatch, db_session):
    # Client that always rate limits
    class RLClient:
        def __init__(self):
            self.settings = DummySettings(kis_account_state_cache_ttl_seconds=2.0, kis_account_state_max_stale_seconds=5.0)

        def _request_balance(self):
            raise KisApiError("rate limited", details={"kis_rate_limited": True})

        def list_open_orders(self):
            raise KisApiError("rate limited", details={"kis_rate_limited": True})

        def list_positions(self):
            raise KisApiError("rate limited", details={"kis_rate_limited": True})

    from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService

    client = RLClient()
    service = KisLimitedAutoSellService(client, session_service=None)
    # run_once should handle rate limit and block
    result = service.run_once(db_session)
    # blocked due to rate limit
    assert result["result"] == "blocked"
    assert "kis_rate_limited" in result["block_reasons"] or result["reason"] == "kis_rate_limited"
