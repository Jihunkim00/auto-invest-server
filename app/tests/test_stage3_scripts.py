from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_trend_builder_defaults_keep_conservative_notional(monkeypatch):
    monkeypatch.delenv("STAGE3_MAX_NOTIONAL_KRW", raising=False)
    monkeypatch.delenv("STAGE3_MAX_NOTIONAL_PCT", raising=False)
    script = _load_script("stage3_build_trend_watchlist.py")

    config = script.parse_args([])

    assert config.max_notional_krw == 50000.0
    assert config.max_notional_pct == 0.80


def test_trend_builder_uses_double_notional_limit():
    script = _load_script("stage3_build_trend_watchlist.py")

    max_notional = script.calculate_max_notional(
        configured_max_notional_krw=55000,
        configured_max_notional_pct=0.94,
        equity=100000,
        cash=90000,
    )

    assert max_notional == 55000


def test_trend_checks_require_one_share_cash_and_technical_pass():
    script = _load_script("stage3_build_trend_watchlist.py")

    checks, expected_qty, estimated_notional = script.build_candidate_checks(
        current_price=52000,
        ema20=51000,
        ema50=50000,
        vwap=51500,
        short_momentum=0.01,
        max_notional=55000,
        cash=60000,
    )

    assert expected_qty == 1
    assert estimated_notional == 52000
    assert all(checks.values())


def test_trend_checks_reject_two_share_candidate():
    script = _load_script("stage3_build_trend_watchlist.py")

    checks, expected_qty, _ = script.build_candidate_checks(
        current_price=25000,
        ema20=24000,
        ema50=23000,
        vwap=24500,
        short_momentum=0.01,
        max_notional=55000,
        cash=60000,
    )

    assert expected_qty == 2
    assert checks["one_share_quantity"] is False


def test_source_universe_requires_100_unique_symbols(tmp_path):
    script = _load_script("stage3_build_trend_watchlist.py")
    path = tmp_path / "universe.yaml"
    symbols = [
        {"symbol": f"{index:06d}", "name": f"name{index}", "market": "KOSPI"}
        for index in range(100)
    ]
    path.write_text(
        "symbols:\n"
        + "\n".join(
            f"- symbol: '{item['symbol']}'\n"
            f"  name: {item['name']}\n"
            f"  market: {item['market']}"
            for item in symbols
        ),
        encoding="utf-8",
    )

    loaded, summary = script.load_source_symbols(path, required_count=100)

    assert len(loaded) == 100
    assert summary["source_symbol_count"] == 100


def test_trend_report_sanitizes_nested_non_finite_values(tmp_path):
    script = _load_script("stage3_build_trend_watchlist.py")
    path = tmp_path / "report.json"

    script.write_json(
        path,
        {
            "top": float("nan"),
            "nested": {
                "items": [
                    float("inf"),
                    {"value": float("-inf")},
                ],
            },
        },
    )

    text = path.read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "Infinity" not in text
    parsed = json.loads(text)
    assert parsed["top"] is None
    assert parsed["nested"]["items"] == [None, {"value": None}]


def test_trend_builder_report_path_writes_exact_file(monkeypatch, tmp_path):
    script = _load_script("stage3_build_trend_watchlist.py")
    source = tmp_path / "source.yaml"
    target = tmp_path / "target.yaml"
    report_dir = tmp_path / "reports"
    report_path = tmp_path / "exact" / "technical.json"
    source.write_text(
        "symbols:\n- symbol: '005930'\n  name: Samsung\n  market: KR\n",
        encoding="utf-8",
    )
    target.write_text("symbols: []\n", encoding="utf-8")

    class FakeIndicatorService:
        def calculate(self, bars):
            return {
                "ema20": 50_000,
                "ema50": 49_000,
                "vwap": 51_000,
                "short_momentum": 0.01,
                "volume_ratio": float("inf"),
                "rsi": 55,
                "nested": {"bad": float("nan")},
            }

    def fake_api_get(path, *, base_url):
        if path == "/kis/account/balance":
            return {"cash": 100_000, "total_asset_value": 100_000}
        if path.startswith("/kis/market/bars/"):
            return {"bars": [{} for _ in range(script.MIN_REQUIRED_BARS)]}
        if path.startswith("/kis/market/price/"):
            return {"current_price": 52_000, "name": "Samsung"}
        raise AssertionError(path)

    monkeypatch.setattr(script, "IndicatorService", FakeIndicatorService)
    monkeypatch.setattr(script, "api_get", fake_api_get)

    result = script.build_trend_watchlist(
        script.TrendBuildConfig(
            base_url="http://test",
            source_watchlist=source,
            target_watchlist=target,
            report_dir=report_dir,
            report_path=report_path,
            max_notional_krw=55_000,
            max_notional_pct=0.94,
            max_candidates=1,
            required_source_count=1,
            check_source_only=False,
        )
    )

    assert result == 0
    assert report_path.exists()
    assert not list(report_dir.glob("trend_watchlist_report_*.json"))
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["all_results"][0]["volume_ratio"] is None


