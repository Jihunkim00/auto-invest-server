from sqlalchemy import inspect, text

from app.db.database import engine
from app.db.models import Base
from app.db import models  # noqa: F401


def _add_column_if_missing(table_name: str, column_name: str, column_sql: str):
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name in existing:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def _create_trade_run_logs_optional_indexes_if_possible():
    inspector = inspect(engine)
    if "trade_run_logs" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("trade_run_logs")}

    with engine.begin() as conn:
        if "mode" in existing:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_run_logs_mode ON trade_run_logs (mode)"))
        if "parent_run_key" in existing:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trade_run_logs_parent_run_key "
                    "ON trade_run_logs (parent_run_key)"
                )
            )
        if "symbol_role" in existing:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trade_run_logs_symbol_role "
                    "ON trade_run_logs (symbol_role)"
                )
            )


def _create_order_optional_indexes_if_possible():
    inspector = inspect(engine)
    if "orders" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("orders")}

    with engine.begin() as conn:
        if "market" in existing:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_market ON orders (market)"))
        if "kis_odno" in existing:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_kis_odno ON orders (kis_odno)"))
        if "kis_orgn_odno" in existing:
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_orders_kis_orgn_odno ON orders (kis_orgn_odno)")
            )


def _create_reference_site_cache_table_if_missing():
    inspector = inspect(engine)
    if "reference_site_cache" in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS reference_site_cache (
                    id INTEGER PRIMARY KEY,
                    site_name VARCHAR(120) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    url TEXT NOT NULL,
                    category VARCHAR(50),
                    summary TEXT NOT NULL,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    expires_at DATETIME NOT NULL,
                    source_status VARCHAR(20) NOT NULL DEFAULT 'fresh'
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reference_site_cache_symbol ON reference_site_cache (symbol)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reference_site_cache_site_name ON reference_site_cache (site_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reference_site_cache_expires_at ON reference_site_cache (expires_at)"))


def _create_company_events_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS company_events (
                    id INTEGER PRIMARY KEY,
                    market VARCHAR(10) NOT NULL,
                    provider VARCHAR(20) NOT NULL DEFAULT 'investing',
                    symbol VARCHAR(20) NOT NULL,
                    company_name VARCHAR(200),
                    event_type VARCHAR(40) NOT NULL DEFAULT 'unknown',
                    event_date DATE NOT NULL,
                    event_time_label VARCHAR(30) NOT NULL DEFAULT 'unknown',
                    source_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    eps_forecast FLOAT,
                    revenue_forecast FLOAT,
                    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',
                    raw_payload TEXT,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_events_market ON company_events (market)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_events_provider ON company_events (provider)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_events_symbol ON company_events (symbol)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_events_event_type ON company_events (event_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_events_event_date ON company_events (event_date)"))


def _create_runtime_settings_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runtime_settings (
                    id INTEGER PRIMARY KEY,
                    bot_enabled BOOLEAN NOT NULL DEFAULT 1,
                    dry_run BOOLEAN NOT NULL DEFAULT 1,
                    kill_switch BOOLEAN NOT NULL DEFAULT 0,
                    scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    default_symbol VARCHAR(20) NOT NULL DEFAULT 'AAPL',
                    default_gate_level INTEGER NOT NULL DEFAULT 2,
                    max_trades_per_day INTEGER NOT NULL DEFAULT 3,
                    global_daily_entry_limit INTEGER NOT NULL DEFAULT 2,
                    per_symbol_daily_entry_limit INTEGER NOT NULL DEFAULT 1,
                    per_slot_new_entry_limit INTEGER NOT NULL DEFAULT 1,
                    max_open_positions INTEGER NOT NULL DEFAULT 3,
                    near_close_block_minutes INTEGER NOT NULL DEFAULT 15,
                    same_direction_cooldown_minutes INTEGER NOT NULL DEFAULT 120,
                    kis_live_auto_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_live_auto_buy_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_live_auto_sell_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_live_auto_requires_manual_confirm BOOLEAN NOT NULL DEFAULT 1,
                    kis_live_auto_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    kis_live_auto_max_notional_pct FLOAT NOT NULL DEFAULT 0.03,
                    kis_limited_auto_sell_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_stop_loss_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_take_profit_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_sell_stop_loss_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_sell_take_profit_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_sell_requires_queue_review BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_sell_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    kis_limited_auto_sell_max_notional_pct FLOAT NOT NULL DEFAULT 0.03,
                    kis_limited_auto_sell_min_shadow_occurrences INTEGER NOT NULL DEFAULT 1,
                    kis_limited_auto_sell_allow_manual_review_trigger BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_sell_allow_take_profit_trigger BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_buy_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_buy_readiness_enabled BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_shadow_enabled BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_requires_shadow_review BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_max_notional_pct FLOAT NOT NULL DEFAULT 0.03,
                    kis_limited_auto_buy_min_cash_buffer_krw FLOAT NOT NULL DEFAULT 0,
                    kis_limited_auto_buy_requires_existing_sell_guards BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_min_final_score FLOAT NOT NULL DEFAULT 75,
                    kis_limited_auto_buy_min_confidence FLOAT NOT NULL DEFAULT 0.70,
                    kis_limited_auto_buy_max_positions INTEGER NOT NULL DEFAULT 3,
                    kis_limited_auto_buy_block_if_position_exists BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_block_if_open_order_exists BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_allow_reentry_same_day BOOLEAN NOT NULL DEFAULT 0,
                    kis_limited_auto_buy_require_market_open BOOLEAN NOT NULL DEFAULT 1,
                    kis_limited_auto_buy_no_new_entry_after VARCHAR(5) NOT NULL DEFAULT '14:50',
                    kis_limited_auto_buy_allow_gpt_hard_block BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_dry_run BOOLEAN NOT NULL DEFAULT 1,
                    kis_scheduler_live_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_allow_real_orders BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_configured_allow_real_orders BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_buy_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_sell_enabled BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_allow_limited_auto_buy BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_allow_limited_auto_sell BOOLEAN NOT NULL DEFAULT 0,
                    kis_scheduler_max_live_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    kis_scheduler_live_requires_dry_run_false BOOLEAN NOT NULL DEFAULT 1,
                    kis_scheduler_live_respect_kill_switch BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )


def _create_kis_shadow_exit_review_queue_state_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS kis_shadow_exit_review_queue_state (
                    id INTEGER PRIMARY KEY,
                    queue_key VARCHAR(180) NOT NULL UNIQUE,
                    symbol VARCHAR(20) NOT NULL,
                    trigger VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    operator_note TEXT,
                    reviewed_at DATETIME,
                    dismissed_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_kis_shadow_exit_review_queue_state_queue_key "
                "ON kis_shadow_exit_review_queue_state (queue_key)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_kis_shadow_exit_review_queue_state_symbol "
                "ON kis_shadow_exit_review_queue_state (symbol)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_kis_shadow_exit_review_queue_state_status "
                "ON kis_shadow_exit_review_queue_state (status)"
            )
        )


def _create_broker_auth_tokens_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS broker_auth_tokens (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL,
                    token_type VARCHAR(40) NOT NULL,
                    token_value TEXT NOT NULL,
                    expires_at DATETIME,
                    issued_at DATETIME NOT NULL,
                    environment VARCHAR(20) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_broker_auth_tokens_provider ON broker_auth_tokens (provider)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_broker_auth_tokens_token_type ON broker_auth_tokens (token_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_broker_auth_tokens_environment ON broker_auth_tokens (environment)"))


def _create_trade_run_logs_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS trade_run_logs (
                    id INTEGER PRIMARY KEY,
                    run_key VARCHAR(64) NOT NULL,
                    trigger_source VARCHAR(40) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    mode VARCHAR(30) NOT NULL DEFAULT 'entry_scan',
                    parent_run_key VARCHAR(64),
                    symbol_role VARCHAR(30),
                    gate_level INTEGER,
                    stage VARCHAR(20) NOT NULL DEFAULT 'precheck',
                    result VARCHAR(40) NOT NULL DEFAULT 'pending',
                    reason TEXT,
                    signal_id INTEGER,
                    order_id INTEGER,
                    request_payload TEXT,
                    response_payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_run_logs_run_key ON trade_run_logs (run_key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_run_logs_trigger_source ON trade_run_logs (trigger_source)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_run_logs_symbol ON trade_run_logs (symbol)"))


def _create_agent_command_logs_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_command_logs (
                    id INTEGER PRIMARY KEY,
                    conversation_id VARCHAR(120),
                    user_message TEXT NOT NULL,
                    parser_status VARCHAR(40) NOT NULL,
                    command_type VARCHAR(80) NOT NULL,
                    domain VARCHAR(40) NOT NULL,
                    market VARCHAR(10),
                    provider VARCHAR(20),
                    symbol VARCHAR(20),
                    side VARCHAR(10),
                    risk_level VARCHAR(40) NOT NULL,
                    requires_auth BOOLEAN NOT NULL DEFAULT 0,
                    needs_clarification BOOLEAN NOT NULL DEFAULT 0,
                    parsed_command_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    model_name VARCHAR(120),
                    schema_version VARCHAR(80) NOT NULL DEFAULT 'autoinvest_command_v1',
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_conversation_id ON agent_command_logs (conversation_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_parser_status ON agent_command_logs (parser_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_command_type ON agent_command_logs (command_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_domain ON agent_command_logs (domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_market ON agent_command_logs (market)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_provider ON agent_command_logs (provider)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_symbol ON agent_command_logs (symbol)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_risk_level ON agent_command_logs (risk_level)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_command_logs_created_at ON agent_command_logs (created_at)"))


def _create_agent_chat_tables_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_conversations (
                    id INTEGER PRIMARY KEY,
                    conversation_key VARCHAR(80) NOT NULL UNIQUE,
                    title VARCHAR(160),
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    source VARCHAR(40) NOT NULL DEFAULT 'unknown',
                    metadata_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    archived_at DATETIME,
                    last_message_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_chat_conversations_conversation_key "
                "ON agent_chat_conversations (conversation_key)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_conversations_status "
                "ON agent_chat_conversations (status)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_conversations_source "
                "ON agent_chat_conversations (source)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_conversations_updated_at "
                "ON agent_chat_conversations (updated_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_conversations_last_message_at "
                "ON agent_chat_conversations (last_message_at)"
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    conversation_key VARCHAR(80) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    message_type VARCHAR(40) NOT NULL DEFAULT 'plain_text',
                    status VARCHAR(20) NOT NULL DEFAULT 'completed',
                    text TEXT NOT NULL,
                    command_log_id INTEGER,
                    plan_id INTEGER,
                    plan_run_id INTEGER,
                    auth_approval_request_id INTEGER,
                    prefill_source_plan_id INTEGER,
                    model_name VARCHAR(120),
                    parser_status VARCHAR(40),
                    safety_json TEXT,
                    metadata_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_conversation_id "
                "ON agent_chat_messages (conversation_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_conversation_key "
                "ON agent_chat_messages (conversation_key)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_role ON agent_chat_messages (role)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_message_type "
                "ON agent_chat_messages (message_type)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_status ON agent_chat_messages (status)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_command_log_id "
                "ON agent_chat_messages (command_log_id)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_plan_id ON agent_chat_messages (plan_id)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_plan_run_id "
                "ON agent_chat_messages (plan_run_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_auth_approval_request_id "
                "ON agent_chat_messages (auth_approval_request_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_prefill_source_plan_id "
                "ON agent_chat_messages (prefill_source_plan_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_parser_status "
                "ON agent_chat_messages (parser_status)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_chat_messages_created_at "
                "ON agent_chat_messages (created_at)"
            )
        )


def _create_agent_plan_tables_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_plans (
                    id INTEGER PRIMARY KEY,
                    plan_key VARCHAR(80) NOT NULL UNIQUE,
                    conversation_id VARCHAR(120),
                    command_log_id INTEGER,
                    schema_version VARCHAR(80) NOT NULL DEFAULT 'agent_plan_v1',
                    command_type VARCHAR(80) NOT NULL,
                    domain VARCHAR(40) NOT NULL,
                    intent VARCHAR(120) NOT NULL DEFAULT 'unknown',
                    market VARCHAR(10),
                    provider VARCHAR(20),
                    symbol VARCHAR(20),
                    side VARCHAR(10),
                    risk_level VARCHAR(40) NOT NULL,
                    status VARCHAR(40) NOT NULL,
                    plan_title TEXT NOT NULL,
                    plan_summary TEXT NOT NULL,
                    user_visible_summary TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    execution_policy_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    scope_hash VARCHAR(64) NOT NULL,
                    requires_auth BOOLEAN NOT NULL DEFAULT 0,
                    requires_risk_approval BOOLEAN NOT NULL DEFAULT 0,
                    requires_confirm_live BOOLEAN NOT NULL DEFAULT 0,
                    requires_recent_validation BOOLEAN NOT NULL DEFAULT 0,
                    allow_live_order BOOLEAN NOT NULL DEFAULT 0,
                    allow_setting_change BOOLEAN NOT NULL DEFAULT 0,
                    allow_scheduler_change BOOLEAN NOT NULL DEFAULT 0,
                    approved_auth_request_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    expires_at DATETIME,
                    cancelled_at DATETIME,
                    cancellation_reason TEXT
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_plans_plan_key ON agent_plans (plan_key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_conversation_id ON agent_plans (conversation_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_command_log_id ON agent_plans (command_log_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_command_type ON agent_plans (command_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_domain ON agent_plans (domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_market ON agent_plans (market)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_provider ON agent_plans (provider)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_symbol ON agent_plans (symbol)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_risk_level ON agent_plans (risk_level)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_status ON agent_plans (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_scope_hash ON agent_plans (scope_hash)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_plans_approved_auth_request_id "
                "ON agent_plans (approved_auth_request_id)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_created_at ON agent_plans (created_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plans_expires_at ON agent_plans (expires_at)"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS auth_approval_requests (
                    id INTEGER PRIMARY KEY,
                    approval_key VARCHAR(80) NOT NULL UNIQUE,
                    plan_id INTEGER NOT NULL,
                    command_log_id INTEGER,
                    conversation_id VARCHAR(120),
                    status VARCHAR(40) NOT NULL,
                    auth_type VARCHAR(60) NOT NULL,
                    risk_level VARCHAR(40) NOT NULL,
                    scope_hash VARCHAR(64) NOT NULL,
                    scope_json TEXT NOT NULL,
                    requested_action_summary TEXT NOT NULL,
                    user_visible_warning TEXT NOT NULL,
                    expires_at DATETIME NOT NULL,
                    approved_at DATETIME,
                    rejected_at DATETIME,
                    cancelled_at DATETIME,
                    used_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    metadata_json TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_auth_approval_requests_approval_key "
                "ON auth_approval_requests (approval_key)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_plan_id ON auth_approval_requests (plan_id)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_command_log_id "
                "ON auth_approval_requests (command_log_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_conversation_id "
                "ON auth_approval_requests (conversation_id)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_status ON auth_approval_requests (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_auth_type ON auth_approval_requests (auth_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_risk_level ON auth_approval_requests (risk_level)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_scope_hash ON auth_approval_requests (scope_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_expires_at ON auth_approval_requests (expires_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_requests_created_at ON auth_approval_requests (created_at)"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS auth_approval_tokens (
                    id INTEGER PRIMARY KEY,
                    approval_request_id INTEGER NOT NULL,
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    token_type VARCHAR(40) NOT NULL,
                    status VARCHAR(40) NOT NULL,
                    scope_hash VARCHAR(64) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    used_at DATETIME,
                    revoked_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_auth_approval_tokens_approval_request_id "
                "ON auth_approval_tokens (approval_request_id)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_auth_approval_tokens_token_hash "
                "ON auth_approval_tokens (token_hash)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_tokens_token_type ON auth_approval_tokens (token_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_tokens_status ON auth_approval_tokens (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_tokens_scope_hash ON auth_approval_tokens (scope_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_approval_tokens_expires_at ON auth_approval_tokens (expires_at)"))


def _create_agent_execution_tables_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_plan_runs (
                    id INTEGER PRIMARY KEY,
                    plan_id INTEGER NOT NULL,
                    plan_key VARCHAR(80) NOT NULL,
                    command_log_id INTEGER,
                    conversation_id VARCHAR(120),
                    command_type VARCHAR(80) NOT NULL,
                    domain VARCHAR(40) NOT NULL,
                    status VARCHAR(40) NOT NULL,
                    result_type VARCHAR(60) NOT NULL,
                    started_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    failed_at DATETIME,
                    error_message TEXT,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    scope_hash VARCHAR(64) NOT NULL,
                    execution_mode VARCHAR(60) NOT NULL,
                    trigger_source VARCHAR(60) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_plan_id ON agent_plan_runs (plan_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_plan_key ON agent_plan_runs (plan_key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_command_log_id ON agent_plan_runs (command_log_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_conversation_id ON agent_plan_runs (conversation_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_command_type ON agent_plan_runs (command_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_domain ON agent_plan_runs (domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_status ON agent_plan_runs (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_result_type ON agent_plan_runs (result_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_started_at ON agent_plan_runs (started_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_scope_hash ON agent_plan_runs (scope_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_execution_mode ON agent_plan_runs (execution_mode)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_trigger_source ON agent_plan_runs (trigger_source)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_plan_runs_created_at ON agent_plan_runs (created_at)"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_schedule_jobs (
                    id INTEGER PRIMARY KEY,
                    schedule_key VARCHAR(80) NOT NULL UNIQUE,
                    plan_id INTEGER NOT NULL,
                    command_log_id INTEGER,
                    conversation_id VARCHAR(120),
                    command_type VARCHAR(80) NOT NULL,
                    domain VARCHAR(40) NOT NULL,
                    status VARCHAR(40) NOT NULL,
                    schedule_type VARCHAR(40) NOT NULL,
                    run_at DATETIME,
                    timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
                    recurrence_rule TEXT,
                    next_run_at DATETIME,
                    last_run_at DATETIME,
                    max_runs INTEGER,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    scope_hash VARCHAR(64) NOT NULL,
                    schedule_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    cancelled_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_schedule_jobs_schedule_key "
                "ON agent_schedule_jobs (schedule_key)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_plan_id ON agent_schedule_jobs (plan_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_command_log_id ON agent_schedule_jobs (command_log_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_conversation_id ON agent_schedule_jobs (conversation_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_command_type ON agent_schedule_jobs (command_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_domain ON agent_schedule_jobs (domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_status ON agent_schedule_jobs (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_schedule_type ON agent_schedule_jobs (schedule_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_run_at ON agent_schedule_jobs (run_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_next_run_at ON agent_schedule_jobs (next_run_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_scope_hash ON agent_schedule_jobs (scope_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_schedule_jobs_created_at ON agent_schedule_jobs (created_at)"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _create_reference_site_cache_table_if_missing()
    _create_company_events_table_if_missing()
    _create_runtime_settings_table_if_missing()
    _create_kis_shadow_exit_review_queue_state_table_if_missing()
    _create_broker_auth_tokens_table_if_missing()
    _create_trade_run_logs_table_if_missing()
    _create_agent_command_logs_table_if_missing()
    _create_agent_chat_tables_if_missing()
    _create_agent_plan_tables_if_missing()
    _create_agent_execution_tables_if_missing()

    # Lightweight SQLite-friendly migrations
    signal_columns = {
        "market_analysis_id": "INTEGER",
        "gpt_entry_allowed": "BOOLEAN",
        "gpt_entry_bias": "VARCHAR(20)",
        "gpt_market_confidence": "FLOAT",
        "quant_buy_score": "FLOAT",
        "quant_sell_score": "FLOAT",
        "ai_buy_score": "FLOAT",
        "ai_sell_score": "FLOAT",
        "final_buy_score": "FLOAT",
        "final_sell_score": "FLOAT",
        "quant_reason": "TEXT",
        "ai_reason": "TEXT",
        "risk_flags": "TEXT",
        "approved_by_risk": "BOOLEAN",
        "position_size_pct": "FLOAT",
        "planned_stop_loss_pct": "FLOAT",
        "planned_take_profit_pct": "FLOAT",
        "signal_status": "VARCHAR(30)",
        "trigger_source": "VARCHAR(30)",
        "timeframe": "VARCHAR(20)",
        "gate_level": "INTEGER",
        "gate_profile_name": "VARCHAR(50)",
        "hard_block_reason": "VARCHAR(120)",
        "hard_blocked": "BOOLEAN DEFAULT 0",
        "gating_notes": "TEXT",
    }

    market_analysis_columns = {
        "gate_level": "INTEGER",
        "gate_profile_name": "VARCHAR(50)",
        "hard_block_reason": "VARCHAR(120)",
        "hard_blocked": "BOOLEAN DEFAULT 0",
        "gating_notes": "TEXT",
    }

    runtime_setting_columns = {
        "bot_enabled": "BOOLEAN DEFAULT 1",
        "dry_run": "BOOLEAN DEFAULT 1",
        "kill_switch": "BOOLEAN DEFAULT 0",
        "scheduler_enabled": "BOOLEAN DEFAULT 0",        
        "default_symbol": "VARCHAR(20) DEFAULT 'AAPL'",
        "default_gate_level": "INTEGER DEFAULT 2",
        "max_trades_per_day": "INTEGER DEFAULT 3",
        "global_daily_entry_limit": "INTEGER DEFAULT 2",
        "per_symbol_daily_entry_limit": "INTEGER DEFAULT 1",
        "per_slot_new_entry_limit": "INTEGER DEFAULT 1",
        "max_open_positions": "INTEGER DEFAULT 3",
        "near_close_block_minutes": "INTEGER DEFAULT 15",
        "same_direction_cooldown_minutes": "INTEGER DEFAULT 120",
        "kis_live_auto_enabled": "BOOLEAN DEFAULT 0",
        "kis_live_auto_buy_enabled": "BOOLEAN DEFAULT 0",
        "kis_live_auto_sell_enabled": "BOOLEAN DEFAULT 0",
        "kis_live_auto_requires_manual_confirm": "BOOLEAN DEFAULT 1",
        "kis_live_auto_max_orders_per_day": "INTEGER DEFAULT 1",
        "kis_live_auto_max_notional_pct": "FLOAT DEFAULT 0.03",
        "kis_limited_auto_sell_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_stop_loss_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_take_profit_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_sell_stop_loss_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_sell_take_profit_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_sell_requires_queue_review": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_sell_max_orders_per_day": "INTEGER DEFAULT 1",
        "kis_limited_auto_sell_max_notional_pct": "FLOAT DEFAULT 0.03",
        "kis_limited_auto_sell_min_shadow_occurrences": "INTEGER DEFAULT 1",
        "kis_limited_auto_sell_allow_manual_review_trigger": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_sell_allow_take_profit_trigger": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_buy_enabled": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_buy_readiness_enabled": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_shadow_enabled": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_requires_shadow_review": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_max_orders_per_day": "INTEGER DEFAULT 1",
        "kis_limited_auto_buy_max_notional_pct": "FLOAT DEFAULT 0.03",
        "kis_limited_auto_buy_min_cash_buffer_krw": "FLOAT DEFAULT 0",
        "kis_limited_auto_buy_requires_existing_sell_guards": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_min_final_score": "FLOAT DEFAULT 75",
        "kis_limited_auto_buy_min_confidence": "FLOAT DEFAULT 0.70",
        "kis_limited_auto_buy_max_positions": "INTEGER DEFAULT 3",
        "kis_limited_auto_buy_block_if_position_exists": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_block_if_open_order_exists": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_allow_reentry_same_day": "BOOLEAN DEFAULT 0",
        "kis_limited_auto_buy_require_market_open": "BOOLEAN DEFAULT 1",
        "kis_limited_auto_buy_no_new_entry_after": "VARCHAR(5) DEFAULT '14:50'",
        "kis_limited_auto_buy_allow_gpt_hard_block": "BOOLEAN DEFAULT 0",
        "kis_scheduler_enabled": "BOOLEAN DEFAULT 0",
        "kis_scheduler_dry_run": "BOOLEAN DEFAULT 1",
        "kis_scheduler_live_enabled": "BOOLEAN DEFAULT 0",
        "kis_scheduler_allow_real_orders": "BOOLEAN DEFAULT 0",
        "kis_scheduler_configured_allow_real_orders": "BOOLEAN DEFAULT 0",
        "kis_scheduler_buy_enabled": "BOOLEAN DEFAULT 0",
        "kis_scheduler_sell_enabled": "BOOLEAN DEFAULT 0",
        "kis_scheduler_allow_limited_auto_buy": "BOOLEAN DEFAULT 0",
        "kis_scheduler_allow_limited_auto_sell": "BOOLEAN DEFAULT 0",
        "kis_scheduler_max_live_orders_per_day": "INTEGER DEFAULT 1",
        "kis_scheduler_live_requires_dry_run_false": "BOOLEAN DEFAULT 1",
        "kis_scheduler_live_respect_kill_switch": "BOOLEAN DEFAULT 1",
    }

    trade_run_log_columns = {
        "mode": "VARCHAR(30) DEFAULT 'entry_scan'",
        "parent_run_key": "VARCHAR(64)",
        "symbol_role": "VARCHAR(30)",
    }

    order_columns = {
        "market": "VARCHAR(10)",
        "kis_odno": "VARCHAR(100)",
        "kis_orgn_odno": "VARCHAR(100)",
        "requested_qty": "FLOAT",
        "remaining_qty": "FLOAT",
        "avg_fill_price": "FLOAT",
        "broker_order_status": "VARCHAR(50)",
        "last_synced_at": "DATETIME",
        "sync_error": "TEXT",
    }

    for name, ddl in signal_columns.items():
        _add_column_if_missing("signals", name, ddl)

    for name, ddl in market_analysis_columns.items():
        _add_column_if_missing("market_analysis", name, ddl)

    for name, ddl in runtime_setting_columns.items():
        _add_column_if_missing("runtime_settings", name, ddl)

    for name, ddl in trade_run_log_columns.items():
        _add_column_if_missing("trade_run_logs", name, ddl)

    for name, ddl in order_columns.items():
        _add_column_if_missing("orders", name, ddl)

    _create_trade_run_logs_optional_indexes_if_possible()
    _create_order_optional_indexes_if_possible()
