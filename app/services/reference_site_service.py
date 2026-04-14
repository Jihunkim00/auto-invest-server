from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass(slots=True)
class ReferenceSite:
    name: str
    url: str
    category: str
    enabled: bool = True
    priority: int = 100
    symbols: tuple[str, ...] = ()


class ReferenceSiteService:
    def __init__(self, config_path: str = "config/reference_sites.yaml") -> None:
        self.config_path = Path(config_path)

    def load_sites(self) -> list[ReferenceSite]:
        if not self.config_path.exists() or yaml is None:
            return []

        try:
            payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []

        if not isinstance(payload, dict):
            return []

        raw_sites = payload.get("sites")
        if not isinstance(raw_sites, list):
            return []

        sites: list[ReferenceSite] = []
        for raw in raw_sites:
            site = self._to_site(raw)
            if site is not None:
                sites.append(site)
        return sites

    def get_sites_for_symbol(self, symbol: str) -> list[ReferenceSite]:
        target = symbol.upper().strip()
        matches = [site for site in self.load_sites() if site.enabled and self._matches_symbol(site, target)]
        return sorted(matches, key=lambda item: (item.priority, item.name))

    @staticmethod
    def _matches_symbol(site: ReferenceSite, symbol: str) -> bool:
        return not site.symbols or symbol in site.symbols

    @staticmethod
    def _to_site(raw: Any) -> ReferenceSite | None:
        if not isinstance(raw, dict):
            return None

        name = str(raw.get("name", "")).strip()
        url = str(raw.get("url", "")).strip()
        category = str(raw.get("category", "general")).strip() or "general"
        if not name or not url:
            return None

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        priority_raw = raw.get("priority", 100)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            priority = 100

        symbols_raw = raw.get("symbols", [])
        symbols: tuple[str, ...] = ()
        if isinstance(symbols_raw, list):
            symbols = tuple(str(item).strip().upper() for item in symbols_raw if str(item).strip())

        enabled_raw = raw.get("enabled", True)
        enabled = enabled_raw if isinstance(enabled_raw, bool) else str(enabled_raw).strip().lower() in {"true", "1", "yes"}

        return ReferenceSite(
            name=name,
            url=url,
            category=category,
            enabled=enabled,
            priority=priority,
            symbols=symbols,
        )