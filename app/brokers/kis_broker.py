from app.brokers.base import Broker, BrokerNotEnabledError
from app.brokers.kis_client import KisClient


class KisBroker(Broker):
    """KIS broker skeleton.

    This class intentionally does not submit orders. It exists so KIS can be
    wired and tested later without changing current Alpaca trading behavior.
    """

    def __init__(self, client: KisClient | None = None):
        self.client = client or KisClient()

    def get_account(self):
        return self.client.get_account_balance()

    def list_positions(self):
        return self.client.list_positions()

    def get_position(self, symbol: str):
        raise NotImplementedError(
            f"KIS position lookup is not implemented for {symbol}."
        )

    def list_open_orders(self):
        return self.client.list_open_orders()

    def get_order(self, order_id: str):
        raise NotImplementedError(
            f"KIS order lookup is not implemented for order_id={order_id}."
        )

    def get_latest_price(self, symbol: str):
        return self.client.get_domestic_stock_price(symbol)

    def submit_market_buy(self, symbol: str, notional: float):
        self._raise_order_disabled()

    def submit_market_buy_qty(self, symbol: str, qty: float):
        self._raise_order_disabled()

    def submit_market_sell(self, symbol: str, qty: float):
        self._raise_order_disabled()

    def _raise_order_disabled(self):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is a non-trading skeleton."
        )
