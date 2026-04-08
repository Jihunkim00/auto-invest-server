from fastapi import APIRouter, HTTPException
from app.brokers.alpaca_client import AlpacaClient

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
def list_positions():
    try:
        broker = AlpacaClient()
        positions = broker.list_positions()

        result = []
        for p in positions:
            result.append({
                "symbol": p.symbol,
                "side": p.side,
                "qty": str(p.qty),
                "avg_entry_price": str(p.avg_entry_price),
                "market_value": str(p.market_value),
                "unrealized_pl": str(p.unrealized_pl),
                "unrealized_plpc": str(p.unrealized_plpc),
                "current_price": str(p.current_price),
            })

        return {
            "count": len(result),
            "positions": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {str(e)}")


@router.get("/{symbol}")
def get_position(symbol: str):
    try:
        broker = AlpacaClient()
        position = broker.get_position(symbol.upper())

        if position is None:
            return {
                "symbol": symbol.upper(),
                "exists": False,
                "message": "No open position"
            }

        return {
            "symbol": position.symbol,
            "exists": True,
            "side": position.side,
            "qty": str(position.qty),
            "avg_entry_price": str(position.avg_entry_price),
            "market_value": str(position.market_value),
            "unrealized_pl": str(position.unrealized_pl),
            "unrealized_plpc": str(position.unrealized_plpc),
            "current_price": str(position.current_price),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch position: {str(e)}")