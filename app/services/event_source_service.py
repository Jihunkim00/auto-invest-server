from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass(slots=True, frozen=True)
class EventSource:
    name: str
    market: str
    type: str
    url: str
    enabled: bool = True
    priority: int = 100


class EventSourceService:
    """Structured event source registry.

    This intentionally stays separate from ReferenceSiteService, which is for
    general context/news summaries rather than event-risk data.
    """

    def __init__(self, config_path: str | None = None) -> None:
        settings = get_settings()
        self.config_path = Path(config_path or settings.event_sources_config_path)
        if not self.config_path.is_absolute():
            self.config_path = Path(__file__).resolve().parents[2] / self.config_path

    def load_sources(self) -> list[EventSource]:
        if not self.config_path.exists() or yaml is None:
            return []

        try:
            payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []

        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, list):
            return []

        sources: list[EventSource] = []
        for raw in raw_sources:
            source = self._to_source(raw)
            if source is not None:
                sources.append(source)
        return sorted(sources, key=lambda item: (item.priority, item.market, item.name))

    def get_enabled_sources(
        self,
        *,
        market: str | None = None,
        type: str | None = None,
    ) -> list[EventSource]:
        normalized_market = str(market or "").strip().upper()
        normalized_type = str(type or "").strip().lower()

        sources = [source for source in self.load_sources() if source.enabled]
        if normalized_market:
            sources = [source for source in sources if source.market == normalized_market]
        if normalized_type:
            sources = [source for source in sources if source.type == normalized_type]
        return sources

    @staticmethod
    def _to_source(raw: Any) -> EventSource | None:
        if not isinstance(raw, dict):
            return None

        name = str(raw.get("name", "")).strip()
        market = str(raw.get("market", "")).strip().upper()
        source_type = str(raw.get("type", "")).strip().lower()
        url = str(raw.get("url", "")).strip()
        if not name or market not in {"US", "KR"} or not source_type or not url:
            return None

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        priority_raw = raw.get("priority", 100)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            priority = 100

        enabled_raw = raw.get("enabled", True)
        enabled = (
            enabled_raw
            if isinstance(enabled_raw, bool)
            else str(enabled_raw).strip().lower() in {"true", "1", "yes"}
        )

        return EventSource(
            name=name,
            market=market,
            type=source_type,
            url=url,
            enabled=enabled,
            priority=priority,
        )
