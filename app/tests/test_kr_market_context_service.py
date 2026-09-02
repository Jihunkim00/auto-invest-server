import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.brokers.kis_client import (
    KIS_DOMESTIC_QUOTE_MARKET_CODE,
    KIS_FX_MARKET_DIVISION,
    KIS_INVESTOR_DAILY_BY_MARKET_PATH,
    KIS_INVESTOR_DAILY_BY_MARKET_TR_ID,
    KIS_USDKRW_IDENTIFIER_NAME,
    KIS_USDKRW_ISCD,
    KisClient,
)
from app.services.kr_market_context_service import KrMarketContextService
from app.services.kis_watchlist_preview_service import KisPreviewGptAdvisor


AS_OF = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


class FakeKis:
    settings = SimpleNamespace(kis_enabled=True)

    def get_usdkrw_daily_chart(self, *, as_of=None, limit=5):
        return [
            {
                "symbol": KIS_USDKRW_ISCD,
                "date": "2026-09-01",
                "close": 1380.0,
                "previous_close": 1365.0,
            }
        ]

    def get_domestic_index_daily_bars(self, index_code, *, as_of=None, limit=5):
        close = 2700.0 if index_code == "0001" else 900.0
        return [
            {
                "date": "2026-09-01",
                "close": close,
                "previous_close": close - 27.0,
            }
        ]
    def get_domestic_stock_price(self, symbol):
        return {
            "symbol": symbol,
            "current_price": 100.0,
            "previous_close": 99.0,
        }

    def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
        return {
            "stck_bsop_date": "20260902",
            "market": market,
            "market_code": "KSP" if market == "KOSPI" else "KSQ",
            "scope": "market_wide",
            "frgn_ntby_tr_pbmn": 100.0 if market == "KOSPI" else 25.0,
            "orgn_ntby_tr_pbmn": -50.0 if market == "KOSPI" else 50.0,
        }

    def get_domestic_news_titles(self, symbol, *, as_of=None, limit=5):
        return [
            {
                "title": f"{symbol} disclosure {index}",
                "published_at": f"2026-09-0{index + 1}",
                "source": "KIS",
            }
            for index in range(7)
        ]


class FakeAlpaca:
    def get_recent_bars(self, symbol, *, limit=5, timeframe="1Day"):
        close = {
            "SPY": 102.0,
            "QQQ": 103.0,
            "DIA": 104.0,
            "SMH": 105.0,
        }[symbol]
        return [
            SimpleNamespace(
                timestamp=datetime(2026, 9, 1, 20, 0, tzinfo=UTC),
                close=100.0,
            ),
            SimpleNamespace(
                timestamp=datetime(2026, 9, 2, 20, 0, tzinfo=UTC),
                close=close,
            ),
        ]


def _quotes():
    return {
        "KOSPI-A": {"current_price": 110.0, "previous_close": 100.0},
        "KOSPI-B": {"current_price": 90.0, "previous_close": 100.0},
        "KOSPI-C": {"current_price": 100.0, "previous_close": 100.0},
        "KOSDAQ-A": {"current_price": 110.0, "previous_close": 100.0},
        "KOSDAQ-B": {"current_price": 90.0, "previous_close": 100.0},
    }


