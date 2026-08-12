from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading
import time
from typing import Any

from app.brokers.kis_client import (
    KisClient,
    _as_list,
    _as_dict,
    _first_dict,
    first_float,
    first_present,
    optional_first_float,
)
from app.brokers.base import KisApiError
from app.services.kis_payload_sanitizer import sanitize_kis_payload

RETRYABLE_ACCOUNT_CATEGORIES = {"rate_limit", "timeout", "connection_error"}
ACCOUNT_COMPONENTS = {"balance", "positions", "open_orders", "account_aggregation", "unknown"}


class KisAccountStateCacheService:
    """Short-lived account state cache and read-only fetch bundler for KIS.

    Usage: call `KisAccountStateCacheService.get_or_create(client).get_account_state(...)`.
    The service stores a cache on the client instance to allow reuse across
    multiple services during one scheduler run.
    """

    def __init__(self, client: KisClient):
        self.client = client
        self.settings = client.settings
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        # attach to client for reuse
        try:
            setattr(self.client, "_account_state_cache", self)
        except Exception:
            pass

    @staticmethod
    def get_or_create(client: KisClient) -> "KisAccountStateCacheService":
        existing = getattr(client, "_account_state_cache", None)
        if isinstance(existing, KisAccountStateCacheService):
            return existing
        return KisAccountStateCacheService(client)

    def clear(self) -> None:
        with self._lock:
            self._cache = None

    def get_account_state(self, *, read_only: bool = True, require_fresh: bool = False) -> dict[str, Any]:
        del read_only
        now = datetime.now(UTC)
        ttl = float(getattr(self.settings, "kis_account_state_cache_ttl_seconds", 2.0))
        with self._lock:
            cached = dict(self._cache) if self._cache else None
        if cached and cached.get("fetched_at") and not require_fresh:
            age = (now - cached["fetched_at"]).total_seconds()
            if age <= ttl:
                cached.update({"source": "cache", "cache_age_seconds": age})
                return cached
        attempts = max(1, min(int(getattr(self.settings, "kis_account_state_max_attempts", 2) or 2), 3))
        backoff = max(0.0, min(float(getattr(self.settings, "kis_account_state_retry_backoff_seconds", 0.2) or 0.2), 2.0))
        try:
            state = self._read_fresh_account_state(attempts=attempts, backoff=backoff, now=now)
        except _AccountComponentFailure as failure:
            return self._account_unavailable(now, failure, cached=cached)
        with self._lock:
            self._cache = dict(state)
        state["cache_age_seconds"] = 0.0
        return state

    def _read_fresh_account_state(self, *, attempts: int, backoff: float, now: datetime) -> dict[str, Any]:
        (balance, positions), aggregation = self._read_component_with_retry(
            "account_aggregation",
            self._read_balance_and_positions,
            attempts=attempts,
            backoff=backoff,
        )
        open_orders, orders = self._read_component_with_retry(
            "open_orders",
            self.client.list_open_orders,
            attempts=attempts,
            backoff=backoff,
        )
        if not isinstance(open_orders, list) or not all(isinstance(item, dict) for item in open_orders):
            raise _AccountComponentFailure("open_orders", ValueError("open_orders_invalid_response"), attempts=1)
        return {
            "provider": "kis",
            "market": "KR",
            "balance": balance,
            "positions": positions,
            "open_orders": open_orders,
            "recent_orders": [],
            "warnings": [],
            "fetch_success": True,
            "fetched_at": now,
            "source": "fresh",
            "equity": balance.get("total_asset_value"),
            "orderable_cash": balance.get("orderable_cash"),
            "orderable_cash_status": balance.get("orderable_cash_status"),
            "account_state_live_verified": True,
            "account_state_status": "available",
            "account_state_failed_component": None,
            "account_state_attempt_count": max(aggregation["attempt_count"], orders["attempt_count"]),
            "account_state_retryable": False,
            "account_state_error_category": None,
            "account_state_error_code": None,
            "account_state_http_status": None,
            "account_state_last_checked_at": now.isoformat(),
            "account_state_component_attempts": {
                "account_aggregation": aggregation["attempt_count"],
                "open_orders": orders["attempt_count"],
            },
            "account_state_component_diagnostics": {
                "account_aggregation": aggregation,
                "open_orders": orders,
            },
        }

    def _read_component_with_retry(self, component: str, reader, *, attempts: int, backoff: float):
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                value = reader()
                return value, {
                    "component": component,
                    "attempt_count": attempt,
                    "status": "success",
                    "retryable": False,
                }
            except Exception as exc:
                last_exc = exc
                diagnostics = _account_error_diagnostics(exc)
                if attempt >= attempts or not diagnostics["retryable"]:
                    failed_component = component
                    if component == "account_aggregation":
                        text = str(exc).lower()
                        if "position" in text:
                            failed_component = "positions"
                        elif "balance" in text:
                            failed_component = "balance"
                    failure = _AccountComponentFailure(failed_component, exc, attempts=attempt)
                    failure.diagnostics = diagnostics
                    raise failure from exc
                delay = max(backoff, min(float(diagnostics.get("retry_after_seconds") or 0.0), 2.0))
                if delay > 0:
                    time.sleep(delay)
        raise _AccountComponentFailure(component, last_exc or RuntimeError("account_read_failed"), attempts=attempts)

    def _read_balance_and_positions(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        raw = self.client._request_balance()
        if not isinstance(raw, dict) or not isinstance(raw.get("output2"), list) or not isinstance(raw.get("output1"), list):
            raise ValueError("account_aggregation_invalid_response")
        summary = _first_dict(raw["output2"])
        orderable_cash = optional_first_float(summary, ["ord_psbl_cash", "ord_psbl_amt", "ord_psbl_cash_amt"])
        balance = {
            "provider": "kis",
            "environment": getattr(self.settings, "kis_env", None),
            "currency": "KRW",
            "cash": optional_first_float(summary, ["dnca_tot_amt", "cash"]),
            "cash_balance": optional_first_float(summary, ["dnca_tot_amt", "cash"]),
            "withdrawable_cash": optional_first_float(summary, ["wdrw_psbl_tot_amt"]),
            "d1_cash": optional_first_float(summary, ["nxdy_excc_amt"]),
            "d2_cash": optional_first_float(summary, ["d2_cash", "d2_excc_amt"]),
            "orderable_cash": orderable_cash,
            "orderable_cash_source": "kis_balance" if orderable_cash is not None else None,
            "orderable_cash_status": "ok" if orderable_cash is not None else "candidate_required",
            "stock_evaluation_amount": optional_first_float(summary, ["scts_evlu_amt"]),
            "total_asset_value": optional_first_float(summary, ["tot_evlu_amt", "nass_amt", "tot_asst_amt"]),
            "purchase_amount": optional_first_float(summary, ["pchs_amt_smtl_amt", "pchs_amt"]),
            "unrealized_pl": optional_first_float(summary, ["evlu_pfls_smtl_amt", "evlu_pfls_amt"]),
            "unrealized_plpc": _safe_account_float(first_present(summary, ["asst_icdc_erng_rt", "evlu_pfls_rt"])),
            "raw_status": "ok",
        }
        positions = []
        for raw_row in raw["output1"]:
            if not isinstance(raw_row, dict):
                raise ValueError("positions_invalid_response")
            item = _as_dict(raw_row)
            qty = first_float(item, ["hldg_qty", "qty"]) or 0.0
            if qty <= 0:
                continue
            avg_price = first_float(item, ["pchs_avg_pric", "avg_prvs"]) or 0.0
            cost_basis = first_float(item, ["pchs_amt", "pchs_amt_smtl_amt"]) or 0.0
            if cost_basis <= 0 and avg_price > 0:
                cost_basis = qty * avg_price
            current_price = first_float(item, ["prpr", "stck_prpr"]) or 0.0
            market_value = first_float(item, ["evlu_amt", "scts_evlu_amt"]) or 0.0
            if market_value <= 0 and current_price > 0:
                market_value = qty * current_price
            positions.append({
                "symbol": item.get("pdno") or item.get("symbol") or "",
                "name": item.get("prdt_name") or item.get("name"),
                "qty": qty,
                "avg_entry_price": avg_price,
                "cost_basis": cost_basis,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pl": first_float(item, ["evlu_pfls_amt", "evlu_pfls"]) or 0.0,
                "unrealized_plpc": _safe_account_float(first_present(item, ["evlu_pfls_rt", "evlu_pfls_erng_rt"])),
                "raw": sanitize_kis_payload(item),
            })
        return balance, positions

    def _account_unavailable(
        self,
        now: datetime,
        failure: "_AccountComponentFailure",
        *,
        cached: dict[str, Any] | None,
    ) -> dict[str, Any]:
        diagnostics = getattr(failure, "diagnostics", None) or _account_error_diagnostics(failure.original)
        age = None
        if cached and cached.get("fetched_at"):
            age = (now - cached["fetched_at"]).total_seconds()
        max_stale = max(0.0, float(getattr(self.settings, "kis_account_state_max_stale_seconds", 5.0)))
        if diagnostics.get("category") == "rate_limit" and cached and age is not None and age <= max_stale:
            out = dict(cached)
            out.update({
                "source": "cache_after_rate_limit",
                "cache_age_seconds": age,
                "rate_limited": True,
                "account_state_live_verified": False,
                "account_state_status": "stale",
                "account_state_failed_component": failure.component,
                "account_state_attempt_count": failure.attempts,
                "account_state_retryable": bool(diagnostics.get("retryable")),
                "account_state_error_category": diagnostics.get("category"),
                "account_state_error_code": diagnostics.get("error_code"),
                "account_state_http_status": diagnostics.get("http_status"),
                "account_state_last_checked_at": now.isoformat(),
                "account_state_component_attempts": getattr(failure, "component_attempts", {}) or {failure.component: failure.attempts},
            })
            out.setdefault("warnings", []).append("kis_rate_limited:fallback_cached")
            return out
        return {
            "provider": "kis",
            "market": "KR",
            "balance": None,
            "positions": [],
            "open_orders": [],
            "recent_orders": [],
            "warnings": [f"account_state_unavailable:{failure.component}"],
            "fetch_success": False,
            "fetched_at": now,
            "source": "error",
            "rate_limited": diagnostics.get("category") == "rate_limit",
            "error_details": sanitize_kis_payload(diagnostics),
            "account_state_live_verified": False,
            "account_state_status": "unavailable",
            "account_state_failed_component": failure.component if failure.component in ACCOUNT_COMPONENTS else "unknown",
            "account_state_attempt_count": failure.attempts,
            "account_state_retryable": bool(diagnostics.get("retryable")),
            "account_state_error_category": diagnostics.get("category"),
            "account_state_error_code": diagnostics.get("error_code"),
            "account_state_http_status": diagnostics.get("http_status"),
            "account_state_last_checked_at": now.isoformat(),
            "account_state_component_attempts": getattr(failure, "component_attempts", {}) or {failure.component: failure.attempts},
        }


class _AccountComponentFailure(RuntimeError):
    def __init__(self, component: str, original: Exception, *, attempts: int):
        super().__init__(str(original))
        self.component = component
        self.original = original
        self.attempts = attempts
        self.diagnostics: dict[str, Any] = {}
        self.component_attempts: dict[str, int] = {}


def _account_error_diagnostics(exc: Exception) -> dict[str, Any]:
    details = getattr(exc, "details", {}) or {}
    if not isinstance(details, dict):
        details = {}
    code = str(details.get("msg_cd") or details.get("error_code") or "").strip() or None
    status = details.get("http_status")
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    text = str(exc).lower()
    if details.get("kis_rate_limited") or details.get("reason") == "kis_rate_limited" or code in {"EGW00201", "EGW00215"}:
        category = "rate_limit"
    elif details.get("token_expired") or "token expired" in text:
        category = "token_expired"
    elif isinstance(exc, TimeoutError) or "timeout" in text:
        category = "timeout"
    elif isinstance(exc, (ConnectionError, OSError)) or "connection reset" in text:
        category = "connection_error"
    elif status is not None and status >= 400:
        category = "http_error"
    elif isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)) or "invalid" in text or "malformed" in text:
        category = "invalid_response"
    elif isinstance(exc, KisApiError):
        category = "broker_error"
    else:
        category = "unknown"
    retryable = category in RETRYABLE_ACCOUNT_CATEGORIES or (
        category in {"http_error", "broker_error"}
        and ((status is not None and status >= 500) or any(word in text for word in ("gateway", "tempor", "server")))
    )
    return {
        "category": category,
        "error_code": code or (type(exc).__name__ if category == "unknown" else None),
        "http_status": status,
        "retryable": bool(retryable),
        "retry_after_seconds": details.get("retry_after_seconds"),
        "sanitized_message": sanitize_kis_payload(str(exc)[:200]),
    }


def _safe_account_float(value: Any) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and abs(number) != float("inf") else 0.0
