from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.responses import JSONResponse

from app.brokers.kis_client import KisClient


def test_kis_price_response_preserves_utf8_korean_name():
    client = KisClient.__new__(KisClient)
    client.settings = SimpleNamespace(kis_env="prod")
    client.request_get = lambda *args, **kwargs: {
        "rt_cd": "0",
        "output": {
            "hts_kor_isnm": "삼성전자",
            "stck_prpr": "70,000",
        },
    }

    result = client.get_domestic_stock_price("005930")
    encoded = JSONResponse(result).body.decode("utf-8")
    decoded = json.loads(encoded)

    assert result["name"] == "삼성전자"
    assert decoded["name"] == "삼성전자"
    assert "\ufffd" not in encoded