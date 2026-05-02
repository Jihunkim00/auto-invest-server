from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class BrokerAuthToken(Base):
    __tablename__ = "broker_auth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False, index=True)
    token_type = Column(String(40), nullable=False, index=True)
    token_value = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    environment = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


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


class KisOrderValidationLog(Base):
    __tablename__ = "kis_order_validations"

    id = Column(Integer, primary_key=True, index=True)
    market = Column(String(10), nullable=False, default="KR", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False, index=True)
    qty = Column(Integer, nullable=False)
    order_type = Column(String(20), nullable=False, default="market")
    validated_for_submission = Column(Boolean, nullable=False, default=False, index=True)
    current_price = Column(Float, nullable=True)
    estimated_amount = Column(Float, nullable=True)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


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
    gate_level = Column(Integer, nullable=True)
    gate_profile_name = Column(String(50), nullable=True)
    hard_block_reason = Column(String(120), nullable=True)
    hard_blocked = Column(Boolean, nullable=False, default=False)
    gating_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    
class ReferenceSiteCache(Base):
    __tablename__ = "reference_site_cache"

    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(120), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    url = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)
    summary = Column(Text, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_status = Column(String(20), nullable=False, default="fresh")


class CompanyEvent(Base):
    __tablename__ = "company_events"

    id = Column(Integer, primary_key=True, index=True)
    market = Column(String(10), nullable=False, index=True)
    provider = Column(String(20), nullable=False, default="investing", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200), nullable=True)
    event_type = Column(String(40), nullable=False, default="unknown", index=True)
    event_date = Column(Date, nullable=False, index=True)
    event_time_label = Column(String(30), nullable=False, default="unknown")
    source_url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    eps_forecast = Column(Float, nullable=True)
    revenue_forecast = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=False, default="medium")
    raw_payload = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
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
    position_size_pct = Column(Float, nullable=True)
    planned_stop_loss_pct = Column(Float, nullable=True)
    planned_take_profit_pct = Column(Float, nullable=True)

    related_order_id = Column(Integer, nullable=True)
    signal_status = Column(String(30), nullable=True)
    trigger_source = Column(String(30), nullable=True)
    timeframe = Column(String(20), nullable=True)

    gate_level = Column(Integer, nullable=True)
    gate_profile_name = Column(String(50), nullable=True)
    hard_block_reason = Column(String(120), nullable=True)
    hard_blocked = Column(Boolean, nullable=False, default=False)
    gating_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    id = Column(Integer, primary_key=True, index=True)
    bot_enabled = Column(Boolean, nullable=False, default=True)
    dry_run = Column(Boolean, nullable=False, default=True)
    kill_switch = Column(Boolean, nullable=False, default=False)
    scheduler_enabled = Column(Boolean, nullable=False, default=False)
    default_symbol = Column(String(20), nullable=False, default="AAPL")
    default_gate_level = Column(Integer, nullable=False, default=2)
    max_trades_per_day = Column(Integer, nullable=False, default=3)
    global_daily_entry_limit = Column(Integer, nullable=False, default=2)
    per_symbol_daily_entry_limit = Column(Integer, nullable=False, default=1)
    per_slot_new_entry_limit = Column(Integer, nullable=False, default=1)
    max_open_positions = Column(Integer, nullable=False, default=3)
    near_close_block_minutes = Column(Integer, nullable=False, default=15)
    same_direction_cooldown_minutes = Column(Integer, nullable=False, default=120)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TradeRunLog(Base):
    __tablename__ = "trade_run_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_key = Column(String(64), nullable=False, index=True)
    trigger_source = Column(String(20), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    mode = Column(String(30), nullable=False, default="entry_scan", index=True)
    parent_run_key = Column(String(64), nullable=True, index=True)
    symbol_role = Column(String(30), nullable=True, index=True)
    gate_level = Column(Integer, nullable=True)
    stage = Column(String(20), nullable=False, default="precheck")
    result = Column(String(20), nullable=False, default="pending")
    reason = Column(Text, nullable=True)
    signal_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
