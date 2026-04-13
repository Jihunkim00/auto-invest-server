from __future__ import annotations

import re
from html import unescape

import requests

from app.services.reference_site_service import ReferenceSite


class WebContentService:
    def __init__(self, timeout_seconds: float = 4.0, max_chars: int = 1200) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def build_site_summaries(self, sites: list[ReferenceSite]) -> list[dict]:
        summaries: list[dict] = []
        for site in sites:
            summary = self._fetch_site_summary(site)
            if summary:
                summaries.append(summary)
        return summaries

    def _fetch_site_summary(self, site: ReferenceSite) -> dict | None:
        try:
            response = requests.get(
                site.url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0 (compatible; auto-invest-server/1.0)"},
            )
            response.raise_for_status()
        except Exception:
            return None

        text = self._extract_text(response.text)
        if not text:
            return None

        clipped = text[: self.max_chars]
        return {
            "name": site.name,
            "url": site.url,
            "category": site.category,
            "priority": site.priority,
            "summary": clipped,
        }

    @staticmethod
    def _extract_text(html: str) -> str:
        body = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
        body = re.sub(r"<style[\\s\\S]*?</style>", " ", body, flags=re.IGNORECASE)
        body = re.sub(r"<[^>]+>", " ", body)
        body = unescape(body)
        body = re.sub(r"\\s+", " ", body).strip()
        return body
