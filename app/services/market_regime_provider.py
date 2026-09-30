from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
HISTORY_YEARS = 10
MIN_WEEKLY_HISTORY = 200
REQUEST_TIMEOUT_SECONDS = 12.0


class YahooFinanceMarketRegimeProvider:
    """Replaceable, read-only source for weekly broad-market index bars."""

    def __init__(self, *, timeout_seconds=REQUEST_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds

    def fetch_weekly_bars(self, *, as_of: datetime):
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("Market-regime data fetch requires an aware timestamp.")
        end = as_of.astimezone(UTC)
        start = end - timedelta(days=365 * HISTORY_YEARS)
        with ThreadPoolExecutor(max_workers=2) as pool:
            k_future = pool.submit(self._fetch_chart, "^KS11", start, end)
            n_future = pool.submit(self._fetch_chart, "^IXIC", start, end)
            k_bars, k_tz, k_error = self._future_result(k_future)
            n_bars, n_tz, n_error = self._future_result(n_future)

        n_symbol, n_label, is_proxy = "^IXIC", "NASDAQ Composite", False
        if len(n_bars) < MIN_WEEKLY_HISTORY:
            proxy, proxy_tz, proxy_error = self._fetch_chart("QQQ", start, end)
            if len(proxy) > len(n_bars):
                n_bars, n_tz, n_error = proxy, proxy_tz, proxy_error
                n_symbol, n_label, is_proxy = "QQQ", "NASDAQ-100 proxy (QQQ)", True

        return {
            "kospi": k_bars,
            "nasdaq": n_bars,
            "data_source": {
                "kospi": {
                    "provider": "Yahoo Finance chart", "symbol": "^KS11",
                    "label": "KOSPI", "timezone": k_tz, "weekly_bar_count": len(k_bars),
                    "error": k_error,
                },
                "nasdaq": {
                    "provider": "Yahoo Finance chart", "symbol": n_symbol,
                    "label": n_label, "timezone": n_tz, "weekly_bar_count": len(n_bars),
                    "is_proxy": is_proxy, "error": n_error,
                },
                "nasdaq_is_proxy": is_proxy,
            },
        }

    def _future_result(self, future):
        try:
            return future.result(timeout=self.timeout_seconds + 2)
        except Exception as exc:
            return [], None, exc.__class__.__name__

    def _fetch_chart(self, symbol, start, end):
        period1 = int(start.timestamp())
        period2 = int((end + timedelta(days=2)).timestamp())
        url = (
            f"{YAHOO_CHART_BASE_URL}/{quote(symbol, safe='')}"
            f"?period1={period1}&period2={period2}&interval=1wk&events=history"
        )
        request = Request(url, headers={
            "User-Agent": "Mozilla/5.0 AutoInvestServer market-regime/1.0",
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return [], None, exc.__class__.__name__

        chart = payload.get("chart") if isinstance(payload, dict) else None
        results = chart.get("result") if isinstance(chart, dict) else None
        if not results:
            error = chart.get("error") if isinstance(chart, dict) else None
            return [], None, str(error or "empty_chart_result")[:120]
        item = results[0]
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        tz_name = str(meta.get("exchangeTimezoneName") or "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz, tz_name = ZoneInfo("UTC"), "UTC"
        timestamps = item.get("timestamp") or []
        quotes = (item.get("indicators") or {}).get("quote") or [{}]
        values = quotes[0] if quotes else {}
        bars = []
        for i, epoch in enumerate(timestamps):
            try:
                instant = datetime.fromtimestamp(int(epoch), UTC)
                local_date = instant.astimezone(tz).date()
                week_ending = local_date + timedelta(days=(4 - local_date.weekday()) % 7)
                row = {
                    key: (values.get(key) or [])[i] if i < len(values.get(key) or []) else None
                    for key in ("open", "high", "low", "close", "volume")
                }
                prices = {key: _finite_positive(row[key]) for key in ("open", "high", "low", "close")}
                if any(value is None for value in prices.values()):
                    continue
                bars.append({
                    "timestamp": instant.isoformat(), "week_ending": week_ending.isoformat(),
                    **prices, "volume": _finite_positive(row["volume"], zero=True) or 0.0,
                })
            except (TypeError, ValueError, OverflowError):
                continue
        bars.sort(key=lambda bar: bar["week_ending"])
        return bars, tz_name, None


def _finite_positive(value, *, zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number and number not in (float("inf"), float("-inf"))):
        return None
    if number < 0 or (number == 0 and not zero):
        return None
    return number
