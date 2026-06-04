from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading
from typing import Any

from app.brokers.kis_client import (
    KisClient,
    _as_list,
    _as_dict,
    _first_dict,
    first_float,
    first_present,
)
from app.brokers.base import KisApiError


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
        """Return account state with short TTL and rate-limit fallback.

        - `read_only`: signals caller intent (status/preflight vs live run).
        - `require_fresh`: if True, do not return stale cache beyond TTL.
        """
        now = datetime.now(UTC)
        ttl = float(getattr(self.settings, "kis_account_state_cache_ttl_seconds", 2.0))
        max_stale = float(getattr(self.settings, "kis_account_state_max_stale_seconds", 5.0))

        with self._lock:
            if self._cache:
                fetched_at = self._cache.get("fetched_at")
                age = (now - fetched_at).total_seconds() if fetched_at else None
                if age is not None and age <= ttl and not require_fresh:
                    out = dict(self._cache)
                    out.update({"source": "cache", "cache_age_seconds": age})
                    return out

        # Attempt fresh fetch (bundle balance/positions + open orders)
        try:
            raw_balance = self.client._request_balance()
            # parse balance summary
            summary = _first_dict(raw_balance.get("output2"))
            cash = first_float(summary, ["dnca_tot_amt", "nass_amt", "cash"])
            stock_evaluation_amount = first_float(summary, ["scts_evlu_amt", "tot_evlu_amt"])
            total_asset_value = first_float(summary, ["tot_evlu_amt", "nass_amt", "tot_asst_amt"])
            purchase_amount = first_float(summary, ["pchs_amt_smtl_amt", "pchs_amt"])
            unrealized_pl = first_float(summary, ["evlu_pfls_smtl_amt", "evlu_pfls_amt"])
            unrealized_plpc = None
            try:
                unrealized_plpc = float(first_present(summary, ["asst_icdc_erng_rt", "evlu_pfls_rt"]) or 0.0)
            except Exception:
                unrealized_plpc = 0.0

            balance = {
                "provider": "kis",
                "environment": getattr(self.settings, "kis_env", None),
                "currency": "KRW",
                "cash": cash,
                "total_asset_value": total_asset_value,
                "stock_evaluation_amount": stock_evaluation_amount,
                "purchase_amount": purchase_amount,
                "unrealized_pl": unrealized_pl,
                "unrealized_plpc": unrealized_plpc,
                "raw_status": "ok",
            }

            # parse positions
            rows = _as_list(raw_balance.get("output1"))
            positions = []
            for row in rows:
                item = _as_dict(row)
                qty = first_float(item, ["hldg_qty", "qty"]) or 0.0
                if qty <= 0:
                    continue
                avg_entry_price = first_float(item, ["pchs_avg_pric", "avg_prvs"]) or 0.0
                cost_basis = first_float(item, ["pchs_amt", "pchs_amt_smtl_amt"]) or 0.0
                if cost_basis <= 0 and avg_entry_price > 0:
                    cost_basis = qty * avg_entry_price
                current_price = first_float(item, ["prpr", "stck_prpr"]) or 0.0
                market_value = first_float(item, ["evlu_amt", "scts_evlu_amt"]) or 0.0
                if market_value <= 0 and current_price > 0:
                    market_value = qty * current_price
                unrealized = first_float(item, ["evlu_pfls_amt", "evlu_pfls"]) or 0.0
                unrealized_pct = None
                try:
                    unrealized_pct = float(first_present(item, ["evlu_pfls_rt", "evlu_pfls_erng_rt"]) or 0.0)
                except Exception:
                    unrealized_pct = 0.0

                positions.append(
                    {
                        "symbol": item.get("pdno") or item.get("symbol") or "",
                        "name": item.get("prdt_name") or item.get("name"),
                        "qty": qty,
                        "avg_entry_price": avg_entry_price,
                        "cost_basis": cost_basis,
                        "current_price": current_price,
                        "market_value": market_value,
                        "unrealized_pl": unrealized,
                        "unrealized_plpc": unrealized_pct,
                        "raw": item,
                    }
                )

            # open orders via existing client helper
            open_orders = self.client.list_open_orders()

            state = {
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
            }

            with self._lock:
                self._cache = dict(state)

            out = dict(state)
            out["cache_age_seconds"] = 0.0
            return out

        except KisApiError as exc:
            # If rate limited and we have a recent cache, allow short stale fallback
            details = getattr(exc, "details", {}) or {}
            rate_limited = bool(details.get("kis_rate_limited") or details.get("reason") == "kis_rate_limited")
            with self._lock:
                cached = self._cache
            if rate_limited and cached:
                fetched_at = cached.get("fetched_at")
                age = (now - fetched_at).total_seconds() if fetched_at else None
                if age is not None and age <= max_stale:
                    out = dict(cached)
                    out.update({"source": "cache_after_rate_limit", "cache_age_seconds": age, "rate_limited": True})
                    out.setdefault("warnings", []).append("kis_rate_limited:fallback_cached")
                    return out

            # otherwise, propagate error details in a structured fallback dict
            warnings = [f"account_state_unavailable:{type(exc).__name__}"]
            if rate_limited:
                warnings.append("kis_rate_limited")
            return {
                "provider": "kis",
                "market": "KR",
                "balance": None,
                "positions": [],
                "open_orders": [],
                "recent_orders": [],
                "warnings": warnings,
                "fetch_success": False,
                "fetched_at": now,
                "source": "error",
                "rate_limited": bool(rate_limited),
                "error_details": details,
            }
