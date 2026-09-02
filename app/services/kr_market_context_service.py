from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.brokers.alpaca_client import AlpacaClient
from app.brokers.kis_client import (
    KIS_FX_MARKET_DIVISION,
    KIS_USDKRW_IDENTIFIER_NAME,
    KIS_USDKRW_ISCD,
    KisClient,
)
from app.config import get_settings


SEOUL = ZoneInfo("Asia/Seoul")
NEW_YORK = ZoneInfo("America/New_York")
US_ETF_PROXIES = {
    "spy_return_pct": "SPY",
    "qqq_return_pct": "QQQ",
    "dia_return_pct": "DIA",
    "smh_return_pct": "SMH",
}


INVESTOR_FLOW_RAW_UNIT = "million_krw"
INVESTOR_FLOW_RAW_MULTIPLIER = 1_000_000

class KrMarketContextService:
    """Build one read-only, fail-soft Korean market context snapshot.

    The service deliberately accepts broker-like objects instead of creating
    a new API client abstraction.  Production callers can use the existing
    KIS/Alpaca clients; tests can inject deterministic fakes.
    """

    def __init__(
        self,
        kis_client: KisClient | Any | None = None,
        *,
        alpaca_client: AlpacaClient | Any | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.kis_client = kis_client
        self.alpaca_client = alpaca_client
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def snapshot(
        self,
        *,
        db=None,
        symbols=None,
        as_of: datetime | date | str | None = None,
        quote_snapshots: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-safe snapshot whose components are independently safe.

        ``symbols`` may contain symbol strings or watchlist dictionaries with
        a ``market`` field.  ``quote_snapshots`` is an optional set of quotes
        already collected by the caller; passing it avoids a second quote
        request for the automation universe.
        """
        captured_at = _coerce_datetime(as_of) or _coerce_datetime(self._now_factory())
        if captured_at is None:
            captured_at = datetime.now(UTC)
        captured_at = captured_at.astimezone(UTC)
        warnings: list[str] = []

        fx, component_warnings = self._fx(captured_at)
        warnings.extend(component_warnings)

        us_market, component_warnings = self._us_market(captured_at)
        warnings.extend(component_warnings)

        kr_breadth, component_warnings = self._breadth(
            symbols=symbols,
            quote_snapshots=quote_snapshots,
            as_of=captured_at,
        )
        warnings.extend(component_warnings)

        index_context, component_warnings = self._indices(captured_at)
        kr_breadth["index_context"] = index_context
        warnings.extend(component_warnings)

        investor_flow, component_warnings = self._investor_flow(captured_at)
        warnings.extend(component_warnings)

        disclosures = {
            "available": self._kis_is_available(),
            "items": [],
            "source": "kis",
            "scope": "candidate_specific",
        }
        if not disclosures["available"]:
            warnings.append("disclosures_unavailable")

        commodities = {"available": False}
        geopolitical = {"available": False}

        return {
            "as_of": captured_at.isoformat(),
            "timezone": "Asia/Seoul",
            "fx": fx,
            "us_market": us_market,
            "kr_breadth": kr_breadth,
            "investor_flow": investor_flow,
            "disclosures": disclosures,
            "commodities": commodities,
            "geopolitical": geopolitical,
            "warnings": _dedupe(warnings),
        }

    def get_disclosures(
        self,
        symbol: str,
        *,
        as_of: datetime | date | str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Return bounded candidate-specific KIS disclosure/news titles."""
        safe_limit = max(1, min(int(limit or 5), 5))
        if not self._kis_is_available():
            return {
                "symbol": str(symbol).strip().upper(),
                "available": False,
                "items": [],
                "source": "kis",
                "warnings": ["disclosures_unavailable"],
            }

        captured_at = _coerce_datetime(as_of)
        warnings: list[str] = []
        rows: Any = None
        method = _first_callable(
            self.kis_client,
            (
                "get_domestic_news_titles",
                "get_company_disclosures",
                "get_disclosures",
            ),
        )
        if method is None:
            return {
                "symbol": str(symbol).strip().upper(),
                "available": False,
                "items": [],
                "source": "kis",
                "warnings": ["disclosures_unavailable"],
            }
        try:
            rows = _call_with_optional_kwargs(
                method,
                str(symbol).strip().upper(),
                as_of=captured_at,
                limit=safe_limit,
            )
        except Exception:
            warnings.append("disclosures_unavailable")

        items = _normalize_disclosures(rows, limit=safe_limit)
        available = bool(items) or not warnings
        if not items and warnings:
            available = False
        return {
            "symbol": str(symbol).strip().upper(),
            "available": available,
            "items": items,
            "source": "kis",
            "warnings": _dedupe(warnings),
        }

    @staticmethod
    def summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
        """Create a small safe observability projection of a snapshot."""
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        fx = _as_dict(snapshot.get("fx"))
        us_market = _as_dict(snapshot.get("us_market"))
        breadth = _as_dict(snapshot.get("kr_breadth"))
        flow = _as_dict(snapshot.get("investor_flow"))
        disclosures = _as_dict(snapshot.get("disclosures"))
        return {
            "market_context_as_of": snapshot.get("as_of"),
            "fx_available": bool(fx.get("available")),
            "fx_error_reason": fx.get("error_reason"),
            "usdkrw": fx.get("usdkrw"),
            "fx_current": fx.get("current"),
            "fx_identifier": fx.get("identifier"),
            "fx_identifier_name": fx.get("identifier_name"),
            "fx_session_date": fx.get("session_date"),
            "fx_freshness": fx.get("freshness"),
            "us_market_returns": {
                key: us_market.get(key)
                for key in US_ETF_PROXIES
            },
            "kr_breadth_ratios": {
                market: _as_dict(breadth.get(market)).get("advance_ratio")
                for market in ("kospi", "kosdaq")
            },
            "breadth_available": bool(breadth.get("available")),
            "breadth_error_reason": breadth.get("error_reason"),
            "investor_flow_available": bool(flow.get("available")),
            "investor_flow_raw_unit": flow.get("raw_unit"),
            "investor_flow_session_date": flow.get("session_date"),
            "investor_flow_requested_date": flow.get("requested_date"),
            "investor_flow_freshness": flow.get("freshness"),
            "investor_flow_scope": flow.get("scope"),
            "investor_flow_session_dates_by_market": flow.get("session_dates_by_market"),
            "investor_flow_request_params": flow.get("request_params_by_market"),
            "foreign_institution_flow_available": bool(flow.get("available")),
            "us_market_available": bool(us_market.get("available")),
            "disclosure_count": len(disclosures.get("items") or []),
            "warnings": list(snapshot.get("warnings") or []),
            "context_source": {
                "fx": fx.get("source"),
                "us_market": us_market.get("source"),
                "kr_breadth": breadth.get("source"),
                "investor_flow": flow.get("source"),
                "disclosures": disclosures.get("source"),
            },
            "data_freshness": {
                "as_of": snapshot.get("as_of"),
                "age_seconds": 0,
                "status": "fresh" if snapshot.get("as_of") else "unknown",
                "components": {
                    "fx": fx.get("freshness"),
                    "us_market": us_market.get("freshness"),
                    "breadth": breadth.get("freshness"),
                    "investor_flow": flow.get("freshness"),
                },
            },
        }

    def _fx(self, as_of: datetime) -> tuple[dict[str, Any], list[str]]:
        base = {
            "usdkrw": None,
            "current": None,
            "previous": None,
            "previous_close": None,
            "change_pct": None,
            "direction": "unknown",
            "source": "kis",
            "available": False,
            "as_of": None,
            "session_date": None,
            "freshness": "unknown",
            "identifier": KIS_USDKRW_ISCD,
            "identifier_name": KIS_USDKRW_IDENTIFIER_NAME,
            "requested_market_division": KIS_FX_MARKET_DIVISION,
            "identifier_configured": bool(KIS_USDKRW_ISCD),
        }
        if not self._kis_is_available():
            base["error_reason"] = "missing_required_field"
            return base, ["fx_unavailable"]

        method = _first_callable(
            self.kis_client,
            (
                "get_usdkrw_daily_chart",
                "get_usdkrw_rate",
                "get_fx_rate",
            ),
        )
        if method is None:
            base["error_reason"] = "missing_required_field"
            return base, ["fx_unavailable"]
        try:
            raw = _call_with_optional_kwargs(method, as_of=as_of, limit=5)
            row = _last_valid_row(_rows(raw))
            if row is None and isinstance(raw, dict):
                row = raw
            if row is None:
                base["error_reason"] = "empty_response"
                return base, ["fx_unavailable"]
            reported_reason = str(row.get("error_reason") or "").strip()
            if reported_reason in {
                "empty_response",
                "api_error",
                "missing_required_field",
                "parse_error",
                "unsupported_identifier",
            }:
                base["error_reason"] = reported_reason
                return base, ["fx_unavailable"]

            reported_identifier = _first_text(
                row,
                ("identifier", "symbol", "stck_shrn_iscd"),
            )
            if (
                reported_identifier
                and reported_identifier.upper() != KIS_USDKRW_ISCD
            ):
                base["error_reason"] = "unsupported_identifier"
                return base, ["fx_unavailable"]

            value_keys = (
                "usdkrw",
                "current",
                "current_price",
                "close",
                "price",
                "rate",
                "deal_bas_r",
                "ovrs_nmix_prpr",
                "ovrs_prod_prpr",
            )
            previous_keys = (
                "previous",
                "previous_close",
                "prev_close",
                "prdy_clpr",
                "prev",
                "ovrs_nmix_prdy_clpr",
            )
            usdkrw = _first_number(row, value_keys)
            previous = _first_number(row, previous_keys)
            change_pct = _first_number(
                row,
                ("change_pct", "change_rate", "prdy_ctrt"),
            )
            if change_pct is None and usdkrw is not None and previous not in (None, 0):
                change_pct = ((usdkrw - previous) / previous) * 100.0
            if usdkrw is None or usdkrw <= 0:
                base["error_reason"] = (
                    "parse_error"
                    if _field_has_value(row, value_keys)
                    else "missing_required_field"
                )
                return base, ["fx_unavailable"]
            session_date = _row_session_date(row)
            freshness = _first_text(row, ("freshness",)) or _data_freshness(
                session_date,
                as_of.date(),
            )
            base.update(
                {
                    "usdkrw": round(usdkrw, 4),
                    "current": round(usdkrw, 4),
                    "previous": _round_or_none(previous),
                    "previous_close": _round_or_none(previous),
                    "change_pct": _round_or_none(change_pct),
                    "direction": (
                        _fx_direction(change_pct)
                        if change_pct is not None
                        else "unknown"
                    ),
                    "source": _first_text(row, ("source",)) or "kis",
                    "available": True,
                    "as_of": as_of.isoformat(),
                    "session_date": session_date,
                    "freshness": freshness,
                }
            )
            base.pop("error_reason", None)
            return base, []
        except Exception:
            base["error_reason"] = "api_error"
            return base, ["fx_unavailable"]
    def _us_market(self, as_of: datetime) -> tuple[dict[str, Any], list[str]]:
        result = {
            "spy_return_pct": None,
            "qqq_return_pct": None,
            "dia_return_pct": None,
            "smh_return_pct": None,
            "session_date": None,
            "source": "alpaca_etf_proxy",
            "available": False,
            "freshness": "unknown",
            "proxy_symbols": dict(US_ETF_PROXIES),
        }
        client = self._get_alpaca_client()
        if client is None:
            return result, ["us_market_unavailable"]

        warnings: list[str] = []
        session_dates: list[str] = []
        for field, symbol in US_ETF_PROXIES.items():
            try:
                bars = self._get_daily_bars(client, symbol)
                rows = _normalize_bars(bars)
                rows = _completed_rows(rows, as_of)
                if len(rows) < 2:
                    warnings.append(f"{field}_unavailable")
                    continue
                previous = _number(rows[-2].get("close"))
                current = _number(rows[-1].get("close"))
                if previous in (None, 0) or current is None:
                    warnings.append(f"{field}_unavailable")
                    continue
                result[field] = round(((current - previous) / previous) * 100.0, 4)
                if rows[-1].get("date"):
                    session_dates.append(str(rows[-1]["date"]))
                result["available"] = True
            except Exception:
                warnings.append(f"{field}_unavailable")
        if session_dates:
            result["session_date"] = sorted(session_dates)[-1]
        if result["available"]:
            result["freshness"] = "latest_completed"
        if not result["available"]:
            warnings.insert(0, "us_market_unavailable")
        return result, _dedupe(warnings)

    def _get_daily_bars(self, client: Any, symbol: str) -> Any:
        method = _first_callable(client, ("get_daily_bars", "get_recent_bars"))
        if method is None:
            raise AttributeError("Alpaca market data client has no daily bars method")
        try:
            return method(symbol, limit=5, timeframe="1Day")
        except TypeError:
            try:
                return method(symbol, limit=5)
            except TypeError:
                return method(symbol)

    def _breadth(
        self,
        *,
        symbols: Any,
        quote_snapshots: dict[str, Any] | list[dict[str, Any]] | None,
        as_of: datetime,
    ) -> tuple[dict[str, Any], list[str]]:
        markets = {
            "KOSPI": {"advancers": 0, "decliners": 0, "unchanged": 0},
            "KOSDAQ": {"advancers": 0, "decliners": 0, "unchanged": 0},
        }
        symbol_rows = _symbol_rows(symbols)
        snapshots = _snapshot_map(quote_snapshots)
        warnings: list[str] = []
        failure_reasons: list[str] = []
        failed_symbol_count = 0
        for symbol_row in symbol_rows:
            symbol = _symbol_from(symbol_row)
            if not symbol:
                failure_reasons.append("missing_required_field")
                failed_symbol_count += 1
                continue

            market = _market_from(symbol_row)
            if market not in markets:
                quote_hint = _as_dict(snapshots.get(symbol))
                market = _market_from(quote_hint)
            if market not in markets:
                failure_reasons.append("unsupported_market_code")
                failed_symbol_count += 1
                continue

            quote = _as_dict(snapshots.get(symbol))
            quote_fetch_failed = False
            if not quote and self._kis_is_available():
                method = _first_callable(
                    self.kis_client,
                    ("get_domestic_stock_price",),
                )
                if method is not None:
                    try:
                        quote = _as_dict(method(symbol))
                    except Exception:
                        failure_reasons.append("api_error")
                        failed_symbol_count += 1
                        quote_fetch_failed = True
                        quote = {}
                else:
                    failure_reasons.append("missing_required_field")
                    failed_symbol_count += 1
            if not quote:
                if not quote_fetch_failed:
                    failure_reasons.append("empty_response")
                    failed_symbol_count += 1
                continue

            current_keys = (
                "current_price",
                "current",
                "price",
                "stck_prpr",
            )
            previous_keys = (
                "previous_close",
                "prev_close",
                "previous",
                "stck_sdpr",
            )
            change_keys = ("change", "prdy_vrss")
            current = _first_number(quote, current_keys)
            previous = _first_number(quote, previous_keys)
            if previous is None:
                change = _first_number(quote, change_keys)
                if current is not None and change is not None:
                    previous = current - change
            if current is None or previous is None or current <= 0 or previous <= 0:
                if current is None:
                    reason = (
                        "parse_error"
                        if _field_has_value(quote, current_keys)
                        else "missing_required_field"
                    )
                elif previous is None:
                    reason = (
                        "parse_error"
                        if _field_has_value(quote, previous_keys + change_keys)
                        else "previous_close_missing"
                    )
                else:
                    reason = "parse_error"
                failure_reasons.append(reason)
                failed_symbol_count += 1
                continue

            if current > previous:
                markets[market]["advancers"] += 1
            elif current < previous:
                markets[market]["decliners"] += 1
            else:
                markets[market]["unchanged"] += 1

        sample_size = sum(sum(values.values()) for values in markets.values())
        result: dict[str, Any] = {}
        for market, values in markets.items():
            valid_count = sum(values.values())
            result[market.lower()] = {
                **values,
                "valid_count": valid_count,
                "advance_ratio": (
                    round(values["advancers"] / valid_count, 4)
                    if valid_count
                    else None
                ),
                "advance_ratio_denominator": "valid_sample_count",
            }
        available = sample_size > 0
        result.update(
            {
                "valid_count": sample_size,
                "sample_size": sample_size,
                "sample_scope": "automation_universe",
                "source": "kis_quotes",
                "available": available,
                "failed_symbol_count": failed_symbol_count,
                "freshness": "current" if available else "unknown",
            }
        )
        if not available:
            warnings.append("kr_breadth_unavailable")
            result["error_reason"] = _select_error_reason(
                failure_reasons,
                default="empty_response",
            )
        elif failed_symbol_count:
            warnings.append("kr_breadth_partial")
        return result, _dedupe(warnings)

    def _indices(self, as_of: datetime) -> tuple[dict[str, Any], list[str]]:
        result = {
            "kospi": {
                "close": None,
                "change_pct": None,
                "session_date": None,
                "source": "kis",
                "available": False,
            },
            "kosdaq": {
                "close": None,
                "change_pct": None,
                "session_date": None,
                "source": "kis",
                "available": False,
            },
            "source": "kis",
            "available": False,
        }
        if not self._kis_is_available():
            return result, ["kr_index_unavailable"]
        method = _first_callable(
            self.kis_client,
            ("get_domestic_index_daily_bars", "get_domestic_daily_index"),
        )
        if method is None:
            return result, ["kr_index_unavailable"]

        warnings: list[str] = []
        for market, index_code in (("kospi", "0001"), ("kosdaq", "1001")):
            try:
                raw = _call_with_optional_kwargs(
                    method,
                    index_code,
                    as_of=as_of,
                    limit=5,
                )
                row = _last_valid_row(_rows(raw))
                if row is None:
                    warnings.append(f"kr_index_{market}_unavailable")
                    continue
                close = _first_number(
                    row,
                    ("close", "current", "current_price", "bstp_nmix_prpr"),
                )
                previous = _first_number(
                    row,
                    ("previous_close", "prev_close", "previous", "bstp_nmix_prdy_clpr"),
                )
                change_pct = _first_number(row, ("change_pct", "change_rate", "prdy_ctrt"))
                if change_pct is None and close is not None and previous not in (None, 0):
                    change_pct = ((close - previous) / previous) * 100.0
                if close is None or close <= 0:
                    warnings.append(f"kr_index_{market}_unavailable")
                    continue
                result[market] = {
                    "close": round(close, 4),
                    "change_pct": _round_or_none(change_pct),
                    "session_date": _first_text(row, ("session_date", "date", "stck_bsop_date")),
                    "source": "kis",
                    "available": True,
                }
                result["available"] = True
            except Exception:
                warnings.append(f"kr_index_{market}_unavailable")
        if not result["available"]:
            warnings.insert(0, "kr_index_unavailable")
        return result, _dedupe(warnings)

    def _investor_flow(self, as_of: datetime) -> tuple[dict[str, Any], list[str]]:
        requested_date = as_of.date()
        result = {
            "foreign_net_buy_krw": None,
            "institution_net_buy_krw": None,
            "foreign_direction": "unknown",
            "institution_direction": "unknown",
            "source": "kis",
            "available": False,
            "by_market": {},
            "raw_unit": INVESTOR_FLOW_RAW_UNIT,
            "raw_values": {"foreign": None, "institution": None},
            "normalized_values_krw": {"foreign": None, "institution": None},
            "raw_value": {"foreign": None, "institution": None},
            "normalized_value": {"foreign_net_buy_krw": None, "institution_net_buy_krw": None},
            "session_date": None,
            "requested_date": requested_date.isoformat(),
            "session_dates_by_market": {},
            "market_codes": {},
            "scope": "market_wide",
            "request_params_by_market": {},
            "freshness": "unknown",
        }
        if not self._kis_is_available():
            result["error_reason"] = "missing_required_field"
            return result, ["investor_flow_unavailable"]

        method = _first_callable(
            self.kis_client,
            (
                "get_domestic_investor_daily_by_market",
                "get_domestic_market_investor_flow",
                "get_investor_flow_by_market",
            ),
        )
        if method is None:
            result["error_reason"] = "missing_required_field"
            return result, ["investor_flow_unavailable"]

        warnings: list[str] = []
        totals = {"foreign": 0.0, "institution": 0.0}
        found = {"foreign": False, "institution": False}
        raw_totals = {"foreign": 0.0, "institution": 0.0}
        raw_found = {"foreign": False, "institution": False}
        raw_units: set[str] = set()
        failure_reasons: list[str] = []
        selected_session_dates: set[str] = set()
        for market in ("KOSPI", "KOSDAQ"):
            request_params = _flow_request_params(market, requested_date)
            result["request_params_by_market"][market] = request_params
            result["market_codes"][market] = request_params["fid_input_iscd_1"]
            try:
                raw = _call_with_optional_kwargs(method, market, as_of=as_of)
                row, selection_reason = _select_investor_flow_row(
                    raw,
                    market=market,
                    target_date=requested_date,
                )
                if row is None:
                    warnings.append(f"investor_flow_{market.lower()}_unavailable")
                    failure_reasons.append(selection_reason or "empty_response")
                    continue

                session_date = _row_session_date(row)
                if session_date:
                    result["session_dates_by_market"][market] = session_date
                    selected_session_dates.add(session_date)
                foreign, foreign_raw, foreign_unit = _flow_value(
                    row,
                    normalized_keys=("foreign_net_buy_krw", "foreign_net_buy_amount"),
                    raw_keys=("frgn_ntby_tr_pbmn", "frgn_ntby_pbmn"),
                )
                institution, institution_raw, institution_unit = _flow_value(
                    row,
                    normalized_keys=("institution_net_buy_krw", "institution_net_buy_amount"),
                    raw_keys=("orgn_ntby_tr_pbmn", "orgn_ntby_pbmn"),
                )
                market_flow = {
                    "market": market,
                    "market_code": (
                        _first_text(row, ("market_code", "marketCode"))
                        or request_params["fid_input_iscd_1"]
                    ),
                    "scope": _flow_scope(row) or "market_wide",
                    "session_date": session_date,
                    "requested_date": requested_date.isoformat(),
                    "freshness": _data_freshness(session_date, requested_date),
                    "source": _first_text(row, ("source",)) or "kis",
                    "request_params": dict(request_params),
                    "foreign_net_buy_krw": _round_or_none(foreign),
                    "institution_net_buy_krw": _round_or_none(institution),
                    "foreign_direction": _direction(foreign),
                    "institution_direction": _direction(institution),
                    "raw_value": {
                        "foreign": _round_or_none(foreign_raw),
                        "institution": _round_or_none(institution_raw),
                    },
                    "normalized_value": {
                        "foreign_net_buy_krw": _round_or_none(foreign),
                        "institution_net_buy_krw": _round_or_none(institution),
                    },
                    "raw_unit": foreign_unit or institution_unit or INVESTOR_FLOW_RAW_UNIT,
                }
                result["by_market"][market] = market_flow
                if foreign is not None:
                    totals["foreign"] += foreign
                    found["foreign"] = True
                    if foreign_raw is not None:
                        raw_totals["foreign"] += foreign_raw
                        raw_found["foreign"] = True
                    if foreign_unit:
                        raw_units.add(foreign_unit)
                if institution is not None:
                    totals["institution"] += institution
                    found["institution"] = True
                    if institution_raw is not None:
                        raw_totals["institution"] += institution_raw
                        raw_found["institution"] = True
                    if institution_unit:
                        raw_units.add(institution_unit)
                if foreign is None and institution is None:
                    failure_reasons.append(
                        "parse_error"
                        if _field_has_value(
                            row,
                            (
                                "foreign_net_buy_krw",
                                "foreign_net_buy_amount",
                                "frgn_ntby_tr_pbmn",
                                "frgn_ntby_pbmn",
                                "institution_net_buy_krw",
                                "institution_net_buy_amount",
                                "orgn_ntby_tr_pbmn",
                                "orgn_ntby_pbmn",
                            ),
                        )
                        else "missing_required_field"
                    )
            except Exception:
                warnings.append(f"investor_flow_{market.lower()}_unavailable")
                failure_reasons.append("api_error")

        if found["foreign"]:
            result["foreign_net_buy_krw"] = round(totals["foreign"], 2)
            result["foreign_direction"] = _direction(totals["foreign"])
        if found["institution"]:
            result["institution_net_buy_krw"] = round(totals["institution"], 2)
            result["institution_direction"] = _direction(totals["institution"])
        result["raw_values"] = {
            "foreign": (
                _round_or_none(raw_totals["foreign"])
                if raw_found["foreign"]
                else None
            ),
            "institution": (
                _round_or_none(raw_totals["institution"])
                if raw_found["institution"]
                else None
            ),
        }
        result["normalized_values_krw"] = {
            "foreign": result["foreign_net_buy_krw"],
            "institution": result["institution_net_buy_krw"],
        }
        result["raw_value"] = dict(result["raw_values"])
        result["normalized_value"] = {
            "foreign_net_buy_krw": result["foreign_net_buy_krw"],
            "institution_net_buy_krw": result["institution_net_buy_krw"],
        }
        if raw_units:
            result["raw_unit"] = (
                next(iter(raw_units))
                if len(raw_units) == 1
                else "mixed"
            )
        if len(selected_session_dates) == 1:
            result["session_date"] = next(iter(selected_session_dates))
        available_session_dates = [
            _as_dict(item).get("session_date")
            for item in result["by_market"].values()
            if _as_dict(item).get("foreign_net_buy_krw") is not None
            or _as_dict(item).get("institution_net_buy_krw") is not None
        ]
        if available_session_dates and all(value is not None for value in available_session_dates):
            result["freshness"] = (
                "current"
                if all(value == requested_date.isoformat() for value in available_session_dates)
                else "latest_completed"
            )
        result["available"] = bool(found["foreign"] or found["institution"])
        if not result["available"]:
            warnings.insert(0, "investor_flow_unavailable")
            result["error_reason"] = _select_error_reason(
                failure_reasons,
                default="empty_response",
            )
        return result, _dedupe(warnings)
    def _get_alpaca_client(self) -> Any | None:
        if self.alpaca_client is not None:
            return self.alpaca_client
        try:
            settings = get_settings()
            # GPT preview needs no US network work when GPT itself is disabled;
            # this also keeps local/read-only preview tests deterministic.
            if not settings.openai_api_key:
                return None
            self.alpaca_client = AlpacaClient()
            return self.alpaca_client
        except Exception:
            return None

    def _kis_is_available(self) -> bool:
        if self.kis_client is None:
            return False
        settings = getattr(self.kis_client, "settings", None)
        if settings is None:
            return True
        return bool(getattr(settings, "kis_enabled", True))


def _completed_rows(rows: list[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
    if not rows:
        return []
    as_of_et = as_of.astimezone(NEW_YORK)
    filtered: list[dict[str, Any]] = []
    has_timestamp = False
    for row in rows:
        timestamp = _coerce_datetime(row.get("timestamp"))
        if timestamp is None:
            filtered.append(row)
            continue
        has_timestamp = True
        timestamp_et = timestamp.astimezone(NEW_YORK)
        if (
            timestamp_et.date() < as_of_et.date()
            or (
                timestamp_et.date() == as_of_et.date()
                and timestamp_et.time() >= time(16, 0)
            )
        ):
            filtered.append(row)
    return filtered if has_timestamp else rows

def _normalize_bars(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("bars") or value.get("data") or []
    if value is None:
        return []
    result: list[dict[str, Any]] = []
    for item in value if isinstance(value, (list, tuple)) else [value]:
        if isinstance(item, dict):
            close = _first_number(item, ("close", "c"))
            timestamp = item.get("timestamp") or item.get("time") or item.get("date")
        else:
            close = _number(getattr(item, "close", None))
            timestamp = getattr(item, "timestamp", None) or getattr(item, "time", None)
        if close is None or close <= 0:
            continue
        parsed_timestamp = _coerce_datetime(timestamp)
        result.append(
            {
                "close": close,
                "timestamp": parsed_timestamp.isoformat() if parsed_timestamp else None,
                "date": parsed_timestamp.date().isoformat() if parsed_timestamp else str(timestamp or "") or None,
            }
        )
    return sorted(result, key=lambda item: str(item.get("timestamp") or item.get("date") or ""))


def _normalize_disclosures(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("items") or value.get("disclosures") or value.get("output") or []
    result: list[dict[str, Any]] = []
    rows = value if isinstance(value, (list, tuple)) else [value]
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _first_text(
            row,
            ("title", "news_title", "news_titl", "hts_pbnt_titl", "news_ctnt"),
        )
        if not title:
            continue
        published_at = _first_text(
            row,
            ("published_at", "timestamp", "news_datetime", "news_dt", "stck_bsop_date"),
        )
        item = {
            "title": title,
            "published_at": published_at,
            "source": _first_text(row, ("source", "news_ofer_entp_name", "orgn_name")),
            "url": _first_text(row, ("url", "news_url", "link")),
        }
        result.append({key: value for key, value in item.items() if value is not None})
        if len(result) >= limit:
            break
    return result


def _symbol_rows(symbols: Any) -> list[Any]:
    if symbols is None:
        return []
    if isinstance(symbols, dict):
        return [symbols]
    return list(symbols) if isinstance(symbols, (list, tuple, set)) else [symbols]


def _snapshot_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key).strip().upper(): item for key, item in value.items()}
    result: dict[str, Any] = {}
    for row in value or []:
        if not isinstance(row, dict):
            continue
        symbol = _symbol_from(row)
        if symbol:
            result[symbol] = row
    return result


def _symbol_from(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("symbol") or value.get("code") or value.get("pdno")

    text = str(value or "").strip().upper()
    return text or None

def _market_from(value: Any) -> str | None:
    if isinstance(value, dict):
        value = (
            value.get("listing_market")
            or value.get("breadth_market")
            or value.get("market")
            or value.get("market_label")
            or value.get("rprs_mrkt_kor_name")
        )
    text = str(value or "").strip().upper()
    if "KOSDAQ" in text or "\ucf54\uc2a4\ub2e5" in text:
        return "KOSDAQ"
    if "KOSPI" in text or "\ucf54\uc2a4\ud53c" in text:
        return "KOSPI"
    return None

def _rows(value: Any) -> list[Any]:
    if isinstance(value, dict):
        for key in ("rows", "data", "items", "output1", "output", "output2"):
            candidate = value.get(key)
            if isinstance(candidate, (list, tuple)):
                return list(candidate)
            if isinstance(candidate, dict):
                return [candidate]
        return [value]
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _last_valid_row(rows: Any) -> dict[str, Any] | None:
    candidates = [row for row in _rows(rows) if isinstance(row, dict)]
    return candidates[-1] if candidates else None


def _row_session_date(row: dict[str, Any]) -> str | None:
    for key in ("session_date", "stck_bsop_date", "date"):
        parsed = _coerce_datetime(row.get(key))
        if parsed is not None:
            return parsed.date().isoformat()
    return None


def _canonical_session_date(value: Any) -> str | None:
    parsed = _coerce_datetime(value)
    return parsed.date().isoformat() if parsed is not None else None


def _flow_scope(row: dict[str, Any]) -> str | None:
    value = _first_text(row, ("scope", "data_scope", "market_scope"))
    if not value:
        return None
    normalized = value.lower().replace("-", "_").replace(" ", "_")
    return "market_wide" if normalized in {"market_wide", "marketwide"} else normalized


def _flow_market(row: dict[str, Any]) -> str | None:
    market = _market_from(row)
    if market:
        return market
    code = _first_text(row, ("market_code", "marketCode"))
    return {
        "KSP": "KOSPI",
        "KSQ": "KOSDAQ",
    }.get((code or "").upper())


def _select_investor_flow_row(
    value: Any,
    *,
    market: str,
    target_date: date,
) -> tuple[dict[str, Any] | None, str | None]:
    candidates = [row for row in _rows(value) if isinstance(row, dict)]
    if not candidates:
        return None, "empty_response"

    explicit_scopes = [
        _flow_scope(row)
        for row in candidates
        if _first_text(row, ("scope", "data_scope", "market_scope"))
    ]
    if explicit_scopes:
        candidates = [
            row for row in candidates
            if _flow_scope(row) == "market_wide"
        ]
        if not candidates:
            return None, "missing_required_field"

    explicit_markets = [
        _flow_market(row)
        for row in candidates
        if _first_text(row, ("market", "listing_market", "breadth_market", "market_code", "marketCode"))
    ]
    if explicit_markets:
        candidates = [row for row in candidates if _flow_market(row) == market]
        if not candidates:
            return None, "unsupported_market_code"

    dated = [
        (session_date, row)
        for row in candidates
        if (session_date := _row_session_date(row)) is not None
    ]
    if dated:
        eligible = [
            item for item in dated
            if _coerce_datetime(item[0]).date() <= target_date
        ]
        if not eligible:
            return None, "stale_data"
        return max(eligible, key=lambda item: item[0])[1], None

    if len(candidates) == 1:
        return candidates[0], None
    return None, "missing_required_field"


def _flow_request_params(market: str, target_date: date) -> dict[str, str]:
    is_kospi = market.upper() == "KOSPI"
    index_code = "0001" if is_kospi else "1001"
    market_code = "KSP" if is_kospi else "KSQ"
    date_value = target_date.strftime("%Y%m%d")
    return {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd": index_code,
        "fid_input_date_1": date_value,
        "fid_input_iscd_1": market_code,
        "fid_input_date_2": date_value,
        "fid_input_iscd_2": index_code,
    }


def _data_freshness(
    session_date: str | None,
    target_date: date,
) -> str:
    if not session_date:
        return "unknown"
    if session_date == target_date.isoformat():
        return "current"
    return "latest_completed"


def _first_valid_row(rows: Any) -> dict[str, Any] | None:
    candidates = [row for row in _rows(rows) if isinstance(row, dict)]
    return candidates[0] if candidates else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _first_number(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in row:
            number = _number(row.get(key))
            if number is not None:
                return number
    return None


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        try:
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _round_or_none(value: float | None) -> float | None:
    return round(float(value), 4) if value is not None else None


def _same_calendar_day(row: dict[str, Any], as_of: datetime) -> bool:
    value = _first_text(row, ("date", "session_date", "stck_bsop_date"))
    parsed = _coerce_datetime(value)
    return parsed is not None and parsed.date() == as_of.date()


def _fx_direction(value: float | None) -> str:
    if value is None:
        return "unknown"
    if abs(value) <= 0.00005:
        return "flat"
    return "krw_weakening" if value > 0 else "krw_strengthening"


def _flow_value(
    row: dict[str, Any],
    *,
    normalized_keys: tuple[str, ...],
    raw_keys: tuple[str, ...],
) -> tuple[float | None, float | None, str | None]:
    for key in raw_keys:
        if key not in row:
            continue
        raw_value = _number(row.get(key))
        if raw_value is None:
            return None, None, INVESTOR_FLOW_RAW_UNIT
        return (
            raw_value * INVESTOR_FLOW_RAW_MULTIPLIER,
            raw_value,
            INVESTOR_FLOW_RAW_UNIT,
        )
    for key in normalized_keys:
        if key not in row:
            continue
        normalized_value = _number(row.get(key))
        if normalized_value is None:
            return None, None, "krw"
        return normalized_value, normalized_value, "krw"
    return None, None, None


def _select_error_reason(
    reasons: list[str],
    *,
    default: str,
) -> str:
    priority = (
        "api_error",
        "empty_response",
        "previous_close_missing",
        "missing_required_field",
        "parse_error",
        "stale_data",
        "unsupported_market_code",
    )
    for candidate in priority:
        if candidate in reasons:
            return candidate
    return default


def _field_has_value(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(
        key in row and row.get(key) is not None and str(row.get(key)).strip()
        for key in keys
    )

def _direction(
    value: float | None,
    *,
    positive: str = "net_buy",
    negative: str = "net_sell",
) -> str:
    if value is None:
        return "unknown"
    if value > 0:
        return positive
    if value < 0:
        return negative
    return "neutral"


def _first_callable(value: Any, names: tuple[str, ...]) -> Callable | None:
    for name in names:
        candidate = getattr(value, name, None)
        if callable(candidate):
            return candidate
    return None


def _call_with_optional_kwargs(method: Callable, *args, **kwargs) -> Any:
    remaining = dict(kwargs)
    while True:
        try:
            return method(*args, **remaining)
        except TypeError:
            if not remaining:
                raise
            remaining.pop(next(iter(remaining)))


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