def test_snapshot_normalizes_all_read_only_market_context_components():
    service = KrMarketContextService(
        kis_client=FakeKis(),
        alpaca_client=FakeAlpaca(),
    )
    snapshot = service.snapshot(
        as_of=AS_OF,
        symbols=[
            {"symbol": "KOSPI-A", "market": "KOSPI"},
            {"symbol": "KOSPI-B", "market": "KOSPI"},
            {"symbol": "KOSPI-C", "market": "KOSPI"},
            {"symbol": "KOSDAQ-A", "market": "KOSDAQ"},
            {"symbol": "KOSDAQ-B", "market": "KOSDAQ"},
        ],
        quote_snapshots=_quotes(),
    )

    assert snapshot["timezone"] == "Asia/Seoul"
    assert snapshot["fx"] == {
        "usdkrw": 1380.0,
        "current": 1380.0,
        "previous": 1365.0,
        "previous_close": 1365.0,
        "change_pct": 1.0989,
        "direction": "krw_weakening",
        "source": "kis",
        "available": True,
        "as_of": AS_OF.isoformat(),
        "session_date": "2026-09-01",
        "freshness": "latest_completed",
        "identifier": KIS_USDKRW_ISCD,
        "identifier_name": KIS_USDKRW_IDENTIFIER_NAME,
        "requested_market_division": "X",
        "identifier_configured": True,
    }
    assert snapshot["us_market"]["source"] == "alpaca_etf_proxy"
    assert snapshot["us_market"]["available"] is True
    assert snapshot["us_market"]["spy_return_pct"] == 2.0
    assert snapshot["us_market"]["qqq_return_pct"] == 3.0
    assert snapshot["us_market"]["dia_return_pct"] == 4.0
    assert snapshot["us_market"]["smh_return_pct"] == 5.0
    assert snapshot["kr_breadth"]["sample_scope"] == "automation_universe"
    assert snapshot["kr_breadth"]["index_context"]["available"] is True
    assert snapshot["kr_breadth"]["index_context"]["kospi"]["change_pct"] == 1.0101
    assert snapshot["kr_breadth"]["sample_size"] == 5
    assert snapshot["kr_breadth"]["kospi"]["valid_count"] == 3
    assert snapshot["kr_breadth"]["kosdaq"]["valid_count"] == 2
    assert snapshot["kr_breadth"]["kospi"]["advance_ratio"] == 0.3333
    assert snapshot["kr_breadth"]["kosdaq"]["advance_ratio"] == 0.5
    assert snapshot["investor_flow"]["foreign_net_buy_krw"] == 125_000_000.0
    assert snapshot["investor_flow"]["raw_unit"] == "million_krw"
    assert snapshot["investor_flow"]["raw_values"] == {"foreign": 125.0, "institution": 0.0}
    assert snapshot["investor_flow"]["institution_net_buy_krw"] == 0.0
    assert snapshot["investor_flow"]["foreign_direction"] == "net_buy"
    assert snapshot["investor_flow"]["institution_direction"] == "neutral"
    assert snapshot["investor_flow"]["session_date"] == "2026-09-02"
    assert snapshot["investor_flow"]["requested_date"] == "2026-09-02"
    assert snapshot["investor_flow"]["freshness"] == "current"
    assert snapshot["investor_flow"]["scope"] == "market_wide"
    assert snapshot["investor_flow"]["by_market"]["KOSPI"]["market_code"] == "KSP"
    assert snapshot["investor_flow"]["by_market"]["KOSDAQ"]["market_code"] == "KSQ"
    assert snapshot["investor_flow"]["by_market"]["KOSPI"]["request_params"] == {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd": "0001",
        "fid_input_date_1": "20260902",
        "fid_input_iscd_1": "KSP",
        "fid_input_date_2": "20260902",
        "fid_input_iscd_2": "0001",
    }
    assert snapshot["commodities"]["available"] is False
    assert snapshot["geopolitical"]["available"] is False
    assert snapshot["warnings"] == []

    summary = service.summary(snapshot)
    assert summary["fx_available"] is True
    assert summary["fx_error_reason"] is None
    assert summary["usdkrw"] == 1380.0
    assert summary["fx_current"] == 1380.0
    assert summary["fx_identifier"] == KIS_USDKRW_ISCD
    assert summary["fx_identifier_name"] == KIS_USDKRW_IDENTIFIER_NAME
    assert summary["fx_session_date"] == "2026-09-01"
    assert summary["fx_freshness"] == "latest_completed"
    assert summary["investor_flow_session_date"] == "2026-09-02"
    assert summary["investor_flow_requested_date"] == "2026-09-02"
    assert summary["investor_flow_freshness"] == "current"
    assert summary["investor_flow_scope"] == "market_wide"
    assert summary["us_market_returns"]["spy_return_pct"] == 2.0
    assert summary["breadth_available"] is True
    assert summary["breadth_error_reason"] is None
    assert summary["kr_breadth_ratios"]["kospi"] == 0.3333
    assert summary["investor_flow_available"] is True
    assert summary["investor_flow_raw_unit"] == "million_krw"
    assert summary["foreign_institution_flow_available"] is True
    assert summary["us_market_available"] is True
    assert summary["disclosure_count"] == 0
    assert summary["data_freshness"]["status"] == "fresh"


