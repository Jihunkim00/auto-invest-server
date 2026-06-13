from pathlib import Path

import yaml

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.services.ai_signal_service import AISignalService
from app.services.entry_readiness_service import evaluate_entry_readiness
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.market_profile_service import MarketProfileService
from app.services.quant_signal_service import QuantSignalService
from app.services.us_symbol_metadata import (
    build_us_symbol_metadata,
    enrich_us_candidate_metadata,
    enrich_us_symbol_metadata,
)

WATCHLIST_DEFAULT_SYMBOLS = [
    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "GOOG",
    "AVGO",
    "META",
    "TSLA",
    "WMT",
    "MU",
    "AMD",
    "ASML",
    "COST",
    "INTC",
    "NFLX",
    "CSCO",
    "LRCX",
    "PLTR",
    "AMAT",
    "TXN",
    "KLAC",
    "ARM",
    "LIN",
    "PEP",
    "TMUS",
    "ADI",
    "AMGN",
    "ISRG",
    "GILD",
    "SHOP",
    "QCOM",
    "APP",
    "SNDK",
    "BKNG",
    "PANW",
    "MRVL",
    "PDD",
    "WDC",
    "HON",
    "STX",
    "SBUX",
    "CRWD",
    "VRTX",
    "CEG",
    "INTU",
    "CMCSA",
    "MAR",
    "ADBE",
    "SNPS",
]


