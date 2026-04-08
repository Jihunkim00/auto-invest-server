from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrderByIdRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from app.config import get_settings


class AlpacaClient:
    def __init__(self):
        settings = get_settings()

        self.trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=True,
        )

        self.data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )

    def get_account(self):
        return self.trading_client.get_account()

    def get_position(self, symbol: str):
        try:
            return self.trading_client.get_open_position(symbol)
        except Exception:
            return None

    def list_positions(self):
        return self.trading_client.get_all_positions()

    def get_latest_price(self, symbol: str):
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self.data_client.get_stock_latest_trade(request)

        latest = trade.get(symbol)
        if latest is None:
            return None

        return {
            "symbol": symbol,
            "price": float(latest.price),
            "timestamp": str(latest.timestamp),
        }

    def submit_market_buy(self, symbol: str, notional: float):
        order_data = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading_client.submit_order(order_data=order_data)

    def submit_market_sell(self, symbol: str, qty: float):
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading_client.submit_order(order_data=order_data)

    def get_order(self, order_id: str):
        req = GetOrderByIdRequest(nested=True)
        return self.trading_client.get_order_by_id(order_id, filter=req)