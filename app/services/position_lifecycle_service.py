from __future__ import annotations

from app.brokers.alpaca_client import AlpacaClient


ENTRY_SCAN_MODE = "entry_scan"
POSITION_MANAGEMENT_MODE = "position_management"


class PositionLifecycleService:
    def __init__(self):
        self.broker = AlpacaClient()

    @staticmethod
    def _safe_qty(position) -> float:
        try:
            return float(getattr(position, "qty", 0) or 0)
        except Exception:
            return 0.0

    def _get_active_position(self):
        positions = self.broker.list_positions()
        active = [p for p in positions if self._safe_qty(p) > 0]
        if not active:
            return None
        return sorted(active, key=lambda p: getattr(p, "symbol", ""))[0]

    def resolve_mode(
        self,
        *,
        default_symbol: str,
        requested_symbol: str | None = None,
    ) -> dict:
        position = self._get_active_position()
        if position is None:
            target_symbol = (requested_symbol or default_symbol or "AAPL").upper()
            return {
                "mode": ENTRY_SCAN_MODE,
                "has_open_position": False,
                "symbol": target_symbol,
                "allowed_actions": ["hold", "buy"],
                "position": None,
            }

        held_symbol = str(getattr(position, "symbol", "") or "").upper()
        return {
            "mode": POSITION_MANAGEMENT_MODE,
            "has_open_position": True,
            "symbol": held_symbol,
            "allowed_actions": ["hold", "sell"],
            "position": {
                "symbol": held_symbol,
                "qty": str(getattr(position, "qty", "")),
                "side": str(getattr(position, "side", "")),
            },
        }
