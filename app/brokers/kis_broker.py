from app.brokers.base import Broker, BrokerNotEnabledError
from app.brokers.kis_client import KisClient


class KisBroker(Broker):
    """KIS broker wrapper.

    Real KIS order methods are present for the manual, gated execution path,
    but stay disabled unless explicit KIS real-order settings are enabled.
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

    def submit_market_buy(
        self,
        symbol: str,
        notional: float | None = None,
        qty: int | None = None,
    ):
        self._require_real_orders_enabled()
        if qty is None:
            raise ValueError("KIS market buy requires qty; notional buy is unsupported.")
        return self.client.submit_domestic_cash_order(
            symbol=symbol,
            side="buy",
            qty=int(qty),
            order_type="market",
        )

    def submit_market_buy_qty(self, symbol: str, qty: float):
        return self.submit_market_buy(symbol=symbol, qty=int(qty))

    def submit_market_sell(self, symbol: str, qty: float):
        self._require_real_orders_enabled()
        return self.client.submit_domestic_cash_order(
            symbol=symbol,
            side="sell",
            qty=int(qty),
            order_type="market",
        )

    def _raise_order_disabled(self):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is a non-trading skeleton."
        )

    def _require_real_orders_enabled(self):
        settings = self.client.settings
        if not bool(getattr(settings, "kis_enabled", False)):
            raise BrokerNotEnabledError("KIS order submission requires KIS_ENABLED=true.")
        if not bool(getattr(settings, "kis_real_order_enabled", False)):
            raise BrokerNotEnabledError(
                "KIS order submission requires KIS_REAL_ORDER_ENABLED=true."
            )