def test_universe_builder_price_range_for_one_share():
    script = _load_script("stage3_build_universe100.py")

    minimum, maximum = script.one_share_price_range(55000)

    assert minimum == 27501
    assert maximum == 55000
    assert int(55000 // minimum) == 1
    assert int(55000 // (minimum - 1)) == 2


def test_scheduled_check_uses_only_allowed_submit_free_endpoints():
    text = (ROOT / "scripts" / "stage3_scheduled_check.ps1").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "POST " + "/kis/limited-auto-buy/" + "run-once",
        "POST " + "/kis/orders/" + "manual-submit",
        "/kis/limited-auto-buy/" + "run-once",
        "/kis/orders/" + "manual-submit",
        "/kis/orders/" + "submit-manual",
        "/kis/limited-auto-buy/" + "execute-reviewed-once",
        "submit" + "_order",
        "submit" + "_manual",
    ]
    for pattern in forbidden:
        assert pattern not in text

    assert "/kis/watchlist/preview" in text
    assert "/kis/limited-auto-buy/preflight-once" in text
    assert "/ops/settings" in text


def test_scheduled_check_uses_exact_report_path_and_no_glob():
    text = (ROOT / "scripts" / "stage3_scheduled_check.ps1").read_text(
        encoding="utf-8"
    )

    assert "--report-path" in text
    assert "$reportPath" in text
    assert 'Get-ChildItem -Path $LogDir -Filter "trend_watchlist_report_*.json"' not in text


def test_scheduled_check_holds_on_report_parse_failure_and_restores_safe(tmp_path):
    root = tmp_path / "root"
    scripts_dir = root / "scripts"
    config_dir = root / "config"
    log_dir = root / "logs"
    scripts_dir.mkdir(parents=True)
    config_dir.mkdir()
    (config_dir / "watchlist_kr.stage3.universe100.yaml").write_text(
        "symbols: []\n",
        encoding="utf-8",
    )
    (config_dir / "watchlist_kr.yaml").write_text("symbols: []\n", encoding="utf-8")
    fake_builder = scripts_dir / "stage3_build_trend_watchlist.py"
    fake_builder.write_text(
        "from pathlib import Path\n"
        "import json, sys\n"
        "if '--check-source-only' in sys.argv:\n"
        "    print(json.dumps({'source_symbol_count': 100}))\n"
        "    raise SystemExit(0)\n"
        "path = Path(sys.argv[sys.argv.index('--report-path') + 1])\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text('{', encoding='utf-8')\n"
        "print(f'Report: {path}')\n",
        encoding="utf-8",
    )

    calls: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            length = int(self.headers.get("content-length") or "0")
            body = self.rfile.read(length).decode("utf-8")
            calls.append((self.path, body))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def do_POST(self):
            calls.append((self.path, ""))
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"unexpected")

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "stage3_scheduled_check.ps1"),
                "-Root",
                str(root),
                "-BaseUrl",
                f"http://127.0.0.1:{server.server_port}",
                "-Python",
                sys.executable,
                "-Slot",
                "test_slot",
                "-LogDir",
                str(log_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr
    log_text = "\n".join(path.read_text(encoding="utf-8") for path in log_dir.glob("*.log"))
    assert "technical_report_parse_failed=true" in log_text
    assert "preflight_executed=false" in log_text
    assert "HOLD: technical report unavailable" in log_text
    assert "safe settings restored" in log_text
    assert "max_notional_krw=55000" in log_text
    assert not any(path.startswith("/kis/watchlist/preview") for path, _ in calls)
    assert not any(path.startswith("/kis/limited-auto-buy/preflight-once") for path, _ in calls)
    assert calls[-1][0] == "/ops/settings"
    restored = json.loads(calls[-1][1])
    assert restored["dry_run"] is True
    assert restored["kill_switch"] is True
    assert restored["kis_limited_auto_buy_max_notional_krw"] == 50000.0
    assert restored["kis_limited_auto_buy_max_notional_pct"] == 0.80


def test_scheduled_check_separates_live_test_cap_from_safe_restore():
    text = (ROOT / "scripts" / "stage3_scheduled_check.ps1").read_text(
        encoding="utf-8"
    )

    assert "$MaxNotionalKrw = 55000.0" in text
    assert "kis_limited_auto_buy_max_notional_krw = 50000.0" in text
    assert (
        '$PreflightSettings["kis_limited_auto_buy_max_notional_krw"] = '
        "[Double]$MaxNotionalKrw"
    ) in text