def test_snapshot_is_fail_soft_per_component_and_never_fabricates_values():
    class BrokenKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_usdkrw_daily_chart(self, **kwargs):
            raise RuntimeError("fx down")

        def get_domestic_stock_price(self, symbol):
            raise RuntimeError("quotes down")

        def get_domestic_investor_daily_by_market(self, market, **kwargs):
            raise RuntimeError("flow down")
    class BrokenAlpaca:
        def get_recent_bars(self, symbol, **kwargs):
            raise RuntimeError("alpaca down")

    service = KrMarketContextService(
        kis_client=BrokenKis(),
        alpaca_client=BrokenAlpaca(),
    )
    snapshot = service.snapshot(
        as_of=AS_OF,
        symbols=[{"symbol": "005930", "market": "KOSPI"}],
    )

    assert snapshot["fx"]["available"] is False
    assert snapshot["fx"]["usdkrw"] is None
    assert snapshot["fx"]["error_reason"] == "api_error"
    assert snapshot["us_market"]["available"] is False
    assert snapshot["us_market"]["spy_return_pct"] is None
    assert snapshot["kr_breadth"]["available"] is False
    assert snapshot["kr_breadth"]["error_reason"] == "api_error"
    assert snapshot["investor_flow"]["available"] is False
    assert snapshot["investor_flow"]["error_reason"] == "api_error"
    assert "fx_unavailable" in snapshot["warnings"]
    assert "us_market_unavailable" in snapshot["warnings"]
    assert "kr_breadth_unavailable" in snapshot["warnings"]
    assert "investor_flow_unavailable" in snapshot["warnings"]
    assert "kr_index_unavailable" in snapshot["warnings"]


def test_candidate_disclosures_are_bounded_and_candidate_specific():
    service = KrMarketContextService(kis_client=FakeKis())
    disclosures = service.get_disclosures("005930", as_of=AS_OF, limit=5)

    assert disclosures["available"] is True
    assert disclosures["symbol"] == "005930"
    assert len(disclosures["items"]) == 5
    assert all("005930" in item["title"] for item in disclosures["items"])


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({"action": "hold"}))


def test_preview_gpt_prompt_contains_context_and_execution_separation_rules():
    responses = FakeResponses()
    advisor = KisPreviewGptAdvisor(
        settings=SimpleNamespace(
            openai_model="test-model",
            openai_reasoning_effort="low",
        ),
        client=SimpleNamespace(responses=responses),
    )
    market_context = {
        "as_of": AS_OF.isoformat(),
        "fx": {"usdkrw": 1380.0, "available": True},
    }
    execution_context = {
        "preview_only": True,
        "trading_enabled": False,
        "kr_trading_disabled": True,
        "broker_submit_permission": False,
    }

    advisor._call_openai(
        symbol="005930",
        name="Samsung",
        current_price=72000.0,
        indicator_status="ok",
        indicator_payload={"ema20": 70000.0},
        market_session={"is_market_open": True},
        reference_sources=[],
        market_context=market_context,
        disclosure_context={"available": True, "items": []},
        execution_context=execution_context,
    )

    call = responses.calls[0]
    prompt = json.loads(call["input"])
    assert prompt["market_context"] == market_context
    assert prompt["execution_context"] == execution_context
    assert "Use only the supplied market_context for factual market-state claims." in prompt["instructions"]
    assert "If a market_context field is unavailable, explicitly state the limitation." in prompt["instructions"]
    assert "Never invent missing market data." in prompt["instructions"]
    assert "must not change ai_buy_score" in " ".join(prompt["instructions"])
    assert "Use only the supplied market_context" in call["instructions"]