class WatchlistService:
    def __init__(
        self,
        symbols: list[str] | None = None,
        market_data_service: MarketDataService | None = None,
        indicator_service: IndicatorService | None = None,
        quant_signal_service: QuantSignalService | None = None,
        ai_signal_service: AISignalService | None = None,
        market: str | None = None,
    ):
        self._settings = get_settings()
        self.market = market
        self.market_profile_service = MarketProfileService()
        self.market_data_service = market_data_service or MarketDataService()
        self.indicator_service = indicator_service or IndicatorService()
        self.quant_signal_service = quant_signal_service or QuantSignalService()
        self.ai_signal_service = ai_signal_service or AISignalService()
        self.symbol_metadata = self._load_symbol_metadata()
        self.symbols = symbols or self._load_symbols() or WATCHLIST_DEFAULT_SYMBOLS
        self.max_watchlist_size = int(getattr(self._settings, "max_watchlist_size", 50))

    def _load_symbols(self) -> list[str] | None:
        settings = get_settings()
        source_path = (
            self.market_profile_service.get_watchlist_path(self.market)
            if self.market
            else settings.watchlist_config_path
        )
        config_path = Path(source_path)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parents[2] / config_path

        if not config_path.exists():
            return None

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        symbols = None
        if isinstance(raw, dict):
            symbols = raw.get("symbols") or raw.get("watchlist")
        elif isinstance(raw, list):
            symbols = raw

        if not isinstance(symbols, list):
            return None

        valid_symbols = []
        for symbol in symbols:
            raw_symbol = _watchlist_symbol(symbol)
            if not raw_symbol:
                continue
            if self.market:
                valid_symbols.append(
                    self.market_profile_service.normalize_symbol(
                        str(raw_symbol),
                        self.market,
                    )
                )
            else:
                valid_symbols.append(str(raw_symbol).upper())
        return valid_symbols or None

    def _load_symbol_metadata(self) -> dict[str, dict[str, object]]:
        settings = get_settings()
        us_metadata = build_us_symbol_metadata() if _is_us_market(self.market) else {}
        source_path = (
            self.market_profile_service.get_watchlist_path(self.market)
            if self.market
            else settings.watchlist_config_path
        )
        config_path = Path(source_path)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parents[2] / config_path

        if not config_path.exists():
            return {}

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        symbols = None
        if isinstance(raw, dict):
            symbols = raw.get("symbols") or raw.get("watchlist")
        elif isinstance(raw, list):
            symbols = raw

        if not isinstance(symbols, list):
            return {}

        metadata: dict[str, dict[str, object]] = {}
        for item in symbols:
            raw_symbol = _watchlist_symbol(item)
            if not raw_symbol:
                continue
            try:
                symbol = (
                    self.market_profile_service.normalize_symbol(raw_symbol, self.market)
                    if self.market
                    else raw_symbol.upper()
                )
            except Exception:
                continue
            if _is_us_market(self.market):
                raw_item = dict(item) if isinstance(item, dict) else {"symbol": symbol}
                raw_item["symbol"] = symbol
                metadata[symbol] = enrich_us_symbol_metadata(
                    raw_item,
                    metadata_by_symbol=us_metadata,
                )
                continue
            if isinstance(item, dict):
                name = _watchlist_company_name(item, symbol)
                market = item.get("market") or self.market or "US"
                broker = item.get("broker") or item.get("provider") or _broker_for_market(str(market))
                market_label = item.get("market_label")
            else:
                name = _watchlist_company_name({}, symbol)
                market = self.market or "US"
                broker = _broker_for_market(str(market))
                market_label = None
            row: dict[str, object] = {
                "symbol": symbol,
                "name": name,
                "company_name": name,
                "market": market,
                "broker": broker,
            }
            if market_label:
                row["market_label"] = market_label
            metadata[symbol] = row
        return metadata

    def _score_symbol(self, symbol: str, gate_level: int = DEFAULT_GATE_LEVEL) -> tuple[dict[str, object], dict[str, object]]:
        normalized_symbol = symbol.upper()
        bars = self.market_data_service.get_recent_bars(symbol.upper())
        indicators = self.indicator_service.calculate(bars)
        quant = self.quant_signal_service.score(indicators, gate_level=gate_level)
        ai = self.ai_signal_service.adjust(
            indicators=indicators,
            quant_buy_score=quant["quant_buy_score"],
            quant_sell_score=quant["quant_sell_score"],
        )
        entry_score = min(max((quant["quant_buy_score"] * 0.75) + (ai["ai_buy_score"] * 0.25), 0.0), 100.0)
        readiness = evaluate_entry_readiness(
            has_indicators=bool(indicators),
            hard_blocked=False,
            entry_score=entry_score,
            buy_score=entry_score,
            sell_score=quant["quant_sell_score"],
            gate_level=gate_level,
            min_entry_score=self._settings.watchlist_min_entry_score,
            max_sell_score=self._settings.watchlist_max_sell_score,
            gating_notes=list(quant.get("quant_notes") or []),
        )

        metadata = self.symbol_metadata.get(normalized_symbol, {})
        if _is_us_market(self.market):
            identity = enrich_us_candidate_metadata(
                {"symbol": normalized_symbol, **metadata},
                self.symbol_metadata,
            )
        else:
            company_name = _watchlist_company_name(metadata, normalized_symbol)
            market = metadata.get("market") or self.market or "US"
            identity = {
                "symbol": normalized_symbol,
                "name": company_name,
                "company_name": company_name,
                "market": market,
                "broker": metadata.get("broker") or _broker_for_market(str(market)),
                "market_label": metadata.get("market_label"),
            }
        symbol_result = {
            **identity,
            "entry_score": round(entry_score, 2),
            "should_trade": bool(readiness["entry_ready"]),
            "quant_score": quant["quant_buy_score"],
            "quant_buy_score": quant["quant_buy_score"],
            "quant_sell_score": quant["quant_sell_score"],
            "ai_buy_score": ai["ai_buy_score"],
            "ai_sell_score": ai["ai_sell_score"],
            "quant_reason": quant["quant_reason"],
            "quant_notes": list(quant.get("quant_notes") or []),
            "ai_reason": ai["ai_reason"],
            "has_indicators": bool(indicators),
            **readiness,
        }
        return symbol_result, indicators

    def analyze(self, gate_level: int = DEFAULT_GATE_LEVEL) -> dict[str, object]:
        analyzed_symbols = self.symbols[: self.max_watchlist_size]
        watchlist_results: list[dict[str, object]] = []
        best_candidate: dict[str, object] | None = None

        for symbol in analyzed_symbols:
            symbol_result, _ = self._score_symbol(symbol, gate_level=gate_level)
            watchlist_results.append(symbol_result)

            if best_candidate is None or self._candidate_sort_key(symbol_result) < self._candidate_sort_key(best_candidate):
                best_candidate = symbol_result

        best_score = best_candidate["entry_score"] if best_candidate is not None else 0.0
        return {
            "watchlist_source": (
                self.market_profile_service.get_watchlist_path(self.market)
                if self.market
                else self._settings.watchlist_config_path
            ),
            "configured_symbol_count": len(self.symbols),
            "analyzed_symbol_count": len(analyzed_symbols),
            "max_watchlist_size": self.max_watchlist_size,
            "watchlist": watchlist_results,
            "best_candidate": best_candidate,
            "best_score": best_score,
            "should_trade": bool(best_candidate and best_candidate.get("entry_ready")),
        }

    @staticmethod
    def _candidate_sort_key(row: dict[str, object]):
        return (
            0 if bool(row.get("entry_ready")) else 1,
            -float(row.get("entry_score", 0) or 0),
            float(row.get("quant_sell_score", 100) or 100),
            str(row.get("symbol", "")),
        )


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "null":
            return text
    return None


def _watchlist_symbol(item: object) -> str | None:
    if isinstance(item, dict):
        return _first_text(item.get("symbol"), item.get("ticker"))
    return _first_text(item)


def _watchlist_company_name(raw: dict[str, object], symbol: str) -> str:
    return _first_text(
        raw.get("company_name"),
        raw.get("companyName"),
        raw.get("name"),
        raw.get("company"),
        symbol,
        "Unknown Company",
    ) or "Unknown Company"


def _broker_for_market(market: str) -> str:
    return "kis" if market.strip().upper() in {"KR", "KOSPI", "KOSDAQ", "KONEX"} else "alpaca"


def _is_us_market(market: str | None) -> bool:
    return str(market or "US").strip().upper() == "US"
