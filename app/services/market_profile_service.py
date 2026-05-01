from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings


class MarketProfileError(ValueError):
    """Raised when a market profile or market-specific symbol is invalid."""


@dataclass(frozen=True)
class MarketProfile:
    market: str
    label: str
    broker_provider: str
    currency: str
    timezone: str
    watchlist_file: str
    reference_sites_file: str
    symbol_format: str
    enabled_for_trading: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketProfileService:
    def __init__(self, config_path: str | None = None):
        settings = get_settings()
        self.config_path = config_path or settings.market_profiles_config_path
        self._root = Path(__file__).resolve().parents[2]

    def list_profiles(self) -> list[dict[str, Any]]:
        payload = self._load_config()
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict):
            return []

        profiles = []
        for market in sorted(markets):
            profiles.append(self._profile_from_config(market, markets[market]).to_dict())
        return profiles

    def get_profile(self, market: str | None = None) -> MarketProfile:
        payload = self._load_config()
        selected_market = self._normalize_market(
            market or payload.get("default_market") or "US"
        )
        markets = payload.get("markets") or {}
        if not isinstance(markets, dict) or selected_market not in markets:
            raise MarketProfileError(f"Unknown market profile: {selected_market}.")
        return self._profile_from_config(selected_market, markets[selected_market])

    def get_default_profile(self) -> MarketProfile:
        return self.get_profile(None)

    def get_watchlist_path(self, market: str | None = None) -> str:
        return self.get_profile(market).watchlist_file

    def get_reference_sites_path(self, market: str | None = None) -> str:
        return self.get_profile(market).reference_sites_file

    def normalize_symbol(self, symbol: str, market: str | None = None) -> str:
        profile = self.get_profile(market)
        value = str(symbol or "").strip()

        if profile.symbol_format == "6_digit_numeric":
            if not re.fullmatch(r"\d{6}", value):
                raise MarketProfileError(
                    f"{profile.market} symbols must be exactly 6 numeric digits."
                )
            return value

        normalized = value.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized):
            raise MarketProfileError(
                f"{profile.market} symbols must be uppercase ticker symbols."
            )
        return normalized

    def validate_symbol_for_market(self, symbol: str, market: str | None = None) -> bool:
        self.normalize_symbol(symbol, market)
        return True

    def load_watchlist(self, market: str | None = None) -> dict[str, Any]:
        profile = self.get_profile(market)
        payload = self._load_yaml_file(profile.watchlist_file)
        raw_symbols = []
        if isinstance(payload, dict):
            raw_symbols = payload.get("symbols") or payload.get("watchlist") or []
        elif isinstance(payload, list):
            raw_symbols = payload

        symbols: list[dict[str, Any]] = []
        rows = raw_symbols if isinstance(raw_symbols, list) else []
        for raw in rows:
            item = self._normalize_watchlist_item(raw, profile)
            if item is not None:
                symbols.append(item)

        return {
            "market": profile.market,
            "currency": profile.currency,
            "timezone": profile.timezone,
            "watchlist_file": profile.watchlist_file,
            "count": len(symbols),
            "symbols": symbols,
        }

    def load_reference_sites(self, market: str | None = None) -> dict[str, Any]:
        profile = self.get_profile(market)
        payload = self._load_yaml_file(profile.reference_sites_file)
        sources = []
        if isinstance(payload, dict):
            raw_sources = payload.get("sources")
            if raw_sources is None:
                raw_sources = payload.get("sites")
            if isinstance(raw_sources, list):
                sources = [item for item in raw_sources if isinstance(item, dict)]

        return {
            "market": profile.market,
            "currency": profile.currency,
            "timezone": profile.timezone,
            "reference_sites_file": profile.reference_sites_file,
            "count": len(sources),
            "sources": sources,
        }

    def get_default_market_key(self) -> str:
        payload = self._load_config()
        return self._normalize_market(payload.get("default_market") or "US")

    def _load_config(self) -> dict[str, Any]:
        payload = self._load_yaml_file(self.config_path)
        if not isinstance(payload, dict):
            raise MarketProfileError("Market profile config must be a mapping.")
        return payload

    def _load_yaml_file(self, path_value: str) -> Any:
        path = Path(path_value)
        if not path.is_absolute():
            path = self._root / path
        if not path.exists():
            raise MarketProfileError(f"Market profile config file not found: {path_value}.")
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise MarketProfileError(f"Invalid YAML config file: {path_value}.") from exc

    def _profile_from_config(self, market: str, raw: Any) -> MarketProfile:
        if not isinstance(raw, dict):
            raise MarketProfileError(f"Invalid market profile: {market}.")

        required = [
            "label",
            "broker_provider",
            "currency",
            "timezone",
            "watchlist_file",
            "reference_sites_file",
            "symbol_format",
        ]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise MarketProfileError(
                f"Market profile {market} is missing: {', '.join(missing)}."
            )

        return MarketProfile(
            market=self._normalize_market(market),
            label=str(raw["label"]),
            broker_provider=str(raw["broker_provider"]),
            currency=str(raw["currency"]),
            timezone=str(raw["timezone"]),
            watchlist_file=str(raw["watchlist_file"]),
            reference_sites_file=str(raw["reference_sites_file"]),
            symbol_format=str(raw["symbol_format"]),
            enabled_for_trading=bool(raw.get("enabled_for_trading", False)),
        )

    def _normalize_watchlist_item(
        self,
        raw: Any,
        profile: MarketProfile,
    ) -> dict[str, Any] | None:
        if isinstance(raw, dict):
            raw_symbol = raw.get("symbol")
            if not raw_symbol:
                return None
            symbol = self.normalize_symbol(str(raw_symbol), profile.market)
            item = dict(raw)
            item["symbol"] = symbol
            item.setdefault("market", profile.market)
            return item

        if raw:
            symbol = self.normalize_symbol(str(raw), profile.market)
            return {"symbol": symbol, "market": profile.market}
        return None

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        return str(market or "US").strip().upper()
