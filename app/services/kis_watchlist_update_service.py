from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.brokers.kis_client import KisClient
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_profile_service import MarketProfileService


TARGET_KR_WATCHLIST_COUNT = 50
KOSPI_TOP_LIMIT = 30
KOSDAQ_TOP_LIMIT = 20
REQUIRED_KR_SYMBOLS = {"005930", "035420"}
MARKET_LABELS = {
    "KOSPI": "코스피",
    "KOSDAQ": "코스닥",
    "KONEX": "코넥스",
    "KR": "한국",
    "US": "미국",
}
BALANCED_KR_GROUP_LABEL = "코스피 Top 30 + 코스닥 Top 20"
BALANCED_KR_MODE_PREVIEW = "kr_watchlist_balanced_update_preview"
BALANCED_KR_MODE_APPLIED = "kr_watchlist_balanced_update_applied"
BALANCED_KR_GROUPS = (
    {"market": "KOSPI", "target_count": KOSPI_TOP_LIMIT},
    {"market": "KOSDAQ", "target_count": KOSDAQ_TOP_LIMIT},
)
REQUIRED_KR_SYMBOL_FALLBACKS = {
    "005930": {
        "symbol": "005930",
        "name": "삼성전자",
        "english_name": "Samsung Electronics",
        "market": "KOSPI",
    },
    "035420": {
        "symbol": "035420",
        "name": "NAVER",
        "english_name": "NAVER",
        "market": "KOSPI",
    },
}


class KisWatchlistUpdateError(ValueError):
    """Raised when a read-only KIS watchlist update cannot be applied."""


