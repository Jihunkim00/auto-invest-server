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
    market = Column(String(10), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)
    time_in_force = Column(String(20), nullable=True)

    qty = Column(Float, nullable=True)
    notional = Column(Float, nullable=True)
    limit_price = Column(Float, nullable=True)

    client_order_id = Column(String(100), nullable=True, index=True)
    broker_order_id = Column(String(100), nullable=True, unique=True, index=True)
    kis_odno = Column(String(100), nullable=True, index=True)
    kis_orgn_odno = Column(String(100), nullable=True, index=True)

    internal_status = Column(String(30), nullable=False, default="REQUESTED")
    broker_status = Column(String(50), nullable=True)
    broker_order_status = Column(String(50), nullable=True)

    requested_qty = Column(Float, nullable=True)
    filled_qty = Column(Float, nullable=True)
    remaining_qty = Column(Float, nullable=True)
    filled_avg_price = Column(Float, nullable=True)
    avg_fill_price = Column(Float, nullable=True)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    extended_hours = Column(Boolean, nullable=False, default=False)

    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    last_sync_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    sync_error = Column(Text, nullable=True)

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
    kis_live_auto_enabled = Column(Boolean, nullable=False, default=False)
    kis_live_auto_buy_enabled = Column(Boolean, nullable=False, default=False)
    kis_live_auto_sell_enabled = Column(Boolean, nullable=False, default=False)
    kis_live_auto_requires_manual_confirm = Column(Boolean, nullable=False, default=True)
    kis_live_auto_max_orders_per_day = Column(Integer, nullable=False, default=1)
    kis_live_auto_max_notional_pct = Column(Float, nullable=False, default=0.03)
    agent_chat_live_order_enabled = Column(Boolean, nullable=False, default=False)
    agent_chat_live_order_kis_enabled = Column(Boolean, nullable=False, default=False)
    agent_chat_live_order_buy_enabled = Column(Boolean, nullable=False, default=False)
    agent_chat_live_order_sell_enabled = Column(Boolean, nullable=False, default=False)
    agent_chat_live_order_requires_confirm = Column(Boolean, nullable=False, default=True)
    agent_chat_live_order_confirm_ttl_seconds = Column(Integer, nullable=False, default=120)
    agent_chat_live_order_max_orders_per_day = Column(Integer, nullable=False, default=1)
    agent_chat_live_order_max_notional_pct = Column(Float, nullable=False, default=0.03)
    agent_chat_live_order_max_notional_krw = Column(Float, nullable=False, default=50000)
    agent_chat_live_order_allow_market_order = Column(Boolean, nullable=False, default=True)
    agent_chat_live_order_allow_limit_order = Column(Boolean, nullable=False, default=False)
    agent_chat_live_order_requires_recent_price = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_sell_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_stop_loss_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_take_profit_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_sell_stop_loss_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_sell_take_profit_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_sell_requires_queue_review = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_sell_max_orders_per_day = Column(Integer, nullable=False, default=1)
    kis_limited_auto_sell_max_notional_pct = Column(Float, nullable=False, default=0.03)
    kis_limited_auto_sell_min_shadow_occurrences = Column(Integer, nullable=False, default=1)
    kis_limited_auto_sell_allow_manual_review_trigger = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_sell_allow_take_profit_trigger = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_buy_enabled = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_buy_readiness_enabled = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_shadow_enabled = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_requires_shadow_review = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_max_orders_per_day = Column(Integer, nullable=False, default=1)
    kis_limited_auto_buy_max_notional_pct = Column(Float, nullable=False, default=0.03)
    kis_limited_auto_buy_min_cash_buffer_krw = Column(Float, nullable=False, default=0)
    kis_limited_auto_buy_requires_existing_sell_guards = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_min_final_score = Column(Float, nullable=False, default=75)
    kis_limited_auto_buy_min_confidence = Column(Float, nullable=False, default=0.70)
    kis_limited_auto_buy_max_positions = Column(Integer, nullable=False, default=3)
    kis_limited_auto_buy_block_if_position_exists = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_block_if_open_order_exists = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_allow_reentry_same_day = Column(Boolean, nullable=False, default=False)
    kis_limited_auto_buy_require_market_open = Column(Boolean, nullable=False, default=True)
    kis_limited_auto_buy_no_new_entry_after = Column(String(5), nullable=False, default="14:50")
    kis_limited_auto_buy_allow_gpt_hard_block = Column(Boolean, nullable=False, default=False)
    kis_scheduler_enabled = Column(Boolean, nullable=False, default=False)
    kis_scheduler_dry_run = Column(Boolean, nullable=False, default=True)
    kis_scheduler_live_enabled = Column(Boolean, nullable=False, default=False)
    kis_scheduler_allow_real_orders = Column(Boolean, nullable=False, default=False)
    kis_scheduler_configured_allow_real_orders = Column(Boolean, nullable=False, default=False)
    kis_scheduler_buy_enabled = Column(Boolean, nullable=False, default=False)
    kis_scheduler_sell_enabled = Column(Boolean, nullable=False, default=False)
    kis_scheduler_allow_limited_auto_buy = Column(Boolean, nullable=False, default=False)
    kis_scheduler_allow_limited_auto_sell = Column(Boolean, nullable=False, default=False)
    kis_scheduler_max_live_orders_per_day = Column(Integer, nullable=False, default=1)
    kis_scheduler_live_requires_dry_run_false = Column(Boolean, nullable=False, default=True)
    kis_scheduler_live_respect_kill_switch = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class KisShadowExitReviewQueueState(Base):
    __tablename__ = "kis_shadow_exit_review_queue_state"

    id = Column(Integer, primary_key=True, index=True)
    queue_key = Column(String(180), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    trigger = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    operator_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TradeRunLog(Base):
    __tablename__ = "trade_run_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_key = Column(String(64), nullable=False, index=True)
    trigger_source = Column(String(40), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    mode = Column(String(30), nullable=False, default="entry_scan", index=True)
    parent_run_key = Column(String(64), nullable=True, index=True)
    symbol_role = Column(String(30), nullable=True, index=True)
    gate_level = Column(Integer, nullable=True)
    stage = Column(String(20), nullable=False, default="precheck")
    result = Column(String(40), nullable=False, default="pending")
    reason = Column(Text, nullable=True)
    signal_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentCommandLog(Base):
    __tablename__ = "agent_command_logs"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(120), nullable=True, index=True)
    user_message = Column(Text, nullable=False)
    parser_status = Column(String(40), nullable=False, index=True)
    command_type = Column(String(80), nullable=False, index=True)
    domain = Column(String(40), nullable=False, index=True)
    market = Column(String(10), nullable=True, index=True)
    provider = Column(String(20), nullable=True, index=True)
    symbol = Column(String(20), nullable=True, index=True)
    side = Column(String(10), nullable=True)
    risk_level = Column(String(40), nullable=False, index=True)
    requires_auth = Column(Boolean, nullable=False, default=False)
    needs_clarification = Column(Boolean, nullable=False, default=False)
    parsed_command_json = Column(Text, nullable=False)
    safety_json = Column(Text, nullable=False)
    model_name = Column(String(120), nullable=True)
    schema_version = Column(String(80), nullable=False, default="autoinvest_command_v1")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class AgentChatConversation(Base):
    __tablename__ = "agent_chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_key = Column(String(80), nullable=False, unique=True, index=True)
    title = Column(String(160), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    source = Column(String(40), nullable=False, default="unknown", index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)


class AgentChatMessage(Base):
    __tablename__ = "agent_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    conversation_key = Column(String(80), nullable=False, index=True)
    role = Column(String(20), nullable=False, index=True)
    message_type = Column(String(40), nullable=False, default="plain_text", index=True)
    status = Column(String(20), nullable=False, default="completed", index=True)
    text = Column(Text, nullable=False)
    command_log_id = Column(Integer, nullable=True, index=True)
    plan_id = Column(Integer, nullable=True, index=True)
    plan_run_id = Column(Integer, nullable=True, index=True)
    auth_approval_request_id = Column(Integer, nullable=True, index=True)
    prefill_source_plan_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(120), nullable=True)
    parser_status = Column(String(40), nullable=True, index=True)
    safety_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class AgentChatOrderAction(Base):
    __tablename__ = "agent_chat_order_actions"

    id = Column(Integer, primary_key=True, index=True)
    conversation_key = Column(String(80), nullable=False, index=True)
    user_message_id = Column(Integer, nullable=True, index=True)
    assistant_message_id = Column(Integer, nullable=True, index=True)
    action_type = Column(String(60), nullable=False, default="chat_confirmed_live_order", index=True)
    provider = Column(String(20), nullable=False, default="kis", index=True)
    market = Column(String(10), nullable=False, default="KR", index=True)
    symbol = Column(String(20), nullable=False, index=True)
    symbol_name = Column(String(160), nullable=True)
    side = Column(String(10), nullable=False, index=True)
    order_type = Column(String(20), nullable=False, default="market")
    quantity = Column(Float, nullable=True)
    notional_amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=False, default="KRW")
    estimated_price = Column(Float, nullable=True)
    estimated_notional = Column(Float, nullable=True)
    status = Column(String(40), nullable=False, default="pending_confirmation", index=True)
    scope_hash = Column(String(64), nullable=False, index=True)
    confirmation_phrase = Column(String(200), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    last_state_change_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    related_order_id = Column(Integer, nullable=True, index=True)
    broker_order_id = Column(String(100), nullable=True, index=True)
    validation_payload_json = Column(Text, nullable=True)
    risk_payload_json = Column(Text, nullable=True)
    request_payload_json = Column(Text, nullable=True)
    response_payload_json = Column(Text, nullable=True)
    last_sync_payload_json = Column(Text, nullable=True)
    safety_payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AgentPlan(Base):
    __tablename__ = "agent_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_key = Column(String(80), nullable=False, unique=True, index=True)
    conversation_id = Column(String(120), nullable=True, index=True)
    command_log_id = Column(Integer, nullable=True, index=True)
    schema_version = Column(String(80), nullable=False, default="agent_plan_v1")
    command_type = Column(String(80), nullable=False, index=True)
    domain = Column(String(40), nullable=False, index=True)
    intent = Column(String(120), nullable=False, default="unknown")
    market = Column(String(10), nullable=True, index=True)
    provider = Column(String(20), nullable=True, index=True)
    symbol = Column(String(20), nullable=True, index=True)
    side = Column(String(10), nullable=True)
    risk_level = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    plan_title = Column(Text, nullable=False)
    plan_summary = Column(Text, nullable=False)
    user_visible_summary = Column(Text, nullable=False)
    command_json = Column(Text, nullable=False)
    execution_policy_json = Column(Text, nullable=False)
    safety_json = Column(Text, nullable=False)
    scope_json = Column(Text, nullable=False)
    scope_hash = Column(String(64), nullable=False, index=True)
    requires_auth = Column(Boolean, nullable=False, default=False)
    requires_risk_approval = Column(Boolean, nullable=False, default=False)
    requires_confirm_live = Column(Boolean, nullable=False, default=False)
    requires_recent_validation = Column(Boolean, nullable=False, default=False)
    allow_live_order = Column(Boolean, nullable=False, default=False)
    allow_setting_change = Column(Boolean, nullable=False, default=False)
    allow_scheduler_change = Column(Boolean, nullable=False, default=False)
    approved_auth_request_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)


