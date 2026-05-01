from fastapi import APIRouter, HTTPException

from app.brokers.alpaca_client import AlpacaClient

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

PENDING_ORDER_STATUSES = {
    "new",
    "accepted",
    "pending_new",
    "partially_filled",
    "pending_cancel",
    "accepted_for_bidding",
    "pending_replace",
    "pending_review",
    "held",
    "calculated",
    "done_for_day",
}


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _as_text(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value)
    if "." in text:
        tail = text.split(".")[-1]
        if tail and tail.lower() == tail:
            return tail
    return text


def _as_datetime_text(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _position_summary(position) -> dict:
    qty = _as_float(getattr(position, "qty", None)) or 0.0
    avg_entry_price = _as_float(getattr(position, "avg_entry_price", None)) or 0.0
    cost_basis = qty * avg_entry_price
    market_value = _as_float(getattr(position, "market_value", None)) or 0.0
    unrealized_pl = _as_float(getattr(position, "unrealized_pl", None)) or 0.0
    unrealized_plpc = _as_float(getattr(position, "unrealized_plpc", None)) or 0.0

    return {
        "symbol": _as_text(getattr(position, "symbol", None)) or "",
        "side": _as_text(getattr(position, "side", None)) or "long",
        "qty": qty,
        "avg_entry_price": avg_entry_price,
        "cost_basis": cost_basis,
        "current_price": _as_float(getattr(position, "current_price", None)),
        "market_value": market_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_plpc": unrealized_plpc,
    }


def _pending_order_summary(order) -> dict | None:
    status = (_as_text(getattr(order, "status", None)) or "").lower()
    if status not in PENDING_ORDER_STATUSES:
        return None

    qty = _as_float(getattr(order, "qty", None))
    notional = _as_float(getattr(order, "notional", None))
    limit_price = _as_float(getattr(order, "limit_price", None))

    estimated_amount = None
    if notional is not None:
        estimated_amount = notional
    elif qty is not None and limit_price is not None:
        estimated_amount = qty * limit_price

    order_type = getattr(order, "order_type", None)
    if order_type is None:
        order_type = getattr(order, "type", None)

    return {
        "id": _as_text(getattr(order, "id", None)) or "",
        "symbol": _as_text(getattr(order, "symbol", None)) or "",
        "side": _as_text(getattr(order, "side", None)) or "",
        "type": _as_text(order_type) or "",
        "status": status,
        "qty": qty,
        "notional": notional,
        "limit_price": limit_price,
        "estimated_amount": estimated_amount,
        "submitted_at": _as_datetime_text(getattr(order, "submitted_at", None)),
    }


@router.get("/summary")
def get_portfolio_summary():
    try:
        broker = AlpacaClient()
        positions = [_position_summary(position) for position in broker.list_positions()]
        pending_orders = []
        for order in broker.list_open_orders():
            item = _pending_order_summary(order)
            if item is not None:
                pending_orders.append(item)

        total_cost_basis = sum(position["cost_basis"] for position in positions)
        total_market_value = sum(position["market_value"] for position in positions)
        total_unrealized_pl = sum(position["unrealized_pl"] for position in positions)
        total_unrealized_plpc = (
            total_unrealized_pl / total_cost_basis if total_cost_basis > 0 else 0.0
        )

        return {
            "currency": "USD",
            "positions_count": len(positions),
            "pending_orders_count": len(pending_orders),
            "total_cost_basis": total_cost_basis,
            "total_market_value": total_market_value,
            "total_unrealized_pl": total_unrealized_pl,
            "total_unrealized_plpc": total_unrealized_plpc,
            "positions": positions,
            "pending_orders": pending_orders,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch portfolio summary: {str(e)}"
        )
