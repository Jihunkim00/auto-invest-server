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


class MarketAnalysis(Base):
    __tablename__ = "market_analysis"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    market_regime = Column(String(50), nullable=True)
    entry_bias = Column(String(20), nullable=True)
    entry_allowed = Column(Boolean, nullable=False, default=False)
    market_confidence = Column(Float, nullable=True)
    risk_note = Column(Text, nullable=True)
    macro_summary = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SignalLog(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    action = Column(String(20), nullable=False, default="hold")
    buy_score = Column(Float, nullable=True)
    sell_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    reason = Column(Text, nullable=True)
    indicator_payload = Column(Text, nullable=True)

    market_analysis_id = Column(Integer, nullable=True, index=True)
    gpt_entry_allowed = Column(Boolean, nullable=True)
    gpt_entry_bias = Column(String(20), nullable=True)
    gpt_market_confidence = Column(Float, nullable=True)

    quant_buy_score = Column(Float, nullable=True)
    quant_sell_score = Column(Float, nullable=True)
    ai_buy_score = Column(Float, nullable=True)
    ai_sell_score = Column(Float, nullable=True)
    final_buy_score = Column(Float, nullable=True)
    final_sell_score = Column(Float, nullable=True)

    quant_reason = Column(Text, nullable=True)
    ai_reason = Column(Text, nullable=True)
    risk_flags = Column(Text, nullable=True)
    approved_by_risk = Column(Boolean, nullable=True)

    related_order_id = Column(Integer, nullable=True)
    signal_status = Column(String(30), nullable=True)
    trigger_source = Column(String(30), nullable=True)
    timeframe = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)