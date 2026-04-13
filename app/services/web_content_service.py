from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

import requests

from app.services.reference_site_service import ReferenceSite


class _MeaningfulTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._capture_title = False
        self.title = ""
        self.meta_description = ""
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): v for k, v in attrs}
        if tag in {"script", "style", "noscript", "nav", "footer", "header"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._capture_title = True
        if tag == "meta":
            name = (attr_map.get("name") or "").lower()
            prop = (attr_map.get("property") or "").lower()
            content = (attr_map.get("content") or "").strip()
            if content and (name == "description" or prop == "og:description"):
                self.meta_description = content

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "nav", "footer", "header"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._capture_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return

        text = re.sub(r"\s+", " ", unescape(data or "")).strip()
        if not text:
            return

        if self._capture_title:
            self.title = f"{self.title} {text}".strip() if self.title else text
            return

        if len(text) >= 40:
            self.paragraphs.append(text)


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

        summary_text = self._extract_meaningful_text(response.text)
        if not summary_text:
            return None

        return {
            "name": site.name,
            "url": site.url,
            "category": site.category,
            "priority": site.priority,
            "summary": summary_text[: self.max_chars],
        }

    def _extract_meaningful_text(self, html: str) -> str:
        parser = _MeaningfulTextParser()
        try:
            parser.feed(html)
        except Exception:
            return ""

        parts: list[str] = []
        if parser.title:
            parts.append(f"Title: {parser.title}")
        if parser.meta_description:
            parts.append(f"Description: {parser.meta_description}")

        if parser.paragraphs:
            seen: set[str] = set()
            for paragraph in parser.paragraphs:
                normalized = paragraph.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                parts.append(paragraph)
                if len(" ".join(parts)) >= self.max_chars:
                    break

        text = "\n".join(parts).strip()
        return text