class KisWatchlistUpdateService:
    """Read-only KIS watchlist config update helper.

    This service updates only local watchlist configuration. It never builds or
    submits order payloads.
    """

    def __init__(
        self,
        client: KisClient,
        *,
        profile_service: MarketProfileService | None = None,
    ):
        self.client = client
        self.profile_service = profile_service or MarketProfileService()

    def preview_kosdaq_top50(self) -> dict[str, Any]:
        """Compatibility wrapper for the legacy KOSDAQ top-50 route name."""
        return self.preview_balanced_kr_watchlist()

    def update_kosdaq_top50(self) -> dict[str, Any]:
        """Compatibility wrapper for the legacy KOSDAQ top-50 route name."""
        return self.update_balanced_kr_watchlist()

    def preview_balanced_kr_watchlist(self) -> dict[str, Any]:
        rankings = self._fetch_balanced_rankings()
        symbols = _combined_symbols(rankings)
        return sanitize_kis_payload(
            {
                "provider": "kis",
                "market": "KR",
                "source_market": "KR",
                "source_market_label": korean_market_label("KR"),
                "mode": BALANCED_KR_MODE_PREVIEW,
                "group_label": BALANCED_KR_GROUP_LABEL,
                "groups": _group_summaries(rankings),
                "count": len(symbols),
                "target_count": TARGET_KR_WATCHLIST_COUNT,
                "required_symbols_present": _required_symbols_present(symbols),
                "ranking_symbol_count": len(symbols),
                "symbols": symbols,
                "updated": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def update_balanced_kr_watchlist(self) -> dict[str, Any]:
        rankings = self._fetch_balanced_rankings()
        watchlist_path = _resolve_project_path(
            self.profile_service.get_watchlist_path("KR")
        )
        current_symbols = _load_current_watchlist_symbols(watchlist_path)
        built = _build_balanced_kr_watchlist(
            ranking_by_market=rankings,
            current_symbols=current_symbols,
        )
        symbols = built["symbols"]
        if (
            len(symbols) != TARGET_KR_WATCHLIST_COUNT
            or not built["required_symbols_present"]
            or not _group_counts_are_complete(built["groups"])
        ):
            raise KisWatchlistUpdateError(_balanced_update_error(built))

        watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = watchlist_path.with_name(
            f"{watchlist_path.stem}.backup.{timestamp}{watchlist_path.suffix}"
        )
        if watchlist_path.exists():
            shutil.copy2(watchlist_path, backup_path)

        payload = {
            "market": "KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
            "symbols": [
                {
                    "symbol": str(item["symbol"]).zfill(6),
                    "name": item.get("name") or "",
                    "market": item.get("market") or "KR",
                }
                for item in symbols
            ],
        }
        temp_path = watchlist_path.with_name(
            f".{watchlist_path.name}.tmp.{timestamp}"
        )
        temp_path.write_text(
            yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        temp_path.replace(watchlist_path)

        return sanitize_kis_payload(
            {
                "provider": "kis",
                "market": "KR",
                "source_market": "KR",
                "source_market_label": korean_market_label("KR"),
                "mode": BALANCED_KR_MODE_APPLIED,
                "group_label": BALANCED_KR_GROUP_LABEL,
                "groups": built["groups"],
                "watchlist_file": str(watchlist_path),
                "backup_file": str(backup_path) if backup_path.exists() else None,
                "updated": True,
                "count": len(symbols),
                "target_count": TARGET_KR_WATCHLIST_COUNT,
                "required_symbols_present": built["required_symbols_present"],
                "symbols": symbols,
                "added_symbols": built["added_symbols"],
                "removed_symbols": built["removed_symbols"],
                "kept_symbols": built["kept_symbols"],
                "deduped_symbols": built["deduped_symbols"],
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def _fetch_balanced_rankings(self) -> dict[str, list[dict[str, Any]]]:
        return {
            group["market"]: self._fetch_market_ranking(
                market=group["market"],
                limit=int(group["target_count"]),
            )
            for group in BALANCED_KR_GROUPS
        }

    def _fetch_market_ranking(
        self,
        *,
        market: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_market = _normalize_market(market)
        rows = self.client.get_domestic_market_cap_ranking(
            market=normalized_market,
            limit=limit,
        )
        normalized = []
        seen: set[str] = set()
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("symbol"))
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("name") or ""),
                    "market": normalized_market,
                    "market_label": korean_market_label(normalized_market),
                    "market_cap": row.get("market_cap"),
                    "rank": int(row.get("rank") or index),
                }
            )
            if len(normalized) >= limit:
                break
        return normalized


def korean_market_label(code: Any) -> str:
    normalized = _normalize_market(code)
    return MARKET_LABELS.get(normalized, normalized)


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    if len(digits) > 6:
        digits = digits[-6:]
    return digits.zfill(6)


def _build_balanced_kr_watchlist(
    *,
    ranking_by_market: dict[str, list[dict[str, Any]]],
    current_symbols: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_by_market: dict[str, list[dict[str, Any]]] = {
        group["market"]: [] for group in BALANCED_KR_GROUPS
    }
    selected_symbols: set[str] = set()
    deduped: list[dict[str, Any]] = []
    current_by_symbol: dict[str, dict[str, Any]] = {}
    current_by_market: dict[str, list[dict[str, Any]]] = {
        group["market"]: [] for group in BALANCED_KR_GROUPS
    }

    for raw in current_symbols:
        item = _normalize_watchlist_item(raw, fallback_market="KR")
        if item is None:
            continue
        current_by_symbol.setdefault(item["symbol"], item)
        if item["market"] in current_by_market:
            current_by_market[item["market"]].append(item)

    def append_item(raw: dict[str, Any], *, market: str, source: str) -> bool:
        symbol = _normalize_symbol(raw.get("symbol"))
        if not symbol:
            return False
        item = _normalize_watchlist_item(raw, fallback_market=market)
        if item is None:
            return False
        item["market"] = market
        item = _with_market_label(item)
        if symbol in selected_symbols:
            deduped.append({**item, "duplicate_source": source})
            return False
        if len(selected_by_market[market]) >= _target_for_market(market):
            return False
        selected_symbols.add(symbol)
        selected_by_market[market].append(item)
        return True

    for group in BALANCED_KR_GROUPS:
        market = group["market"]
        for ranked in ranking_by_market.get(market, []):
            append_item(ranked, market=market, source=f"{market.lower()}_ranking")
        if market == "KOSPI":
            _ensure_required_symbols(
                selected_by_market=selected_by_market,
                selected_symbols=selected_symbols,
                current_by_symbol=current_by_symbol,
            )
        for current in current_by_market[market]:
            append_item(current, market=market, source=f"{market.lower()}_fallback")

    symbols = [
        item
        for group in BALANCED_KR_GROUPS
        for item in selected_by_market[group["market"]]
    ]
    old_by_symbol = {
        item["symbol"]: item
        for item in current_symbols
        if isinstance(item, dict) and item.get("symbol")
    }
    new_by_symbol = {item["symbol"]: item for item in symbols}
    old_symbols = set(old_by_symbol)
    new_symbols = set(new_by_symbol)
    groups = [
        _group_summary(
            market=group["market"],
            count=len(selected_by_market[group["market"]]),
            ranking_count=len(ranking_by_market.get(group["market"], [])),
        )
        for group in BALANCED_KR_GROUPS
    ]

    return {
        "symbols": symbols,
        "groups": groups,
        "required_symbols_present": _required_symbols_present(symbols),
        "added_symbols": [
            item for item in symbols if item["symbol"] not in old_symbols
        ],
        "removed_symbols": [
            old_by_symbol[symbol]
            for symbol in old_by_symbol
            if symbol not in new_symbols
        ],
        "kept_symbols": [
            item for item in symbols if item["symbol"] in old_symbols
        ],
        "deduped_symbols": deduped,
    }


def _ensure_required_symbols(
    *,
    selected_by_market: dict[str, list[dict[str, Any]]],
    selected_symbols: set[str],
    current_by_symbol: dict[str, dict[str, Any]],
) -> None:
    market = "KOSPI"
    target = _target_for_market(market)
    selected = selected_by_market[market]
    for symbol in sorted(REQUIRED_KR_SYMBOLS):
        if symbol in selected_symbols:
            continue
        raw = current_by_symbol.get(symbol) or REQUIRED_KR_SYMBOL_FALLBACKS[symbol]
        item = _normalize_watchlist_item(raw, fallback_market=market)
        if item is None:
            item = dict(REQUIRED_KR_SYMBOL_FALLBACKS[symbol])
        item["symbol"] = symbol
        item["market"] = market
        item = _with_market_label(item)
        if len(selected) >= target:
            removed_index = next(
                (
                    index
                    for index in range(len(selected) - 1, -1, -1)
                    if selected[index]["symbol"] not in REQUIRED_KR_SYMBOLS
                ),
                None,
            )
            if removed_index is None:
                continue
            removed = selected.pop(removed_index)
            selected_symbols.discard(removed["symbol"])
        selected.append(item)
        selected_symbols.add(symbol)


def _combined_symbols(
    ranking_by_market: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        item
        for group in BALANCED_KR_GROUPS
        for item in ranking_by_market.get(group["market"], [])
    ]


def _group_summaries(
    ranking_by_market: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        _group_summary(
            market=group["market"],
            count=len(ranking_by_market.get(group["market"], [])),
            ranking_count=len(ranking_by_market.get(group["market"], [])),
        )
        for group in BALANCED_KR_GROUPS
    ]


def _group_summary(
    *,
    market: str,
    count: int,
    ranking_count: int,
) -> dict[str, Any]:
    return {
        "market": market,
        "market_label": korean_market_label(market),
        "target_count": _target_for_market(market),
        "count": count,
        "ranking_symbol_count": ranking_count,
    }


def _required_symbols_present(symbols: list[dict[str, Any]]) -> bool:
    present = {str(item.get("symbol") or "") for item in symbols}
    return REQUIRED_KR_SYMBOLS.issubset(present)


def _group_counts_are_complete(groups: list[dict[str, Any]]) -> bool:
    return all(
        int(group.get("count") or 0) == int(group.get("target_count") or 0)
        for group in groups
    )


def _balanced_update_error(built: dict[str, Any]) -> str:
    groups = built.get("groups") or []
    group_text = ", ".join(
        f"{group.get('market')} {group.get('count')}/{group.get('target_count')}"
        for group in groups
    )
    required_text = (
        "required symbols present"
        if built.get("required_symbols_present")
        else "required symbols missing"
    )
    return (
        "Balanced KR watchlist update aborted: "
        f"only {len(built.get('symbols') or [])}/{TARGET_KR_WATCHLIST_COUNT} "
        f"symbols available ({group_text}; {required_text})."
    )


def _target_for_market(market: str) -> int:
    normalized = _normalize_market(market)
    for group in BALANCED_KR_GROUPS:
        if group["market"] == normalized:
            return int(group["target_count"])
    return 0


def _load_current_watchlist_symbols(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise KisWatchlistUpdateError(f"Invalid watchlist YAML: {path}.") from exc

    if isinstance(payload, dict):
        raw_symbols = payload.get("symbols") or payload.get("watchlist") or []
    elif isinstance(payload, list):
        raw_symbols = payload
    else:
        raw_symbols = []

    normalized = []
    for raw in raw_symbols if isinstance(raw_symbols, list) else []:
        item = _normalize_watchlist_item(raw, fallback_market="KR")
        if item is not None:
            normalized.append(item)
    return normalized


def _normalize_watchlist_item(
    raw: Any,
    *,
    fallback_market: str,
) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        symbol = _normalize_symbol(raw.get("symbol"))
        if not symbol:
            return None
        market = _normalize_market(raw.get("market") or fallback_market)
        item = {
            "symbol": symbol,
            "name": str(raw.get("name") or ""),
            "market": market,
        }
        if raw.get("english_name"):
            item["english_name"] = str(raw["english_name"])
        if raw.get("market_cap") is not None:
            item["market_cap"] = raw.get("market_cap")
        if raw.get("rank") is not None:
            item["rank"] = raw.get("rank")
        return _with_market_label(item)

    symbol = _normalize_symbol(raw)
    if not symbol:
        return None
    return _with_market_label(
        {
            "symbol": symbol,
            "name": "",
            "market": _normalize_market(fallback_market),
        }
    )


def _with_market_label(item: dict[str, Any]) -> dict[str, Any]:
    market = _normalize_market(item.get("market"))
    item["market"] = market
    item["market_label"] = korean_market_label(market)
    return item


def _normalize_market(value: Any) -> str:
    return str(value or "KR").strip().upper()


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path