def test_kis_fx_adapter_parses_official_output1_summary_and_output2_rows():
    client = KisClient.__new__(KisClient)
    calls = []

    def fake_request_get(path, *, tr_id, params):
        calls.append((path, tr_id, params))
        return {
            "rt_cd": "0",
            "output1": {
                "stck_bsop_date": "20260902",
                "ovrs_nmix_prdy_clpr": "1390.0",
                "ovrs_nmix_prpr": "1395.2",
                "prdy_ctrt": "0.374",
            },
            "output2": [
                {
                    "stck_bsop_date": "20260901",
                    "ovrs_nmix_prpr": "1390.0",
                    "ovrs_nmix_prdy_vrss": "2.0",
                    "prdy_ctrt": "0.144",
                }
            ],
        }

    client.request_get = fake_request_get
    rows = client.get_usdkrw_daily_chart(as_of=AS_OF, limit=5)

    assert calls[0][1] == "FHKST03030100"
    assert calls[0][2]["FID_COND_MRKT_DIV_CODE"] == "X"
    assert calls[0][2]["FID_INPUT_ISCD"] == KIS_USDKRW_ISCD
    assert rows[-1] == {
        "symbol": KIS_USDKRW_ISCD,
        "date": "2026-09-02",
        "close": 1395.2,
        "previous_close": 1390.0,
        "change_pct": 0.374,
        "freshness": "current",
    }


def test_fx_change_direction_uses_current_previous_and_flat_is_explicit():
    class FlatKis(FakeKis):
        def get_usdkrw_daily_chart(self, *, as_of=None, limit=5):
            return [
                {
                    "date": "2026-09-02",
                    "close": 1390.0,
                    "previous_close": 1390.0,
                }
            ]

    service = KrMarketContextService(kis_client=FlatKis())
    snapshot = service.snapshot(as_of=AS_OF)

    assert snapshot["fx"]["usdkrw"] == 1390.0
    assert snapshot["fx"]["previous"] == 1390.0
    assert snapshot["fx"]["change_pct"] == 0.0
    assert snapshot["fx"]["direction"] == "flat"
    assert snapshot["fx"]["freshness"] == "current"


def test_fx_failure_exposes_sanitized_error_reason_and_warning():
    class FailedFxKis(FakeKis):
        def get_usdkrw_daily_chart(self, **kwargs):
            raise RuntimeError("secret token must never be returned")

    snapshot = KrMarketContextService(kis_client=FailedFxKis()).snapshot(as_of=AS_OF)

    assert snapshot["fx"]["available"] is False
    assert snapshot["fx"]["error_reason"] == "api_error"
    assert "fx_unavailable" in snapshot["warnings"]
    assert "secret" not in json.dumps(snapshot).lower()
    assert "token" not in json.dumps(snapshot).lower()


def test_breadth_excludes_missing_previous_close_from_valid_sample():
    service = KrMarketContextService(kis_client=None)
    breadth, warnings = service._breadth(
        symbols=[
            {"symbol": "KOSPI-A", "market": "KOSPI"},
            {"symbol": "KOSPI-B", "market": "KOSPI"},
        ],
        quote_snapshots={
            "KOSPI-A": {"current_price": 110.0, "previous_close": 100.0},
            "KOSPI-B": {"current_price": 90.0},
        },
        as_of=AS_OF,
    )

    assert breadth["available"] is True
    assert breadth["kospi"]["valid_count"] == 1
    assert breadth["kospi"]["advance_ratio"] == 1.0
    assert breadth["sample_size"] == 1
    assert breadth["failed_symbol_count"] == 1
    assert "kr_breadth_partial" in warnings


