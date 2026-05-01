from __future__ import annotations

from sqlalchemy.orm import Session

from app.brokers.alpaca_client import AlpacaClient
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog
from app.services.order_service import normalize_broker_status, sync_order_status

ALPACA_ORDER_BROKERS = ("alpaca", "alpaca_paper")


class OrderSyncService:
    ACTIVE_BROKER_STATUSES = {
        "new",
        "accepted",
        "pending_new",
        "accepted_for_bidding",
        "partially_filled",
        "partial_fill",
        "calculated",
    }

    ACTIVE_INTERNAL_STATUSES = {
        InternalOrderStatus.REQUESTED.value,
        InternalOrderStatus.SUBMITTED.value,
        InternalOrderStatus.ACCEPTED.value,
        InternalOrderStatus.PENDING.value,
        InternalOrderStatus.PARTIALLY_FILLED.value,
    }

    def __init__(self):
        self.broker = AlpacaClient()

    def sync_order_status_by_broker_order_id(self, db: Session, broker_order_id: str) -> OrderLog | None:
        if not broker_order_id:
            return None

        local_order = (
            db.query(OrderLog)
            .filter(OrderLog.broker_order_id == broker_order_id)
            .order_by(OrderLog.created_at.desc())
            .first()
        )
        if not local_order:
            return None

        try:
            broker_order = self.broker.get_order(broker_order_id)
            synced = sync_order_status(db, local_order, broker_order)
            synced.error_message = None
            db.commit()
            db.refresh(synced)
            return synced
        except Exception as exc:
            local_order.error_message = f"order_sync_error: {exc}"
            db.commit()
            db.refresh(local_order)
            return local_order

    @staticmethod
    def _broker_scoped_query(query, broker: str):
        normalized = str(broker or "").strip().lower()
        if normalized == "alpaca":
            return query.filter(OrderLog.broker.in_(ALPACA_ORDER_BROKERS))
        return query.filter(OrderLog.broker == normalized)

    def sync_open_orders_for_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        broker: str = "alpaca",
    ) -> list[OrderLog]:
        symbol = symbol.upper()

        candidates = (
            self._broker_scoped_query(db.query(OrderLog), broker)
            .filter(
                OrderLog.symbol == symbol,
                OrderLog.broker_order_id.isnot(None),
            )
            .order_by(OrderLog.created_at.desc())
            .limit(20)
            .all()
        )

        synced_rows: list[OrderLog] = []
        for row in candidates:
            synced = self.sync_order_status_by_broker_order_id(db, row.broker_order_id)
            if synced is not None:
                synced_rows.append(synced)

        return synced_rows

    def has_conflicting_open_order(
        self,
        db: Session,
        symbol: str,
        *,
        broker: str = "alpaca",
    ) -> bool:
        symbol = symbol.upper()

        candidates = (
            self._broker_scoped_query(db.query(OrderLog), broker)
            .filter(OrderLog.symbol == symbol)
            .order_by(OrderLog.created_at.desc())
            .limit(20)
            .all()
        )

        for row in candidates:
            if self._is_open_order(row):
                return True
        return False

    def _is_open_order(self, row: OrderLog) -> bool:
        if row.broker_status:
            return normalize_broker_status(row.broker_status) in self.ACTIVE_BROKER_STATUSES
        return row.internal_status in self.ACTIVE_INTERNAL_STATUSES
