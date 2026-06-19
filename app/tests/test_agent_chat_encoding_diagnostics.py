from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


MOJIBAKE_MARKERS = tuple(chr(code) for code in (0x00EC, 0x00EB, 0x00EA, 0xFFFD))


def test_encoding_diagnostics_endpoint_returns_valid_korean():
    client = TestClient(app)

    response = client.get("/agent/chat/diagnostics/encoding")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "삼성전자" in payload["sample_korean"]
    assert "삼성전자(005930)" in payload["sample_answer"]
    assert payload["sample_unicode_escape"] == r"\uc0bc\uc131\uc804\uc790 \ud604\uc7ac\uac00 \uc870\ud68c"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["real_order_submitted"] is False
    assert payload["safety"]["validation_called"] is False
    assert payload["safety"]["setting_changed"] is False
    assert payload["safety"]["scheduler_changed"] is False

    response_text = json.dumps(payload, ensure_ascii=False)
    assert "삼성전자 현재가 조회" in response_text
    assert not any(marker in response_text for marker in MOJIBAKE_MARKERS)
    assert json.loads(json.dumps(payload, ensure_ascii=False))["sample_korean"] == "삼성전자 현재가 조회"


def test_agent_chat_utf8_debug_scripts_exist():
    root = Path(__file__).resolve().parents[2]

    assert (root / "scripts" / "debug_agent_chat_utf8.ps1").exists()
    assert (root / "scripts" / "debug_agent_chat_utf8.py").exists()
