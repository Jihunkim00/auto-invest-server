from app.brokers.alpaca_client import AlpacaClient
from app.core.constants import DEFAULT_BARS_LIMIT, DEFAULT_TIMEFRAME


class MarketDataService:
    def __init__(self, broker: AlpacaClient | None = None):
        self.broker = broker or AlpacaClient()

    def get_recent_bars(self, symbol: str, limit: int = DEFAULT_BARS_LIMIT, timeframe: str = DEFAULT_TIMEFRAME):
        bars = self.broker.get_recent_bars(symbol=symbol.upper(), limit=limit, timeframe=timeframe)
        return [
            {
                "timestamp": str(b.timestamp),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars
        ]