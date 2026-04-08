from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.db.database import get_db
from app.db.models import OrderLog
from app.services.order_service import (
    create_order_log,
    update_order_from_broker_response,
    sync_order_status,
)

router = APIRouter(prefix="/orders", tags=["orders"])


class TestBuyRequest(BaseModel):
    symbol: str = Field(default="AAPL", min_length=1, examples=["AAPL"])
    notional: float = Field(default=50, gt=0, le=1000, examples=[50])


class TestSellRequest(BaseModel):
    symbol: str = Field(default="AAPL", min_length=1, examples=["AAPL"])
    qty: float = Field(default=1, gt=0, examples=[1])


@router.post("/test-buy")
def test_buy(payload: TestBuyRequest, db: Session = Depends(get_db)):
    local_order = None

    try:
        broker = AlpacaClient()
        symbol = payload.symbol.upper()

        account = broker.get_account()
        cash = float(account.cash)

        if cash < payload.notional:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough cash. cash={cash}, requested={payload.notional}"
            )

        # 1) 요청 로그 먼저 저장
        local_order = create_order_log(
            db,
            symbol=symbol,
            side="buy",
            order_type="market",
            time_in_force="day",
            qty=None,
            notional=payload.notional,
            limit_price=None,
            extended_hours=False,
            request_payload=payload.model_dump(),
        )

        # 2) 브로커 주문
        broker_order = broker.submit_market_buy(
            symbol=symbol,
            notional=payload.notional,
        )

        # 3) 브로커 응답 반영
        local_order = update_order_from_broker_response(
            db,
            local_order,
            broker_order,
        )

        return {
            "message": "test buy order submitted",
            "symbol": symbol,
            "notional": payload.notional,
            "order_id": str(broker_order.id),
            "status": str(broker_order.status),
            "side": str(broker_order.side),
            "type": str(broker_order.order_type),
            "db_order_id": local_order.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        if local_order is not None:
            local_order.internal_status = "FAILED"
            local_order.error_message = str(e)
            db.commit()
            db.refresh(local_order)

        raise HTTPException(status_code=500, detail=f"Failed to submit buy order: {str(e)}")


@router.post("/test-sell")
def test_sell(payload: TestSellRequest, db: Session = Depends(get_db)):
    local_order = None

    try:
        broker = AlpacaClient()
        symbol = payload.symbol.upper()

        position = broker.get_position(symbol)
        if position is None:
            raise HTTPException(status_code=400, detail=f"No open position for {symbol}")

        current_qty = float(position.qty)
        if payload.qty > current_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Sell qty exceeds position. current_qty={current_qty}, requested={payload.qty}"
            )

        # 1) 요청 로그 먼저 저장
        local_order = create_order_log(
            db,
            symbol=symbol,
            side="sell",
            order_type="market",
            time_in_force="day",
            qty=payload.qty,
            notional=None,
            limit_price=None,
            extended_hours=False,
            request_payload=payload.model_dump(),
        )

        # 2) 브로커 주문
        broker_order = broker.submit_market_sell(
            symbol=symbol,
            qty=payload.qty,
        )

        # 3) 브로커 응답 반영
        local_order = update_order_from_broker_response(
            db,
            local_order,
            broker_order,
        )

        return {
            "message": "test sell order submitted",
            "symbol": symbol,
            "qty": payload.qty,
            "order_id": str(broker_order.id),
            "status": str(broker_order.status),
            "side": str(broker_order.side),
            "type": str(broker_order.order_type),
            "db_order_id": local_order.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        if local_order is not None:
            local_order.internal_status = "FAILED"
            local_order.error_message = str(e)
            db.commit()
            db.refresh(local_order)

        raise HTTPException(status_code=500, detail=f"Failed to submit sell order: {str(e)}")


@router.get("/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    try:
        broker = AlpacaClient()
        broker_order = broker.get_order(order_id)

        # DB에 저장된 주문 있으면 상태 동기화
        local_order = (
            db.query(OrderLog)
            .filter(OrderLog.broker_order_id == order_id)
            .first()
        )

        if local_order:
            sync_order_status(db, local_order, broker_order)

        return {
            "order_id": str(broker_order.id),
            "symbol": broker_order.symbol,
            "status": str(broker_order.status),
            "side": str(broker_order.side),
            "type": str(broker_order.order_type),
            "qty": str(broker_order.qty) if broker_order.qty else None,
            "notional": str(broker_order.notional) if broker_order.notional else None,
            "filled_qty": str(broker_order.filled_qty) if broker_order.filled_qty else None,
            "filled_avg_price": str(broker_order.filled_avg_price) if broker_order.filled_avg_price else None,
            "created_at": str(broker_order.created_at),
            "submitted_at": str(broker_order.submitted_at) if broker_order.submitted_at else None,
            "filled_at": str(broker_order.filled_at) if broker_order.filled_at else None,
            "db_synced": local_order is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch order: {str(e)}")