from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Agent Chat UTF-8 rendering.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    diagnostics = _get_json(f"{base_url}/agent/chat/diagnostics/encoding")
    print(f"diagnostics.status={diagnostics.get('status')}")
    print(f"diagnostics.sample_korean={diagnostics.get('sample_korean')}")
    print(f"diagnostics.sample_unicode_escape={diagnostics.get('sample_unicode_escape')}")

    response = _post_json(
        f"{base_url}/agent/chat/send",
        {
            "conversation_key": None,
            "message": "\uC0BC\uC131\uC804\uC790 \uD604\uC7AC\uAC00 \uC5BC\uB9C8\uC57C?",
            "context": {
                "default_market": "KR",
                "default_provider": "kis",
                "timezone": "Asia/Seoul",
            },
            "auto_create_conversation": True,
        },
    )
    answer = ((response.get("answer") or {}).get("text") or "")
    safety = response.get("safety") or {}
    chat_diagnostics = response.get("diagnostics") or {}
    print(f"intent.category={(response.get('intent') or {}).get('category')}")
    print(f"intent.symbol={(response.get('intent') or {}).get('symbol')}")
    print(f"answer.text={answer}")
    print(f"answer.text.unicode_escape={answer.encode('unicode_escape').decode('ascii')}")
    print(f"safety.real_order_submitted={safety.get('real_order_submitted')}")
    print(f"safety.validation_called={safety.get('validation_called')}")
    print(f"safety.setting_changed={safety.get('setting_changed')}")
    print(f"safety.scheduler_changed={safety.get('scheduler_changed')}")
    print(f"diagnostics.encoding_safe={chat_diagnostics.get('encoding_safe')}")


if __name__ == "__main__":
    main()
