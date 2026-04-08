from fastapi import APIRouter, HTTPException
from app.brokers.alpaca_client import AlpacaClient

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
def get_account():
    try:
        broker = AlpacaClient()
        account = broker.get_account()

        return {
            "account_number": account.account_number,
            "status": account.status,
            "currency": account.currency,
            "cash": str(account.cash),
            "buying_power": str(account.buying_power),
            "equity": str(account.equity),
            "portfolio_value": str(account.portfolio_value),
            "long_market_value": str(account.long_market_value),
            "short_market_value": str(account.short_market_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch account: {str(e)}")