def test_partial_breadth_source_failure_keeps_valid_sample_available():
    service = KrMarketContextService(kis_client=None)
    breadth, warnings = service._breadth(
        symbols=[
            {"symbol": "KOSPI-A", "market": "KOSPI"},
            {"symbol": "KOSDAQ-A", "market": "KOSDAQ"},
            {"symbol": "KOSDAQ-B", "market": "KOSDAQ"},
        ],
        quote_snapshots={
            "KOSPI-A": {"current_price": 110.0, "previous_close": 100.0},
            "KOSDAQ-A": {"current_price": 90.0, "previous_close": 100.0},
        },
        as_of=AS_OF,
    )

    assert breadth["available"] is True
    assert breadth["sample_size"] == 2
    assert breadth["kospi"]["advance_ratio"] == 1.0
    assert breadth["kosdaq"]["advance_ratio"] == 0.0
    assert breadth["failed_symbol_count"] == 1
    assert "kr_breadth_partial" in warnings


def test_all_breadth_sources_failed_returns_error_reason():
    class FailedQuotes:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_stock_price(self, symbol):
            raise RuntimeError("quote API failed")

    service = KrMarketContextService(kis_client=FailedQuotes())
    breadth, warnings = service._breadth(
        symbols=[{"symbol": "005930", "market": "KOSPI"}],
        quote_snapshots=None,
        as_of=AS_OF,
    )

    assert breadth["available"] is False
    assert breadth["error_reason"] == "api_error"
    assert breadth["sample_size"] == 0
    assert "kr_breadth_unavailable" in warnings


def test_investor_flow_normalizes_kis_million_krw_fields_to_actual_krw():
    class RawFlowKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
            if market == "KOSDAQ":
                return []
            return {
                "frgn_ntby_tr_pbmn": "-114060",
                "orgn_ntby_tr_pbmn": "-736742",
            }

    service = KrMarketContextService(kis_client=RawFlowKis())
    flow, warnings = service._investor_flow(AS_OF)

    assert flow["available"] is True
    assert flow["foreign_net_buy_krw"] == -114_060_000_000.0
    assert flow["institution_net_buy_krw"] == -736_742_000_000.0
    assert flow["foreign_direction"] == "net_sell"
    assert flow["institution_direction"] == "net_sell"
    assert flow["raw_unit"] == "million_krw"
    assert flow["raw_values"] == {
        "foreign": -114060.0,
        "institution": -736742.0,
    }
    assert flow["normalized_values_krw"] == {
        "foreign": -114_060_000_000.0,
        "institution": -736_742_000_000.0,
    }
    assert "investor_flow_kosdaq_unavailable" in warnings


def test_market_context_service_is_read_only():
    source = open("app/services/kr_market_context_service.py", encoding="utf-8").read()
    lowered = source.lower()
    for forbidden in (
        "submit_order",
        "submit_domestic_cash_order",
        "submit_manual",
        "kismanualorderservice",
        "broker submit",
    ):
        assert forbidden not in lowered


def test_kis_domestic_quote_uses_krx_j_for_both_internal_markets():
    client = KisClient.__new__(KisClient)
    client.settings = SimpleNamespace(kis_env="prod")
    calls = []

    def fake_request_get(path, *, tr_id, params):
        calls.append((path, tr_id, params))
        return {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "100",
                "stck_sdpr": "99",
                "prdy_vrss": "1",
                "rprs_mrkt_kor_name": (
                    "코스피"
                    if params["FID_INPUT_ISCD"] == "005930"
                    else "코스닥"
                ),
            },
        }

    client.request_get = fake_request_get
    kospi = client.get_domestic_stock_price("005930")
    kosdaq = client.get_domestic_stock_price("086520")

    assert [call[2]["FID_COND_MRKT_DIV_CODE"] for call in calls] == [
        KIS_DOMESTIC_QUOTE_MARKET_CODE,
        KIS_DOMESTIC_QUOTE_MARKET_CODE,
    ]
    assert kospi["market"] == "KOSPI"
    assert kosdaq["market"] == "KOSDAQ"