class AuthApprovalRequest(Base):
    __tablename__ = "auth_approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    approval_key = Column(String(80), nullable=False, unique=True, index=True)
    plan_id = Column(Integer, nullable=False, index=True)
    command_log_id = Column(Integer, nullable=True, index=True)
    conversation_id = Column(String(120), nullable=True, index=True)
    status = Column(String(40), nullable=False, index=True)
    auth_type = Column(String(60), nullable=False, index=True)
    risk_level = Column(String(40), nullable=False, index=True)
    scope_hash = Column(String(64), nullable=False, index=True)
    scope_json = Column(Text, nullable=False)
    requested_action_summary = Column(Text, nullable=False)
    user_visible_warning = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    metadata_json = Column(Text, nullable=True)


class AuthApprovalToken(Base):
    __tablename__ = "auth_approval_tokens"

    id = Column(Integer, primary_key=True, index=True)
    approval_request_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    token_type = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    scope_hash = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class AgentPlanRun(Base):
    __tablename__ = "agent_plan_runs"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, nullable=False, index=True)
    plan_key = Column(String(80), nullable=False, index=True)
    command_log_id = Column(Integer, nullable=True, index=True)
    conversation_id = Column(String(120), nullable=True, index=True)
    command_type = Column(String(80), nullable=False, index=True)
    domain = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    result_type = Column(String(60), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    request_json = Column(Text, nullable=False)
    response_json = Column(Text, nullable=False)
    safety_json = Column(Text, nullable=False)
    scope_hash = Column(String(64), nullable=False, index=True)
    execution_mode = Column(String(60), nullable=False, index=True)
    trigger_source = Column(String(60), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class AgentReviewQueueState(Base):
    __tablename__ = "agent_review_queue_state"

    id = Column(Integer, primary_key=True, index=True)
    queue_key = Column(String(120), nullable=False, unique=True, index=True)
    item_type = Column(String(60), nullable=False, index=True)
    source_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AgentScheduleJob(Base):
    __tablename__ = "agent_schedule_jobs"

    id = Column(Integer, primary_key=True, index=True)
    schedule_key = Column(String(80), nullable=False, unique=True, index=True)
    plan_id = Column(Integer, nullable=False, index=True)
    command_log_id = Column(Integer, nullable=True, index=True)
    conversation_id = Column(String(120), nullable=True, index=True)
    command_type = Column(String(80), nullable=False, index=True)
    domain = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, index=True)
    schedule_type = Column(String(40), nullable=False, index=True)
    run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    timezone = Column(String(80), nullable=False, default="UTC")
    recurrence_rule = Column(Text, nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    max_runs = Column(Integer, nullable=True)
    run_count = Column(Integer, nullable=False, default=0)
    scope_hash = Column(String(64), nullable=False, index=True)
    schedule_json = Column(Text, nullable=False)
    safety_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
