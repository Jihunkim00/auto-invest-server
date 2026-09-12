from __future__ import annotations

from typing import Any, Mapping

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


class UserAlpacaLiveExecutionBlocked(RuntimeError):
    """The user-scoped client refuses every non-paper environment."""


class UserAlpacaTradingClient:
    """Alpaca client that is intrinsically paper-only.

    The execution service still applies the user settings and risk gates, but
    this lower-level client independently refuses live credentials and always
    constructs the SDK client with ``paper=True``.
    """

    def __init__(
        self,
        credentials: Mapping[str, Any],
        *,
        trading_client: Any | None = None,
    ) -> None:
        self.environment = str(credentials.get("environment") or "").strip().lower()
        if self.environment != "paper":
            raise UserAlpacaLiveExecutionBlocked("regular_user_live_execution_disabled")
        self.trading_client = trading_client or TradingClient(
            api_key=str(credentials.get("api_key") or ""),
            secret_key=str(credentials.get("secret_key") or ""),
            paper=True,
        )

    def submit_market_buy_qty(self, *, symbol: str, qty: float):
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading_client.submit_order(order_data=order_data)


class UserAlpacaLiveTradingClient:
    """Explicit Alpaca live client; it refuses paper credentials."""

    def __init__(
        self,
        credentials: Mapping[str, Any],
        *,
        trading_client: Any | None = None,
    ) -> None:
        self.environment = str(credentials.get("environment") or "").strip().lower()
        if self.environment != "live":
            raise UserAlpacaLiveExecutionBlocked("broker_environment_invalid")
        self.trading_client = trading_client or TradingClient(
            api_key=str(credentials.get("api_key") or ""),
            secret_key=str(credentials.get("secret_key") or ""),
            paper=False,
        )

    def submit_market_buy_qty(self, *, symbol: str, qty: float):
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading_client.submit_order(order_data=order_data)