def test_breadth_uses_internal_listing_market_for_exact_40_10_universe():
    symbols = []
    quotes = {}
    for index in range(40):
        symbol = f"K{index:05d}"
        symbols.append(
            {
                "symbol": symbol,
                "market": "KR",
                "listing_market": "KOSPI",
            }
        )
        current = 110.0 if index < 20 else 90.0 if index < 30 else 100.0
        quotes[symbol] = {"current_price": current, "previous_close": 100.0}
    for index in range(10):
        symbol = f"D{index:05d}"
        symbols.append(
            {
                "symbol": symbol,
                "market": "KR",
                "listing_market": "KOSDAQ",
            }
        )
        current = 110.0 if index < 4 else 90.0 if index < 7 else 100.0
        quotes[symbol] = {"current_price": current, "previous_close": 100.0}

    service = KrMarketContextService(kis_client=None)
    breadth, warnings = service._breadth(
        symbols=symbols,
        quote_snapshots=quotes,
        as_of=AS_OF,
    )

    assert breadth["available"] is True
    assert breadth["sample_size"] == 50
    assert breadth["valid_count"] == 50
    assert breadth["failed_symbol_count"] == 0
    assert breadth["kospi"]["valid_count"] == 40
    assert breadth["kospi"]["advancers"] == 20
    assert breadth["kospi"]["decliners"] == 10
    assert breadth["kospi"]["unchanged"] == 10
    assert breadth["kospi"]["advance_ratio"] == 0.5
    assert breadth["kosdaq"]["valid_count"] == 10
    assert breadth["kosdaq"]["advancers"] == 4
    assert breadth["kosdaq"]["decliners"] == 3
    assert breadth["kosdaq"]["unchanged"] == 3
    assert breadth["kosdaq"]["advance_ratio"] == 0.4
    assert warnings == []


def test_fx_adapter_falls_back_to_two_output2_completed_rows():
    client = KisClient.__new__(KisClient)
    calls = []

    def fake_request_get(path, *, tr_id, params):
        calls.append(params)
        return {
            "rt_cd": "0",
            "output2": [
                {
                    "stck_bsop_date": "20260901",
                    "ovrs_nmix_prpr": "1390.0",
                },
                {
                    "stck_bsop_date": "20260902",
                    "ovrs_nmix_prpr": "1395.2",
                },
            ],
        }

    client.request_get = fake_request_get
    rows = client.get_usdkrw_daily_chart(as_of=AS_OF, limit=5)

    assert calls[0]["FID_COND_MRKT_DIV_CODE"] == KIS_FX_MARKET_DIVISION
    assert calls[0]["FID_INPUT_ISCD"] == KIS_USDKRW_ISCD
    assert rows[-1]["close"] == 1395.2
    assert rows[-1]["previous_close"] == 1390.0
    assert rows[-1]["change_pct"] == 0.3741007194


def test_fx_wrong_identifier_is_reported_without_raw_error_details():
    class WrongIdentifierKis(FakeKis):
        def get_usdkrw_daily_chart(self, **kwargs):
            return {
                "error_reason": "unsupported_identifier",
                "requested_market_division": "X",
                "identifier_configured": False,
                "message": "private appsecret must not leak",
            }

    snapshot = KrMarketContextService(kis_client=WrongIdentifierKis()).snapshot(
        as_of=AS_OF
    )

    assert snapshot["fx"]["available"] is False
    assert snapshot["fx"]["error_reason"] == "unsupported_identifier"
    assert snapshot["fx"]["requested_market_division"] == "X"
    assert snapshot["fx"]["identifier_configured"] is True
    assert "appsecret" not in json.dumps(snapshot).lower()

