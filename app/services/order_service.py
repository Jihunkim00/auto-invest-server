import json
from sqlalchemy.orm import Session
from app.db.models import OrderLog
from app.core.enums import InternalOrderStatus


def map_broker_status_to_internal(broker_status: str | None) -> str:
    if not broker_status:
        return InternalOrderStatus.SUBMITTED.value

    s = str(broker_status).lower()

    if "." in s:
        s = s.split(".")[-1]

    if s == "accepted":
        return InternalOrderStatus.ACCEPTED.value
    if s in ("pending_new", "new", "accepted_for_bidding", "done_for_day", "calculated"):
        return InternalOrderStatus.PENDING.value
    if s in ("partial_fill", "partially_filled"):
        return InternalOrderStatus.PARTIALLY_FILLED.value
    if s in ("fill", "filled"):
        return InternalOrderStatus.FILLED.value
    if s in ("canceled", "cancelled"):
        return InternalOrderStatus.CANCELED.value
    if s in ("rejected", "order_cancel_rejected", "order_replace_rejected"):
        return InternalOrderStatus.REJECTED.value
    if s == "expired":
        return InternalOrderStatus.EXPIRED.value

    return InternalOrderStatus.PENDING.value


def create_order_log(
    db: Session,
    *,
    symbol: str,
    side: str,
    order_type: str,
    time_in_force: str | None,
    qty: float | None,
    notional: float | None,
    limit_price: float | None,
    extended_hours: bool,
    request_payload: dict | None,
):
    order = OrderLog(
        broker="alpaca",
        symbol=symbol,
        side=side,
        order_type=order_type,
        time_in_force=time_in_force,
        qty=qty,
        notional=notional,
        limit_price=limit_price,
        extended_hours=extended_hours,
        internal_status=InternalOrderStatus.REQUESTED.value,
        request_payload=json.dumps(request_payload, ensure_ascii=False) if request_payload else None,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def update_order_from_broker_response(db: Session, order: OrderLog, broker_order):
    broker_status = str(getattr(broker_order, "status", None))

    order.broker_order_id = str(getattr(broker_order, "id", None))
    order.client_order_id = str(getattr(broker_order, "client_order_id", None)) if getattr(broker_order, "client_order_id", None) else None
    order.broker_status = broker_status
    order.internal_status = map_broker_status_to_internal(broker_status)

    order.filled_qty = float(getattr(broker_order, "filled_qty", 0) or 0)

    filled_avg_price = getattr(broker_order, "filled_avg_price", None)
    order.filled_avg_price = float(filled_avg_price) if filled_avg_price else None

    order.submitted_at = getattr(broker_order, "submitted_at", None)
    order.filled_at = getattr(broker_order, "filled_at", None)
    order.canceled_at = getattr(broker_order, "canceled_at", None)

    if hasattr(broker_order, "dict"):
        order.response_payload = json.dumps(broker_order.dict(), default=str, ensure_ascii=False)
    else:
        order.response_payload = json.dumps(str(broker_order), ensure_ascii=False)

    db.commit()
    db.refresh(order)
    return order


def sync_order_status(db: Session, order: OrderLog, broker_order):
    broker_status = str(getattr(broker_order, "status", None))

    order.broker_status = broker_status
    order.internal_status = map_broker_status_to_internal(broker_status)
    order.filled_qty = float(getattr(broker_order, "filled_qty", 0) or 0)

    filled_avg_price = getattr(broker_order, "filled_avg_price", None)
    order.filled_avg_price = float(filled_avg_price) if filled_avg_price else None

    order.filled_at = getattr(broker_order, "filled_at", None)
    order.canceled_at = getattr(broker_order, "canceled_at", None)

    if hasattr(broker_order, "dict"):
        order.last_sync_payload = json.dumps(broker_order.dict(), default=str, ensure_ascii=False)
    else:
        order.last_sync_payload = json.dumps(str(broker_order), ensure_ascii=False)

    db.commit()
    db.refresh(order)
    return order