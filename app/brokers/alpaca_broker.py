from app.brokers.alpaca_client import AlpacaClient
from app.brokers.base import Broker


class AlpacaBroker(AlpacaClient, Broker):
    """Compatibility wrapper for the active Alpaca paper broker."""
