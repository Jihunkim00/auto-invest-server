from fastapi import APIRouter, HTTPException, Query
from app.brokers.alpaca_client import AlpacaClient

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price")
def get_latest_price(symbol: str = Query(..., min_length=1)):
    try:
        broker = AlpacaClient()
        price_data = broker.get_latest_price(symbol.upper())

        if price_data is None:
            raise HTTPException(status_code=404, detail="Price not found")

        return price_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch latest price: {str(e)}")