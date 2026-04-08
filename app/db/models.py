from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class OrderLog(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    broker = Column(String(20), nullable=False, default="alpaca")
    symbol = Column(String(20), nullable=False, index=True)

    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)
    time_in_force = Column(String(20), nullable=True)

    qty = Column(Float, nullable=True)
    notional = Column(Float, nullable=True)
    limit_price = Column(Float, nullable=True)

    client_order_id = Column(String(100), nullable=True, index=True)
    broker_order_id = Column(String(100), nullable=True, unique=True, index=True)

    internal_status = Column(String(30), nullable=False, default="REQUESTED")
    broker_status = Column(String(50), nullable=True)

    filled_qty = Column(Float, nullable=True)
    filled_avg_price = Column(Float, nullable=True)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)

    extended_hours = Column(Boolean, nullable=False, default=False)

    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    last_sync_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SignalLog(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    action = Column(String(20), nullable=False)
    buy_score = Column(Float, nullable=True)
    sell_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    reason = Column(Text, nullable=True)
    indicator_payload = Column(Text, nullable=True)

    related_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)