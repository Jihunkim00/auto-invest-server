from __future__ import annotations

import math
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
AUTOMATION_WATCHLIST_SOURCE_FILE = 'config/watchlist_kr_test4_universe.yaml'
AUTOMATION_WATCHLIST_TARGET_COUNT = 50
AUTOMATION_KOSPI_LIMIT = 40
AUTOMATION_KOSDAQ_LIMIT = 10
AUTOMATION_WATCHLIST_MODE = 'automation_daily_kr_watchlist_refresh'


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

    def build_automation_watchlist(
        self,
        profile: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        '''Build the daily Automation KR watchlist without writing a file.'''
        return _build_automation_watchlist(
            self.client,
            profile,
            profile_service=self.profile_service,
            now=now,
        )

    def update_automation_watchlist(
        self,
        profile: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        '''Safely apply one Automation daily KR watchlist candidate.'''
        built = self.build_automation_watchlist(profile, now=now)
        symbols = list(built.get('symbols') or [])
        if not symbols:
            raise KisWatchlistUpdateError(
                'Automation KR watchlist refresh aborted: zero usable symbols.'
            )

        watchlist_path = _resolve_project_path(
            self.profile_service.get_watchlist_path('KR')
        )
        try:
            backup_path = _replace_watchlist_atomically(
                watchlist_path,
                _watchlist_payload(symbols),
            )
        except Exception as exc:
            raise KisWatchlistUpdateError(
                f'Automation KR watchlist refresh file update failed: {exc}.'
            ) from exc

        degraded = bool(
            built.get('price_lookup_failure_count')
            or built.get('final_watchlist_count', 0)
            < AUTOMATION_WATCHLIST_TARGET_COUNT
        )
        return sanitize_kis_payload(
            {
                **built,
                'mode': AUTOMATION_WATCHLIST_MODE,
                'status': 'degraded' if degraded else 'success',
                'result': 'degraded' if degraded else 'success',
                'reason': (
                    'price_lookup_failures'
                    if built.get('price_lookup_failure_count')
                    else (
                        'market_quota_shortage'
                        if degraded
                        else 'automation_watchlist_refreshed'
                    )
                ),
                'watchlist_file': str(watchlist_path),
                'backup_file': (
                    str(backup_path) if backup_path is not None else None
                ),
                'updated': True,
                'real_order_submitted': False,
                'broker_submit_called': False,
                'manual_submit_called': False,
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


def _watchlist_payload(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'market': 'KR',
        'currency': 'KRW',
        'timezone': 'Asia/Seoul',
        'symbols': [
            {
                'symbol': str(item['symbol']).zfill(6),
                'name': item.get('name') or '',
                'market': item.get('market') or 'KR',
            }
            for item in symbols
        ],
    }


def _replace_watchlist_atomically(
    watchlist_path: Path,
    payload: dict[str, Any],
) -> Path | None:
    '''Back up then atomically replace a local watchlist file.'''
    watchlist_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = watchlist_path.with_name(
        f'{watchlist_path.stem}.backup.{timestamp}{watchlist_path.suffix}'
    )
    temp_path = watchlist_path.with_name(
        f'.{watchlist_path.name}.tmp.{timestamp}'
    )
    if watchlist_path.exists():
        shutil.copy2(watchlist_path, backup_path)
    try:
        serialized = yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        temp_path.write_text(serialized, encoding='utf-8')
        temp_path.replace(watchlist_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return backup_path if backup_path.exists() else None


def _build_automation_watchlist(
    client: KisClient,
    profile: dict[str, Any],
    *,
    profile_service: MarketProfileService,
    now: datetime | None = None,
) -> dict[str, Any]:
    del now
    profile_payload = (
        profile.get('profile') if isinstance(profile, dict) else None
    )
    profile_payload = (
        profile_payload if isinstance(profile_payload, dict) else profile
    )
    if not isinstance(profile_payload, dict):
        raise KisWatchlistUpdateError('Automation profile payload is invalid.')

    settings = profile_payload.get('settings')
    effective_settings = profile_payload.get('effective_settings')
    settings = settings if isinstance(settings, dict) else profile_payload
    effective_settings = (
        effective_settings
        if isinstance(effective_settings, dict)
        else settings
    )
    capital = (
        settings.get('capital')
        if isinstance(settings.get('capital'), dict)
        else {}
    )
    effective_capital = (
        effective_settings.get('capital')
        if isinstance(effective_settings.get('capital'), dict)
        else capital
    )
    universe = (
        settings.get('universe')
        if isinstance(settings.get('universe'), dict)
        else {}
    )
    effective_universe = (
        effective_settings.get('universe')
        if isinstance(effective_settings.get('universe'), dict)
        else universe
    )
    configured_max_price = _optional_price_value(
        universe.get('max_price_krw')
        if 'max_price_krw' in universe
        else effective_universe.get('max_price_krw'),
        field='universe.max_price_krw',
        allow_zero=False,
    )
    configured_min_price = _optional_price_value(
        universe.get('min_price_krw')
        if 'min_price_krw' in universe
        else effective_universe.get('min_price_krw'),
        field='universe.min_price_krw',
        allow_zero=True,
    )

    sizing_mode = str(
        capital.get('sizing_mode')
        or effective_capital.get('sizing_mode')
        or 'equity_pct'
    ).strip().lower()
    if sizing_mode not in {'equity_pct', 'fixed_budget'}:
        raise KisWatchlistUpdateError(
            f'Automation profile budget is invalid: unsupported sizing mode {sizing_mode}.'
        )

    raw_max_order = (
        capital.get('max_order_notional_krw')
        if 'max_order_notional_krw' in capital
        else effective_capital.get('max_order_notional_krw')
    )
    if 'max_order_notional_krw' in capital and raw_max_order is None:
        max_order_notional = None
    else:
        effective_max_order = (
            effective_capital.get('max_order_notional_krw')
            if 'max_order_notional_krw' in effective_capital
            else raw_max_order
        )
        _optional_price_value(
            raw_max_order,
            field='capital.max_order_notional_krw',
            allow_zero=False,
        )
        max_order_notional = _optional_price_value(
            effective_max_order,
            field='capital.max_order_notional_krw',
            allow_zero=False,
        )

    fixed_budget = None
    if sizing_mode == 'fixed_budget':
        fixed_value = (
            capital.get('fixed_budget')
            if 'fixed_budget' in capital
            else effective_capital.get('fixed_budget')
        )
        fixed_budget = _optional_price_value(
            fixed_value,
            field='capital.fixed_budget',
            allow_zero=False,
        )

    cap_components = [
        value
        for value in (configured_max_price, max_order_notional, fixed_budget)
        if value is not None
    ]
    if not cap_components:
        raise KisWatchlistUpdateError(
            'Automation profile budget is invalid: no usable price cap.'
        )
    effective_max_price = min(cap_components)

    source_path = _resolve_project_path(AUTOMATION_WATCHLIST_SOURCE_FILE)
    source_rows = _load_automation_source_universe(source_path)
    source_counts = {
        'KOSPI': sum(item['market'] == 'KOSPI' for item in source_rows),
        'KOSDAQ': sum(item['market'] == 'KOSDAQ' for item in source_rows),
    }
    eligible_by_market: dict[str, list[dict[str, Any]]] = {
        'KOSPI': [],
        'KOSDAQ': [],
    }
    price_lookup_success_count = 0
    price_lookup_failure_count = 0
    price_lookup_failures: list[dict[str, str]] = []
    for source_item in source_rows:
        symbol = source_item['symbol']
        try:
            quote = client.get_domestic_stock_price(symbol)
            price = _quote_price(quote)
            if price is None:
                raise ValueError('current_price_unavailable')
        except Exception as exc:
            price_lookup_failure_count += 1
            if len(price_lookup_failures) < 20:
                price_lookup_failures.append(
                    {'symbol': symbol, 'reason': _price_lookup_reason(exc)}
                )
            continue
        price_lookup_success_count += 1
        if configured_min_price is not None and price < configured_min_price:
            continue
        if price > effective_max_price:
            continue
        eligible_by_market[source_item['market']].append(
            {
                **source_item,
                'current_price': price,
            }
        )

    selected_by_market = {
        'KOSPI': eligible_by_market['KOSPI'][:AUTOMATION_KOSPI_LIMIT],
        'KOSDAQ': eligible_by_market['KOSDAQ'][:AUTOMATION_KOSDAQ_LIMIT],
    }
    selected = selected_by_market['KOSPI'] + selected_by_market['KOSDAQ']
    if not selected:
        raise KisWatchlistUpdateError(
            'Automation KR watchlist refresh aborted: zero usable symbols.'
        )
    max_final_price = max(
        (float(item['current_price']) for item in selected),
        default=None,
    )
    over_budget_count = sum(
        float(item['current_price']) > effective_max_price
        for item in selected
    )
    budget_values = [
        value for value in (max_order_notional, fixed_budget)
        if value is not None
    ]
    return {
        'provider': 'kis',
        'market': 'KR',
        'mode': AUTOMATION_WATCHLIST_MODE,
        'source_universe_file': AUTOMATION_WATCHLIST_SOURCE_FILE,
        'source_universe_count': len(source_rows),
        'source_kospi_count': source_counts['KOSPI'],
        'source_kosdaq_count': source_counts['KOSDAQ'],
        'configured_min_price_krw': configured_min_price,
        'configured_max_price_krw': configured_max_price,
        'budget_max_price_krw': min(budget_values) if budget_values else None,
        'effective_max_price_krw': effective_max_price,
        'price_lookup_success_count': price_lookup_success_count,
        'price_lookup_failure_count': price_lookup_failure_count,
        'price_lookup_failures': price_lookup_failures,
        'eligible_kospi_count': len(eligible_by_market['KOSPI']),
        'eligible_kosdaq_count': len(eligible_by_market['KOSDAQ']),
        'selected_kospi_count': len(selected_by_market['KOSPI']),
        'selected_kosdaq_count': len(selected_by_market['KOSDAQ']),
        'final_watchlist_count': len(selected),
        'target_watchlist_count': AUTOMATION_WATCHLIST_TARGET_COUNT,
        'max_price_in_final_watchlist': max_final_price,
        'over_budget_price_count': over_budget_count,
        'symbols': selected,
        'updated': False,
        'real_order_submitted': False,
        'broker_submit_called': False,
        'manual_submit_called': False,
    }


def _load_automation_source_universe(path: Path) -> list[dict[str, Any]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise KisWatchlistUpdateError(
            f'Automation source universe load failed: {path}.'
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('symbols'), list):
        raise KisWatchlistUpdateError(
            f'Automation source universe is malformed: {path}.'
        )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload['symbols']):
        if not isinstance(raw, dict):
            raise KisWatchlistUpdateError(
                f'Automation source universe row {index + 1} is malformed.'
            )
        symbol = _normalize_symbol(raw.get('symbol'))
        market = _normalize_market(raw.get('market'))
        if not symbol or market not in {'KOSPI', 'KOSDAQ'}:
            raise KisWatchlistUpdateError(
                f'Automation source universe row {index + 1} has invalid symbol or market.'
            )
        if symbol in seen:
            raise KisWatchlistUpdateError(
                f'Automation source universe contains duplicate symbol {symbol}.'
            )
        seen.add(symbol)
        rows.append(
            {
                'symbol': symbol,
                'name': str(raw.get('name') or raw.get('source_name') or ''),
                'market': market,
                'source_index': index,
            }
        )
    return rows


def _optional_price_value(
    value: Any,
    *,
    field: str,
    allow_zero: bool,
) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise KisWatchlistUpdateError(
            f'Automation profile value is invalid: {field}.'
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KisWatchlistUpdateError(
            f'Automation profile value is invalid: {field}.'
        ) from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise KisWatchlistUpdateError(
            f'Automation profile value is invalid: {field}.'
        )
    return number


def _quote_price(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ('current_price', 'price', 'stck_prpr'):
        value = payload.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            return number
    return None


def _price_lookup_reason(exc: Exception) -> str:
    text = str(exc).strip()
    return f'{exc.__class__.__name__}:{text}' if text else exc.__class__.__name__
