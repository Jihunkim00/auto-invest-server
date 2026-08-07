from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from app.services.operation_test4_universe import load_operation_test4_universe


DEFAULT_COUNT = 50
DEFAULT_PRICE_CAP_KRW = 1_000_000.0
DEFAULT_SOURCE = Path("config/watchlist_kr_test4_universe.yaml")
KR_TZ = ZoneInfo("Asia/Seoul")


class OperationTest4WatchlistError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class QuoteValidation:
    eligible: bool
    reasons: tuple[str, ...]
    snapshot: dict[str, Any]


def load_source_symbols(
    root: Path,
    *,
    count: int = DEFAULT_COUNT,
    source_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = [source_path] if source_path is not None else [root / DEFAULT_SOURCE]

    for path in candidates:
        if path is None or not path.exists():
            continue
        if path.name == DEFAULT_SOURCE.name:
            try:
                universe = load_operation_test4_universe(path, minimum_count=count)
            except ValueError as exc:
                raise OperationTest4WatchlistError(
                    f"invalid Test4 source universe: {exc}"
                ) from exc
            return universe["symbols"], {
                "source_universe_file": str(path.relative_to(root)).replace("\\", "/")
                if path.is_relative_to(root)
                else str(path).replace("\\", "/"),
                "source_universe_count": universe["count"],
                "source_count": universe["count"],
                "source_priority": 1,
                "source_counts": universe.get("source_counts") or {},
            }
        symbols = _read_symbols(path)
        if len(symbols) >= count:
            return symbols, {
                "source_path": str(path.relative_to(root)).replace("\\", "/")
                if path.is_relative_to(root)
                else str(path).replace("\\", "/"),
                "source_count": len(symbols),
                "source_priority": candidates.index(path) + 1,
            }

    raise OperationTest4WatchlistError(
        f"no source watchlist contains at least {count} valid candidates"
    )


def validate_quote(
    quote: dict[str, Any],
    *,
    price_cap_krw: float = DEFAULT_PRICE_CAP_KRW,
    source_name: str | None = None,
) -> QuoteValidation:
    if not isinstance(quote, dict):
        return QuoteValidation(False, ("quote_invalid",), {})

    price = _first_number(quote, "current_price", "price", "stck_prpr", "last")
    name = _first_text(quote, "name", "prdt_name", "hts_kor_isnm")
    source_name_text = str(source_name or "").strip()
    reasons: list[str] = []
    if price is None or price <= 0:
        reasons.append("invalid_quote_price")
    elif price >= float(price_cap_krw):
        reasons.append("price_cap_exceeded")

    for key, reason in (
        ("is_trading_halted", "trading_halted"),
        ("trading_halted", "trading_halted"),
        ("halted", "trading_halted"),
        ("is_management", "management_stock"),
        ("management", "management_stock"),
        ("is_order_restricted", "order_restricted"),
        ("order_restricted", "order_restricted"),
        ("is_etf", "etf_excluded"),
        ("is_etn", "etn_excluded"),
        ("is_elw", "elw_excluded"),
        ("is_preferred", "preferred_stock_excluded"),
    ):
        if _truthy(quote.get(key)):
            reasons.append(reason)

    instrument_type = " ".join(
        str(quote.get(key) or "")
        for key in ("instrument_type", "security_type", "product_type", "prd_type")
    ).upper()
    for marker, reason in (
        ("ETF", "etf_excluded"),
        ("ETN", "etn_excluded"),
        ("ELW", "elw_excluded"),
        ("PREFERRED", "preferred_stock_excluded"),
        ("우선", "preferred_stock_excluded"),
    ):
        if marker in instrument_type:
            reasons.append(reason)

    normalized_names = (name.upper(), source_name_text.upper())
    if any(
        normalized_name.endswith("우") or "우선주" in normalized_name
        for normalized_name in normalized_names
    ):
        reasons.append("preferred_stock_excluded")

    snapshot = {
        "current_price": price,
        "name": name,
        "raw_status": quote.get("raw_status"),
    }
    for key in (
        "is_trading_halted",
        "is_management",
        "is_order_restricted",
        "is_etf",
        "is_etn",
        "is_elw",
        "is_preferred",
        "instrument_type",
        "security_type",
        "product_type",
    ):
        if key in quote:
            snapshot[key] = quote.get(key)
    return QuoteValidation(not reasons, tuple(dict.fromkeys(reasons)), snapshot)


def build_operation_test4_watchlist(
    *,
    root: Path,
    output_path: Path,
    count: int = DEFAULT_COUNT,
    price_cap_krw: float = DEFAULT_PRICE_CAP_KRW,
    client: Any,
    now: datetime | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    source_symbols, source_info = load_source_symbols(
        root,
        count=count,
        source_path=source_path,
    )
    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen: set[str] = set()
    quote_checked_count = 0
    for item in source_symbols:
        symbol = str(item.get("symbol") or "").strip()
        if symbol in seen:
            exclusions.append({"symbol": symbol, "reasons": ["duplicate_symbol"]})
            continue
        seen.add(symbol)
        quote_checked_count += 1
        try:
            quote = client.get_domestic_stock_price(symbol)
        except Exception as exc:
            exclusions.append(
                {"symbol": symbol, "reasons": [f"quote_read_failed:{exc.__class__.__name__}"]}
            )
            continue
        validation = validate_quote(
            quote,
            price_cap_krw=price_cap_krw,
            source_name=str(item.get("name") or ""),
        )
        if not validation.eligible:
            exclusions.append(
                {
                    "symbol": symbol,
                    "reasons": list(validation.reasons),
                    "price_snapshot": validation.snapshot,
                }
            )
            continue
        eligible.append(
            {
                "symbol": symbol,
                "name": str(item.get("name") or validation.snapshot.get("name") or ""),
                "source_name": str(
                    item.get("source_name") or item.get("name") or ""
                ),
                "source": str(item.get("source") or source_info.get("source_universe_file") or ""),
                "market": str(item.get("market") or "KR"),
            }
        )

    if len(eligible) < count:
        reason_counts: dict[str, int] = {}
        for item in exclusions:
            for reason in item.get("reasons") or ["unknown_exclusion"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reason_summary = ", ".join(
            f"{reason}={total}"
            for reason, total in sorted(reason_counts.items())
        )
        details = {
            "source_universe_count": len(source_symbols),
            "quote_checked_count": quote_checked_count,
            "eligible_count": len(eligible),
            "selected_count": 0,
            "reserve_eligible_count": 0,
            "excluded_count": len(exclusions),
            "exclusion_reasons": reason_counts,
            "exclusion_symbols": [item.get("symbol") for item in exclusions],
        }
        raise OperationTest4WatchlistError(
            "eligible candidate count is below requested count: "
            f"requested={count}, eligible={len(eligible)}, "
            f"excluded={len(exclusions)}, reasons={reason_summary}",
            details=details,
        )

    selected = eligible[:count]
    reserve_eligible_count = max(0, len(eligible) - count)
    generated_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    reason_counts: dict[str, int] = {}
    for item in exclusions:
        for reason in item.get("reasons") or ["unknown_exclusion"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    payload = {
        "market": "KR",
        "currency": "KRW",
        "timezone": "Asia/Seoul",
        "operation_test": "test4",
        "generated_at": generated_at,
        "source": source_info,
        "source_universe_file": source_info.get("source_universe_file"),
        "source_universe_count": len(source_symbols),
        "price_cap_krw": float(price_cap_krw),
        "configured_count": len(selected),
        "quote_checked_count": quote_checked_count,
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "reserve_eligible_count": reserve_eligible_count,
        "excluded_count": len(exclusions),
        "exclusion_reasons": reason_counts,
        "selected_symbols": [item["symbol"] for item in selected],
        "symbols": selected,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {
        **payload,
        "excluded_count": len(exclusions),
        "exclusions": exclusions,
        "output_path": str(output_path),
    }


def load_operation_test4_watchlist(
    path: Path,
    *,
    count: int = DEFAULT_COUNT,
    price_cap_krw: float | None = None,
    require_fresh: bool = False,
    today_kst: date | None = None,
) -> dict[str, Any]:
    if not path.exists():
        raise OperationTest4WatchlistError(
            f"watchlist is missing: {path}",
            details={"reason": "test4_watchlist_missing"},
        )
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise OperationTest4WatchlistError("watchlist must be a mapping")
    rows = payload.get("symbols")
    if not isinstance(rows, list):
        raise OperationTest4WatchlistError("watchlist symbols must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise OperationTest4WatchlistError("watchlist contains a non-mapping symbol")
        symbol = str(row.get("symbol") or "").strip()
        if not re.fullmatch(r"\d{6}", symbol):
            raise OperationTest4WatchlistError(f"invalid KR symbol: {symbol}")
        if symbol in seen:
            raise OperationTest4WatchlistError(f"duplicate KR symbol: {symbol}")
        seen.add(symbol)
        normalized.append({**row, "symbol": symbol})
    if len(normalized) != count:
        raise OperationTest4WatchlistError(
            f"watchlist count mismatch: expected={count}, actual={len(normalized)}"
        )
    selected_count = payload.get("selected_count", payload.get("configured_count"))
    if selected_count != count:
        raise OperationTest4WatchlistError(
            f"watchlist selected_count mismatch: expected={count}, actual={selected_count}",
            details={"reason": "test4_watchlist_count_mismatch"},
        )
    if price_cap_krw is not None:
        try:
            metadata_cap = float(payload.get("price_cap_krw"))
        except (TypeError, ValueError):
            metadata_cap = None
        if metadata_cap is None or abs(metadata_cap - float(price_cap_krw)) > 1e-9:
            raise OperationTest4WatchlistError(
                "watchlist price cap metadata mismatch",
                details={"reason": "test4_watchlist_price_cap_mismatch"},
            )
    if require_fresh:
        generated_at = str(payload.get("generated_at") or "").strip()
        try:
            generated_date = datetime.fromisoformat(generated_at).astimezone(KR_TZ).date()
        except (TypeError, ValueError):
            generated_date = None
        expected_date = today_kst or datetime.now(KR_TZ).date()
        if generated_date != expected_date:
            raise OperationTest4WatchlistError(
                "watchlist snapshot is stale",
                details={"reason": "test4_watchlist_stale"},
            )
    return {**payload, "symbols": normalized, "count": len(normalized)}


def _read_symbols(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get("symbols") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip()
        if symbol.isdigit():
            symbol = symbol.zfill(6)
        if not re.fullmatch(r"\d{6}", symbol) or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append({**row, "symbol": symbol})
    return normalized


def _first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(payload.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and value not in {float("inf"), float("-inf")}:
            return value
    return None


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "halted", "restricted"}