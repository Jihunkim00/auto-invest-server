from __future__ import annotations

from typing import Any


_CATALOG: tuple[dict[str, Any], ...] = (
    {'symbol': '005930', 'name': '삼성전자', 'market': 'KR', 'provider': 'kis'},
    {'symbol': '006400', 'name': '삼성SDI', 'market': 'KR', 'provider': 'kis'},
    {'symbol': '000810', 'name': '삼성화재', 'market': 'KR', 'provider': 'kis'},
    {'symbol': '005380', 'name': '현대차', 'market': 'KR', 'provider': 'kis'},
    {'symbol': '000660', 'name': 'SK하이닉스', 'market': 'KR', 'provider': 'kis'},
    {'symbol': '035420', 'name': 'NAVER', 'market': 'KR', 'provider': 'kis'},
    {'symbol': 'AAPL', 'name': 'Apple', 'market': 'US', 'provider': 'alpaca'},
    {'symbol': 'MSFT', 'name': 'Microsoft', 'market': 'US', 'provider': 'alpaca'},
    {'symbol': 'TSLA', 'name': 'Tesla', 'market': 'US', 'provider': 'alpaca'},
)


class SymbolSearchService:
    def search(self, query: str, *, market: str | None = None, limit: int = 20) -> dict[str, Any]:
        text = str(query or '').strip().casefold()
        normalized_market = str(market or '').strip().upper() or None
        rows = []
        for item in _CATALOG:
            if normalized_market and item['market'] != normalized_market:
                continue
            if text and not (
                text in item['symbol'].casefold()
                or text in item['name'].casefold()
                or (item['symbol'] == '005930' and text in {'삼전', '삼성'})
            ):
                continue
            rows.append({**item, 'current_price': None, 'watchlist_included': False, 'source': 'catalog'})
        return {'query': query, 'market': normalized_market, 'results': rows[: max(1, min(int(limit), 100))]}
