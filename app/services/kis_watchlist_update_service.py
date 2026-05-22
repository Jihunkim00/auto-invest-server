from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.brokers.kis_client import KisClient
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_profile_service import MarketProfileService


KOSDAQ_TOP50_LIMIT = 50
MIN_UPDATE_SYMBOLS = 10
SOURCE_MARKET = "KOSDAQ"


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
        symbols = self._fetch_kosdaq_top50()
        return sanitize_kis_payload(
            {
                "provider": "kis",
                "market": "KR",
                "source_market": SOURCE_MARKET,
                "mode": "watchlist_update_preview",
                "count": len(symbols),
                "symbols": symbols,
                "updated": False,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def update_kosdaq_top50(self) -> dict[str, Any]:
        preview = self.preview_kosdaq_top50()
        symbols = list(preview.get("symbols") or [])
        if len(symbols) < MIN_UPDATE_SYMBOLS:
            raise KisWatchlistUpdateError(
                f"KOSDAQ top50 update aborted: only {len(symbols)} symbols returned."
            )

        watchlist_path = _resolve_project_path(
            self.profile_service.get_watchlist_path("KR")
        )
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
                    "market": SOURCE_MARKET,
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
                "source_market": SOURCE_MARKET,
                "mode": "watchlist_update_applied",
                "watchlist_file": str(watchlist_path),
                "backup_file": str(backup_path) if backup_path.exists() else None,
                "updated": True,
                "count": len(symbols),
                "symbols": symbols,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
            }
        )

    def _fetch_kosdaq_top50(self) -> list[dict[str, Any]]:
        rows = self.client.get_domestic_market_cap_ranking(
            market=SOURCE_MARKET,
            limit=KOSDAQ_TOP50_LIMIT,
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
                    "market": SOURCE_MARKET,
                    "market_cap": row.get("market_cap"),
                    "rank": int(row.get("rank") or index),
                }
            )
            if len(normalized) >= KOSDAQ_TOP50_LIMIT:
                break
        return normalized


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    if len(digits) > 6:
        digits = digits[-6:]
    return digits.zfill(6)


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path