def test_kis_investor_flow_request_params_match_official_market_contract():
    client = KisClient.__new__(KisClient)
    client.settings = SimpleNamespace(kis_env="prod")
    calls = []

    def fake_request_get(path, *, tr_id, params):
        calls.append((path, tr_id, dict(params)))
        return {
            "rt_cd": "0",
            "output": [
                {
                    "stck_bsop_date": "20260902",
                    "frgn_ntby_tr_pbmn": "1",
                    "orgn_ntby_tr_pbmn": "-2",
                }
            ],
        }

    client.request_get = fake_request_get
    kospi = client.get_domestic_investor_daily_by_market("KOSPI", as_of=AS_OF)
    kosdaq = client.get_domestic_investor_daily_by_market("KOSDAQ", as_of=AS_OF)

    assert [call[0] for call in calls] == [
        KIS_INVESTOR_DAILY_BY_MARKET_PATH,
        KIS_INVESTOR_DAILY_BY_MARKET_PATH,
    ]
    assert [call[1] for call in calls] == [
        KIS_INVESTOR_DAILY_BY_MARKET_TR_ID,
        KIS_INVESTOR_DAILY_BY_MARKET_TR_ID,
    ]
    assert calls[0][2] == {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001",
        "FID_INPUT_DATE_1": "20260902",
        "FID_INPUT_ISCD_1": "KSP",
        "FID_INPUT_DATE_2": "20260902",
        "FID_INPUT_ISCD_2": "0001",
    }
    assert calls[1][2] == {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "1001",
        "FID_INPUT_DATE_1": "20260902",
        "FID_INPUT_ISCD_1": "KSQ",
        "FID_INPUT_DATE_2": "20260902",
        "FID_INPUT_ISCD_2": "1001",
    }
    assert kospi[0]["market"] == "KOSPI"
    assert kospi[0]["market_code"] == "KSP"
    assert kospi[0]["scope"] == "market_wide"
    assert kospi[0]["requested_date"] == "20260902"
    assert kosdaq[0]["market"] == "KOSDAQ"
    assert kosdaq[0]["market_code"] == "KSQ"


def test_investor_flow_selects_requested_date_from_descending_history_not_last_row():
    class HistoricalFlowKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
            current = (10, -20) if market == "KOSPI" else (30, -40)
            stale = (1000, -2000)
            return [
                {
                    "stck_bsop_date": "20260902",
                    "market": market,
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": str(current[0]),
                    "orgn_ntby_tr_pbmn": str(current[1]),
                },
                {
                    "stck_bsop_date": "20260901",
                    "market": market,
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": "50",
                    "orgn_ntby_tr_pbmn": "-60",
                },
                {
                    "stck_bsop_date": "20250613",
                    "market": market,
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": str(stale[0]),
                    "orgn_ntby_tr_pbmn": str(stale[1]),
                },
            ]

    flow, warnings = KrMarketContextService(
        kis_client=HistoricalFlowKis()
    )._investor_flow(AS_OF)

    assert warnings == []
    assert flow["available"] is True
    assert flow["session_date"] == "2026-09-02"
    assert flow["freshness"] == "current"
    assert flow["raw_values"] == {"foreign": 40.0, "institution": -60.0}
    assert flow["normalized_values_krw"] == {
        "foreign": 40_000_000.0,
        "institution": -60_000_000.0,
    }
    assert flow["by_market"]["KOSPI"]["raw_value"] == {
        "foreign": 10.0,
        "institution": -20.0,
    }
    assert flow["by_market"]["KOSDAQ"]["raw_value"] == {
        "foreign": 30.0,
        "institution": -40.0,
    }


