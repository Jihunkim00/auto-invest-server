from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings

US_SYMBOL_COMPANY_NAMES: dict[str, str] = {
    "NVDA": "NVIDIA Corporation",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
    "GOOG": "Alphabet Inc.",
    "AVGO": "Broadcom Inc.",
    "META": "Meta Platforms, Inc.",
    "TSLA": "Tesla, Inc.",
    "WMT": "Walmart Inc.",
    "MU": "Micron Technology, Inc.",
    "AMD": "Advanced Micro Devices, Inc.",
    "ASML": "ASML Holding N.V.",
    "COST": "Costco Wholesale Corporation",
    "INTC": "Intel Corporation",
    "NFLX": "Netflix, Inc.",
    "CSCO": "Cisco Systems, Inc.",
    "LRCX": "Lam Research Corporation",
    "PLTR": "Palantir Technologies Inc.",
    "AMAT": "Applied Materials, Inc.",
    "TXN": "Texas Instruments Incorporated",
    "KLAC": "KLA Corporation",
    "ARM": "Arm Holdings plc",
    "LIN": "Linde plc",
    "PEP": "PepsiCo, Inc.",
    "TMUS": "T-Mobile US, Inc.",
    "ADI": "Analog Devices, Inc.",
    "AMGN": "Amgen Inc.",
    "ISRG": "Intuitive Surgical, Inc.",
    "GILD": "Gilead Sciences, Inc.",
    "SHOP": "Shopify Inc.",
    "QCOM": "Qualcomm Incorporated",
    "APP": "AppLovin Corporation",
    "SNDK": "SanDisk Corporation",
    "BKNG": "Booking Holdings Inc.",
    "PANW": "Palo Alto Networks, Inc.",
    "MRVL": "Marvell Technology, Inc.",
    "PDD": "PDD Holdings Inc.",
    "WDC": "Western Digital Corporation",
    "HON": "Honeywell International Inc.",
    "STX": "Seagate Technology Holdings plc",
    "SBUX": "Starbucks Corporation",
    "CRWD": "CrowdStrike Holdings, Inc.",
    "VRTX": "Vertex Pharmaceuticals Incorporated",
    "CEG": "Constellation Energy Corporation",
    "INTU": "Intuit Inc.",
    "CMCSA": "Comcast Corporation",
    "MAR": "Marriott International, Inc.",
    "ADBE": "Adobe Inc.",
    "SNPS": "Synopsys, Inc.",
}

_PRIMARY_NAME_KEYS = ("company_name", "companyName", "name", "company")
_EXTRA_NAME_KEYS = ("display_name", "asset_name", "symbol_name", "korean_name")


def build_us_symbol_metadata(config_path: str | None = None) -> dict[str, dict[str, object]]:
    metadata = {
        symbol: _metadata_payload(symbol, company_name)
        for symbol, company_name in US_SYMBOL_COMPANY_NAMES.items()
    }

    for item in _load_watchlist_items(config_path):
        symbol = _symbol_from_payload(item)
        if not symbol:
            continue
        raw = item if isinstance(item, dict) else {"symbol": symbol}
        metadata[symbol] = get_us_symbol_metadata(
            symbol,
            raw,
            metadata_by_symbol=metadata,
        )
    return metadata


def get_us_symbol_metadata(
    symbol: object,
    payload: dict[str, Any] | None = None,
    *,
    metadata_by_symbol: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    normalized_symbol = _normalize_symbol(symbol)
    company_name = get_company_name(
        normalized_symbol,
        market="US",
        payload=payload,
        metadata_by_symbol=metadata_by_symbol,
    )
    return _metadata_payload(normalized_symbol, company_name)


def get_company_name(
    symbol: object,
    market: str = "US",
    payload: dict[str, Any] | None = None,
    *,
    metadata_by_symbol: dict[str, dict[str, object]] | None = None,
) -> str:
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = str(market or "US").strip().upper()
    if normalized_market != "US":
        return _company_name_from_payload(payload, normalized_symbol) or normalized_symbol or "Unknown Company"

    payload_name = _company_name_from_payload(payload, normalized_symbol)
    if payload_name:
        return payload_name

    metadata = (metadata_by_symbol or {}).get(normalized_symbol, {})
    metadata_name = _company_name_from_payload(metadata, normalized_symbol)
    if metadata_name:
        return metadata_name

    static_name = US_SYMBOL_COMPANY_NAMES.get(normalized_symbol)
    if static_name:
        return static_name

    return normalized_symbol or "Unknown Company"


def enrich_us_symbol_metadata(
    payload: dict[str, Any],
    *,
    metadata_by_symbol: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    symbol = _symbol_from_payload(payload)
    row = dict(payload)
    if not symbol:
        return row
    company_name = get_company_name(
        symbol,
        market="US",
        payload=row,
        metadata_by_symbol=metadata_by_symbol,
    )
    row["symbol"] = symbol
    row["company_name"] = company_name
    row["name"] = company_name
    row["market"] = "US"
    row["broker"] = "alpaca"
    return row


def enrich_us_candidate_metadata(
    candidate: dict[str, Any],
    metadata_by_symbol: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    row = enrich_us_symbol_metadata(candidate, metadata_by_symbol=metadata_by_symbol)
    if row.get("symbol"):
        row["broker"] = "alpaca"
        row["market"] = "US"
    return row


def enrich_us_watchlist_payload(
    payload: dict[str, Any],
    metadata_by_symbol: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    metadata = metadata_by_symbol or build_us_symbol_metadata()
    row = dict(payload)
    for key in (
        "watchlist",
        "quant_candidates",
        "top_quant_candidates",
        "researched_candidates",
        "final_candidates",
        "final_ranked_candidates",
        "tied_final_candidates",
        "near_tied_candidates",
    ):
        value = row.get(key)
        if isinstance(value, list):
            row[key] = [
                enrich_us_candidate_metadata(item, metadata)
                if isinstance(item, dict)
                else item
                for item in value
            ]

    for key in (
        "final_best_candidate",
        "second_final_candidate",
        "final_candidate",
        "best_candidate",
    ):
        value = row.get(key)
        if isinstance(value, dict):
            row[key] = enrich_us_candidate_metadata(value, metadata)

    return row


def _load_watchlist_items(config_path: str | None = None) -> list[Any]:
    settings = get_settings()
    path = Path(config_path or settings.watchlist_us_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    if isinstance(raw, dict):
        values = raw.get("symbols") or raw.get("watchlist") or []
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    return values if isinstance(values, list) else []


def _metadata_payload(symbol: str, company_name: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "company_name": company_name,
        "name": company_name,
        "market": "US",
        "broker": "alpaca",
    }


def _company_name_from_payload(payload: dict[str, Any] | None, symbol: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in (*_PRIMARY_NAME_KEYS, *_EXTRA_NAME_KEYS):
        value = _distinct_text(payload.get(key), symbol)
        if value:
            return value
    return None


def _symbol_from_payload(value: object) -> str | None:
    if isinstance(value, dict):
        return _normalize_symbol(_first_text(value.get("symbol"), value.get("ticker")))
    return _normalize_symbol(value)


def _normalize_symbol(value: object) -> str:
    return str(value or "").strip().upper()


def _distinct_text(value: object, symbol: str) -> str | None:
    text = _first_text(value)
    if not text:
        return None
    normalized = text.strip()
    if normalized.upper() == symbol.upper():
        return None
    if normalized.lower() in {"unknown", "unknown company", "n/a", "none"}:
        return None
    return normalized


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "null":
            return text
    return None
