from abc import ABC, abstractmethod


class BrokerConfigurationError(RuntimeError):
    """Raised when a broker is selected without the required safe configuration."""


class BrokerNotEnabledError(RuntimeError):
    """Raised when a broker or broker action is deliberately disabled."""


class Broker(ABC):
    @abstractmethod
    def get_account(self):
        raise NotImplementedError

    @abstractmethod
    def list_positions(self):
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str):
        raise NotImplementedError

    @abstractmethod
    def list_open_orders(self):
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str):
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str):
        raise NotImplementedError

    @abstractmethod
    def submit_market_buy(self, symbol: str, notional: float):
        raise NotImplementedError

    @abstractmethod
    def submit_market_buy_qty(self, symbol: str, qty: float):
        raise NotImplementedError

    @abstractmethod
    def submit_market_sell(self, symbol: str, qty: float):
        raise NotImplementedError
