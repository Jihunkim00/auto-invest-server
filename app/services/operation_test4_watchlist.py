from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


DEFAULT_COUNT = 50
DEFAULT_PRICE_CAP_KRW = 1_000_000.0
DEFAULT_SOURCE = Path("config/local-watchlists/watchlist_kr.base50.yaml")


class OperationTest4WatchlistError(ValueError):
    pass


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
    if source_path is None:
        candidates.extend(_git_watchlist_candidates(root))
        candidates.append(root / "config/watchlist_kr.yaml")

    for path in candidates:
        if path is None or not path.exists():
            continue
        symbols = _read_symbols(path)
        if len(symbols) >= count:
            return symbols, {
                "source_path": str(path.relative_to(root))
                if path.is_relative_to(root)
                else str(path),
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
) -> QuoteValidation:
    if not isinstance(quote, dict):
        return QuoteValidation(False, ("quote_invalid",), {})

    price = _first_number(quote, "current_price", "price", "stck_prpr", "last")
    name = _first_text(quote, "name", "prdt_name", "hts_kor_isnm")
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

    normalized_name = name.upper()
    if normalized_name.endswith("우") or "우선주" in normalized_name:
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
    selected: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in source_symbols:
        symbol = str(item.get("symbol") or "").strip()
        if symbol in seen:
            exclusions.append({"symbol": symbol, "reasons": ["duplicate_symbol"]})
            continue
        seen.add(symbol)
        try:
            quote = client.get_domestic_stock_price(symbol)
        except Exception as exc:
            exclusions.append(
                {"symbol": symbol, "reasons": [f"quote_read_failed:{exc.__class__.__name__}"]}
            )
            continue
        validation = validate_quote(quote, price_cap_krw=price_cap_krw)
        if not validation.eligible:
            exclusions.append(
                {
                    "symbol": symbol,
                    "reasons": list(validation.reasons),
                    "price_snapshot": validation.snapshot,
                }
            )
            continue
        selected.append(
            {
                "symbol": symbol,
                "name": str(item.get("name") or validation.snapshot.get("name") or ""),
                "market": str(item.get("market") or "KR"),
            }
        )
        if len(selected) >= count:
            break

    if len(selected) != count:
        reason_counts: dict[str, int] = {}
        for item in exclusions:
            for reason in item.get("reasons") or ["unknown_exclusion"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reason_summary = ", ".join(
            f"{reason}={total}"
            for reason, total in sorted(reason_counts.items())
        )
        raise OperationTest4WatchlistError(
            "eligible candidate count is below requested count: "
            f"requested={count}, eligible={len(selected)}, "
            f"excluded={len(exclusions)}, reasons={reason_summary}"
        )

    generated_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    payload = {
        "market": "KR",
        "currency": "KRW",
        "timezone": "Asia/Seoul",
        "operation_test": "test4",
        "generated_at": generated_at,
        "source": source_info,
        "price_cap_krw": float(price_cap_krw),
        "configured_count": len(selected),
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
) -> dict[str, Any]:
    if not path.exists():
        raise OperationTest4WatchlistError(f"watchlist is missing: {path}")
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


def _git_watchlist_candidates(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H", "-20", "--", "config/watchlist_kr.yaml"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    paths: list[Path] = []
    temp_root = Path(tempfile.gettempdir()) / "auto-invest-test4-watchlist-sources"
    temp_root.mkdir(parents=True, exist_ok=True)
    for commit in result.stdout.splitlines():
        commit = commit.strip()
        if not commit:
            continue
        candidate = temp_root / f"watchlist_{commit}.yaml"
        try:
            content = subprocess.run(
                ["git", "show", f"{commit}:config/watchlist_kr.yaml"],
                cwd=root,
                check=True,
                capture_output=True,
            ).stdout
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(content)
        except (OSError, subprocess.SubprocessError):
            continue
        if len(_read_symbols(candidate)) >= DEFAULT_COUNT:
            paths.append(candidate)
    return paths


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