def test_investor_flow_uses_latest_completed_row_when_requested_date_is_absent():
    class CompletedFlowKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
            return [
                {
                    "stck_bsop_date": "20260901",
                    "market": market,
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": "7",
                    "orgn_ntby_tr_pbmn": "-8",
                },
                {
                    "stck_bsop_date": "20260831",
                    "market": market,
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": "70",
                    "orgn_ntby_tr_pbmn": "-80",
                },
            ]

    flow, warnings = KrMarketContextService(
        kis_client=CompletedFlowKis()
    )._investor_flow(AS_OF)

    assert warnings == []
    assert flow["available"] is True
    assert flow["session_date"] == "2026-09-01"
    assert flow["freshness"] == "latest_completed"
    assert flow["raw_values"] == {"foreign": 14.0, "institution": -16.0}


def test_investor_flow_rejects_future_only_rows_as_stale():
    class FutureFlowKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
            return {
                "stck_bsop_date": "20260903",
                "market": market,
                "scope": "market_wide",
                "frgn_ntby_tr_pbmn": "1",
                "orgn_ntby_tr_pbmn": "2",
            }

    flow, warnings = KrMarketContextService(
        kis_client=FutureFlowKis()
    )._investor_flow(AS_OF)

    assert flow["available"] is False
    assert flow["error_reason"] == "stale_data"
    assert "investor_flow_unavailable" in warnings


def test_investor_flow_prefers_market_wide_scope_and_reports_row_metadata():
    class ScopedFlowKis:
        settings = SimpleNamespace(kis_enabled=True)

        def get_domestic_investor_daily_by_market(self, market, *, as_of=None):
            return [
                {
                    "stck_bsop_date": "20260902",
                    "market": market,
                    "market_code": "KSP" if market == "KOSPI" else "KSQ",
                    "scope": "sector",
                    "frgn_ntby_tr_pbmn": "999",
                    "orgn_ntby_tr_pbmn": "999",
                },
                {
                    "stck_bsop_date": "20260902",
                    "market": market,
                    "market_code": "KSP" if market == "KOSPI" else "KSQ",
                    "scope": "market_wide",
                    "frgn_ntby_tr_pbmn": "3",
                    "orgn_ntby_tr_pbmn": "-4",
                },
            ]

    flow, warnings = KrMarketContextService(
        kis_client=ScopedFlowKis()
    )._investor_flow(AS_OF)

    assert warnings == []
    assert flow["available"] is True
    assert flow["raw_values"] == {"foreign": 6.0, "institution": -8.0}
    assert flow["by_market"]["KOSPI"]["scope"] == "market_wide"
    assert flow["by_market"]["KOSPI"]["session_date"] == "2026-09-02"
    assert flow["by_market"]["KOSPI"]["requested_date"] == "2026-09-02"
    assert flow["by_market"]["KOSPI"]["source"] == "kis"
    assert flow["by_market"]["KOSPI"]["request_params"]["fid_input_iscd_1"] == "KSP"
    assert flow["by_market"]["KOSDAQ"]["market_code"] == "KSQ"


def test_fx_rejects_a_noncanonical_identifier_even_when_values_are_valid():
    class WrongSeriesKis(FakeKis):
        def get_usdkrw_daily_chart(self, *, as_of=None, limit=5):
            return [
                {
                    "symbol": "FX@KRW",
                    "date": "2026-09-02",
                    "close": 1380.0,
                    "previous_close": 1370.0,
                }
            ]

    snapshot = KrMarketContextService(kis_client=WrongSeriesKis()).snapshot(
        as_of=AS_OF
    )

    assert snapshot["fx"]["available"] is False
    assert snapshot["fx"]["error_reason"] == "unsupported_identifier"
    assert snapshot["fx"]["identifier"] == KIS_USDKRW_ISCD
    assert snapshot["fx"]["identifier_name"] == KIS_USDKRW_IDENTIFIER_NAME
    assert "close" not in snapshot["fx"]