from __future__ import annotations

from app.brokers.alpaca_client import AlpacaClient


ENTRY_SCAN_MODE = "entry_scan"
POSITION_MANAGEMENT_MODE = "position_management"
PORTFOLIO_MANAGEMENT_MODE = "portfolio_management"
DEFAULT_MAX_OPEN_POSITIONS = 3


class PositionLifecycleService:
    def __init__(self, max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS):
        self.broker = AlpacaClient()
        self.max_open_positions = int(max_open_positions)

    @staticmethod
    def _safe_qty(position) -> float:
        try:
            return float(getattr(position, "qty", 0) or 0)
        except Exception:
            return 0.0

    def list_open_positions(self) -> list[dict]:
        positions = self.broker.list_positions()
        active = [p for p in positions if self._safe_qty(p) > 0]
        active = sorted(active, key=lambda p: str(getattr(p, "symbol", "")).upper())

        return [
            {
                "symbol": str(getattr(position, "symbol", "") or "").upper(),
                "qty": str(getattr(position, "qty", "")),
                "side": str(getattr(position, "side", "")),
            }
            for position in active
            if str(getattr(position, "symbol", "") or "")
        ]

    def resolve_portfolio(
        self,
        *,
        default_symbol: str,
        requested_symbol: str | None = None,
    ) -> dict:
        open_positions = self.list_open_positions()
        has_open_positions = len(open_positions) > 0
        portfolio_has_room = len(open_positions) < self.max_open_positions
        candidate_symbol = (requested_symbol or default_symbol or "AAPL").upper()

        can_scan_new_entry = portfolio_has_room
        if any(p["symbol"] == candidate_symbol for p in open_positions):
            can_scan_new_entry = False

        mode_summary = PORTFOLIO_MANAGEMENT_MODE if has_open_positions else ENTRY_SCAN_MODE

        return {
            "mode_summary": mode_summary,
            "open_positions": open_positions,
            "has_open_positions": has_open_positions,
            "open_position_count": len(open_positions),
            "max_open_positions": self.max_open_positions,
            "portfolio_has_room": portfolio_has_room,
            "entry_candidate_symbol": candidate_symbol,
            "can_scan_new_entry": can_scan_new_entry,
        }

    # Backward-compatible helper kept for old call sites.
    def resolve_mode(
        self,
        *,
        default_symbol: str,
        requested_symbol: str | None = None,
    ) -> dict:
        portfolio = self.resolve_portfolio(default_symbol=default_symbol, requested_symbol=requested_symbol)

        if not portfolio["has_open_positions"]:
            return {
                "mode": ENTRY_SCAN_MODE,
                "has_open_position": False,
                "symbol": portfolio["entry_candidate_symbol"],
                "allowed_actions": ["hold", "buy"],
                "position": None,
            }

        first_position = portfolio["open_positions"][0]
        return {
            "mode": POSITION_MANAGEMENT_MODE,
            "has_open_position": True,
            "symbol": first_position["symbol"],
            "allowed_actions": ["hold", "sell"],
            "position": first_position,
        }
