from sqlalchemy import inspect, text

from app.db.database import SessionLocal, engine
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
                    agent_chat_live_order_enabled BOOLEAN NOT NULL DEFAULT 0,
                    agent_chat_live_order_kis_enabled BOOLEAN NOT NULL DEFAULT 0,
                    agent_chat_live_order_buy_enabled BOOLEAN NOT NULL DEFAULT 0,
                    agent_chat_live_order_sell_enabled BOOLEAN NOT NULL DEFAULT 0,
                    agent_chat_live_order_requires_confirm BOOLEAN NOT NULL DEFAULT 1,
                    agent_chat_live_order_confirm_ttl_seconds INTEGER NOT NULL DEFAULT 120,
                    agent_chat_live_order_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    agent_chat_live_order_max_notional_pct FLOAT NOT NULL DEFAULT 0.03,
                    agent_chat_live_order_max_notional_krw FLOAT NOT NULL DEFAULT 50000,
                    agent_chat_live_order_allow_market_order BOOLEAN NOT NULL DEFAULT 1,
                    agent_chat_live_order_allow_limit_order BOOLEAN NOT NULL DEFAULT 0,
                    agent_chat_live_order_requires_recent_price BOOLEAN NOT NULL DEFAULT 1,
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
                    strategy_live_auto_buy_enabled BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_buy_requires_recent_dry_run BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_buy_recent_dry_run_ttl_minutes INTEGER NOT NULL DEFAULT 30,
                    strategy_live_auto_buy_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    strategy_live_auto_buy_max_notional_krw FLOAT NOT NULL DEFAULT 50000,
                    strategy_live_auto_buy_max_notional_pct FLOAT NOT NULL DEFAULT 0.03,
                    strategy_live_auto_buy_allowed_profiles TEXT NOT NULL DEFAULT '["safe", "balanced"]',
                    strategy_live_auto_buy_allow_aggressive BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_buy_requires_operator_confirm BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_buy_block_after_loss_limit BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_buy_block_after_target_hit BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_buy_scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    strategy_auto_buy_scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    strategy_auto_buy_scheduler_dry_run_only BOOLEAN NOT NULL DEFAULT 1,
                    strategy_auto_buy_scheduler_allow_live_orders BOOLEAN NOT NULL DEFAULT 0,
                    strategy_auto_buy_scheduler_profile_source VARCHAR(20) NOT NULL DEFAULT 'active',
                    strategy_auto_buy_scheduler_max_runs_per_day INTEGER NOT NULL DEFAULT 3,
                    strategy_auto_buy_scheduler_min_minutes_between_runs INTEGER NOT NULL DEFAULT 60,
                    strategy_auto_buy_scheduler_promotion_ttl_minutes INTEGER NOT NULL DEFAULT 45,
                    strategy_auto_buy_scheduler_create_promotion_on_would_buy BOOLEAN NOT NULL DEFAULT 1,
                    strategy_auto_buy_scheduler_block_when_kill_switch BOOLEAN NOT NULL DEFAULT 1,
                    strategy_auto_buy_scheduler_block_when_market_closed BOOLEAN NOT NULL DEFAULT 1,
                    strategy_auto_buy_scheduler_block_after_no_new_entry_time BOOLEAN NOT NULL DEFAULT 1,
                    strategy_auto_buy_scheduler_no_new_entry_after VARCHAR(5) NOT NULL DEFAULT '15:00',
                    strategy_auto_buy_scheduler_allowed_profiles TEXT NOT NULL DEFAULT '["safe", "balanced"]',
                    strategy_auto_buy_scheduler_allow_aggressive BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_enabled BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_requires_operator_confirm BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_exit_max_orders_per_day INTEGER NOT NULL DEFAULT 1,
                    strategy_live_auto_exit_max_notional_krw FLOAT NOT NULL DEFAULT 50000,
                    strategy_live_auto_exit_max_position_pct FLOAT NOT NULL DEFAULT 1.0,
                    strategy_live_auto_exit_allow_stop_loss BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_exit_allow_take_profit BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_allow_max_holding_days BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_allow_monthly_loss_exit BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_exit_allow_target_hit_reduce BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_allowed_profiles TEXT NOT NULL DEFAULT '["safe", "balanced"]',
                    strategy_live_auto_exit_allow_aggressive BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    strategy_live_auto_exit_requires_cost_basis BOOLEAN NOT NULL DEFAULT 1,
                    strategy_live_auto_exit_min_quantity INTEGER NOT NULL DEFAULT 1,
                    position_management_scheduler_enabled BOOLEAN NOT NULL DEFAULT 0,
                    position_management_scheduler_dry_run_only BOOLEAN NOT NULL DEFAULT 1,
                    position_management_scheduler_allow_live_orders BOOLEAN NOT NULL DEFAULT 0,
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


def _create_strategy_tables_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_profiles (
                    id INTEGER PRIMARY KEY,
                    profile_name VARCHAR(40) NOT NULL UNIQUE,
                    display_name VARCHAR(80) NOT NULL,
                    description TEXT,
                    monthly_target_return_pct FLOAT NOT NULL,
                    monthly_target_min_pct FLOAT NOT NULL,
                    monthly_target_max_pct FLOAT NOT NULL,
                    monthly_max_loss_pct FLOAT NOT NULL,
                    daily_max_loss_pct FLOAT NOT NULL,
                    max_order_notional_pct FLOAT NOT NULL,
                    max_order_notional_krw FLOAT NOT NULL,
                    max_trades_per_day INTEGER NOT NULL,
                    max_positions INTEGER NOT NULL,
                    buy_score_threshold FLOAT NOT NULL,
                    sell_score_threshold FLOAT NOT NULL,
                    stop_loss_pct FLOAT NOT NULL,
                    take_profit_pct FLOAT NOT NULL,
                    max_holding_days INTEGER NOT NULL,
                    stop_after_monthly_target BOOLEAN NOT NULL DEFAULT 0,
                    reduce_size_after_loss BOOLEAN NOT NULL DEFAULT 1,
                    consecutive_loss_reduce_threshold INTEGER NOT NULL DEFAULT 1,
                    is_active BOOLEAN NOT NULL DEFAULT 0,
                    is_builtin BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_strategy_profiles_profile_name "
                "ON strategy_profiles (profile_name)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_strategy_profiles_is_active "
                "ON strategy_profiles (is_active)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_strategy_profiles_is_builtin "
                "ON strategy_profiles (is_builtin)"
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_profile_audits (
                    id INTEGER PRIMARY KEY,
                    action VARCHAR(80) NOT NULL,
                    previous_profile VARCHAR(40),
                    new_profile VARCHAR(40),
                    before_snapshot TEXT,
                    after_snapshot TEXT,
                    confirm_operator_ack BOOLEAN NOT NULL DEFAULT 0,
                    source VARCHAR(80) NOT NULL DEFAULT 'unknown',
                    safety_flags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name, column in {
            "action": "action",
            "previous_profile": "previous_profile",
            "new_profile": "new_profile",
            "source": "source",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_strategy_profile_audits_{name} "
                    f"ON strategy_profile_audits ({column})"
                )
            )


def _create_agent_chat_strategy_actions_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_strategy_actions (
                    id INTEGER PRIMARY KEY,
                    conversation_key VARCHAR(80) NOT NULL,
                    user_message_id INTEGER,
                    assistant_message_id INTEGER,
                    action_type VARCHAR(80) NOT NULL DEFAULT 'strategy_profile_apply',
                    requested_profile VARCHAR(40) NOT NULL,
                    current_profile VARCHAR(40),
                    status VARCHAR(40) NOT NULL DEFAULT 'pending_confirmation',
                    confirmation_token_hash VARCHAR(64),
                    expires_at DATETIME NOT NULL,
                    confirmed_at DATETIME,
                    cancelled_at DATETIME,
                    result_payload TEXT,
                    safety_flags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name, column in {
            "conversation_key": "conversation_key",
            "user_message_id": "user_message_id",
            "assistant_message_id": "assistant_message_id",
            "action_type": "action_type",
            "requested_profile": "requested_profile",
            "current_profile": "current_profile",
            "status": "status",
            "confirmation_token_hash": "confirmation_token_hash",
            "expires_at": "expires_at",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_agent_chat_strategy_actions_{name} "
                    f"ON agent_chat_strategy_actions ({column})"
                )
            )


def _create_strategy_performance_snapshots_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_performance_snapshots (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL,
                    market VARCHAR(10) NOT NULL,
                    profile_name VARCHAR(40) NOT NULL,
                    period_type VARCHAR(20) NOT NULL,
                    period_key VARCHAR(20) NOT NULL,
                    realized_pnl FLOAT NOT NULL DEFAULT 0,
                    unrealized_pnl FLOAT NOT NULL DEFAULT 0,
                    gross_pnl FLOAT NOT NULL DEFAULT 0,
                    estimated_fees FLOAT NOT NULL DEFAULT 0,
                    net_pnl_estimated FLOAT NOT NULL DEFAULT 0,
                    pnl_pct FLOAT NOT NULL DEFAULT 0,
                    target_progress_pct FLOAT,
                    loss_budget_used_pct FLOAT,
                    orders_count INTEGER NOT NULL DEFAULT 0,
                    filled_orders_count INTEGER NOT NULL DEFAULT 0,
                    rejected_orders_count INTEGER NOT NULL DEFAULT 0,
                    win_rate FLOAT NOT NULL DEFAULT 0,
                    profit_factor FLOAT,
                    max_drawdown_pct FLOAT NOT NULL DEFAULT 0,
                    data_quality TEXT,
                    source_payload TEXT,
                    safety_flags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name in (
            "provider",
            "market",
            "profile_name",
            "period_type",
            "period_key",
            "created_at",
        ):
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"ix_strategy_performance_snapshots_{name} "
                    f"ON strategy_performance_snapshots ({name})"
                )
            )


def _create_strategy_live_auto_buy_attempts_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_live_auto_buy_attempts (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL DEFAULT 'kis',
                    market VARCHAR(10) NOT NULL DEFAULT 'KR',
                    active_profile VARCHAR(40),
                    symbol VARCHAR(20),
                    symbol_name VARCHAR(160),
                    status VARCHAR(40) NOT NULL DEFAULT 'blocked',
                    trigger_source VARCHAR(80) NOT NULL DEFAULT 'manual',
                    client_request_id VARCHAR(120),
                    source_dry_run_id INTEGER,
                    source_signal_id INTEGER,
                    source_trade_run_id INTEGER,
                    requested_notional_krw FLOAT,
                    approved_notional_krw FLOAT,
                    quantity FLOAT,
                    estimated_price FLOAT,
                    estimated_notional_krw FLOAT,
                    target_risk_result TEXT,
                    validation_result TEXT,
                    related_order_id INTEGER,
                    broker_order_id VARCHAR(100),
                    block_reason VARCHAR(160),
                    risk_flags TEXT,
                    gating_notes TEXT,
                    safety_flags TEXT,
                    request_payload TEXT,
                    response_payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    submitted_at DATETIME,
                    synced_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name, column in {
            "provider": "provider",
            "market": "market",
            "active_profile": "active_profile",
            "symbol": "symbol",
            "status": "status",
            "trigger_source": "trigger_source",
            "client_request_id": "client_request_id",
            "source_dry_run_id": "source_dry_run_id",
            "source_signal_id": "source_signal_id",
            "source_trade_run_id": "source_trade_run_id",
            "related_order_id": "related_order_id",
            "broker_order_id": "broker_order_id",
            "block_reason": "block_reason",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"ix_strategy_live_auto_buy_attempts_{name} "
                    f"ON strategy_live_auto_buy_attempts ({column})"
                )
            )


def _create_strategy_auto_buy_promotions_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_auto_buy_promotions (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL DEFAULT 'kis',
                    market VARCHAR(10) NOT NULL DEFAULT 'KR',
                    active_profile VARCHAR(40),
                    symbol VARCHAR(20),
                    symbol_name VARCHAR(160),
                    status VARCHAR(40) NOT NULL DEFAULT 'pending',
                    promotion_reason TEXT,
                    source_dry_run_signal_id INTEGER,
                    source_dry_run_trade_run_id INTEGER,
                    source_dry_run_order_id INTEGER,
                    dry_run_action VARCHAR(40),
                    buy_score FLOAT,
                    sell_score FLOAT,
                    final_score FLOAT,
                    confidence FLOAT,
                    recommended_notional_krw FLOAT,
                    simulated_quantity FLOAT,
                    simulated_price FLOAT,
                    simulated_notional_krw FLOAT,
                    target_risk_result TEXT,
                    block_reason VARCHAR(160),
                    risk_flags TEXT,
                    gating_notes TEXT,
                    expires_at DATETIME,
                    acknowledged_at DATETIME,
                    dismissed_at DATETIME,
                    promoted_to_live_attempt_id INTEGER,
                    related_live_order_id INTEGER,
                    converted_live_attempt_id INTEGER,
                    converted_order_id INTEGER,
                    converted_at DATETIME,
                    conversion_status VARCHAR(40),
                    last_sync_at DATETIME,
                    last_sync_status VARCHAR(40),
                    trace_payload_json TEXT,
                    request_payload TEXT,
                    response_payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(strategy_auto_buy_promotions)"))
        }
        for column_name, column_sql in {
            "converted_live_attempt_id": "INTEGER",
            "converted_order_id": "INTEGER",
            "converted_at": "DATETIME",
            "conversion_status": "VARCHAR(40)",
            "last_sync_at": "DATETIME",
            "last_sync_status": "VARCHAR(40)",
            "trace_payload_json": "TEXT",
        }.items():
            if column_name not in existing_columns:
                conn.execute(
                    text(
                        "ALTER TABLE strategy_auto_buy_promotions "
                        f"ADD COLUMN {column_name} {column_sql}"
                    )
                )
                existing_columns.add(column_name)
        for name, column in {
            "provider": "provider",
            "market": "market",
            "active_profile": "active_profile",
            "symbol": "symbol",
            "status": "status",
            "source_dry_run_signal_id": "source_dry_run_signal_id",
            "source_dry_run_trade_run_id": "source_dry_run_trade_run_id",
            "source_dry_run_order_id": "source_dry_run_order_id",
            "dry_run_action": "dry_run_action",
            "block_reason": "block_reason",
            "expires_at": "expires_at",
            "promoted_to_live_attempt_id": "promoted_to_live_attempt_id",
            "related_live_order_id": "related_live_order_id",
            "converted_live_attempt_id": "converted_live_attempt_id",
            "converted_order_id": "converted_order_id",
            "conversion_status": "conversion_status",
            "last_sync_status": "last_sync_status",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    f"ix_strategy_auto_buy_promotions_{name} "
                    f"ON strategy_auto_buy_promotions ({column})"
                )
            )


def _create_strategy_live_auto_exit_attempts_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS strategy_live_auto_exit_attempts (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL DEFAULT 'kis',
                    market VARCHAR(10) NOT NULL DEFAULT 'KR',
                    active_profile VARCHAR(40),
                    symbol VARCHAR(20),
                    symbol_name VARCHAR(160),
                    status VARCHAR(40) NOT NULL DEFAULT 'blocked',
                    trigger_source VARCHAR(80) NOT NULL DEFAULT 'manual',
                    client_request_id VARCHAR(120),
                    exit_trigger VARCHAR(40),
                    exit_reason TEXT,
                    quantity FLOAT,
                    current_price FLOAT,
                    cost_basis FLOAT,
                    unrealized_pnl FLOAT,
                    unrealized_pnl_pct FLOAT,
                    stop_loss_pct FLOAT,
                    take_profit_pct FLOAT,
                    max_holding_days INTEGER,
                    position_age_days FLOAT,
                    requested_notional_krw FLOAT,
                    approved_notional_krw FLOAT,
                    target_risk_result TEXT,
                    validation_result TEXT,
                    related_order_id INTEGER,
                    broker_order_id VARCHAR(100),
                    block_reason VARCHAR(160),
                    risk_flags TEXT,
                    gating_notes TEXT,
                    safety_flags TEXT,
                    request_payload TEXT,
                    response_payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    submitted_at DATETIME,
                    synced_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name, column in {
            "provider": "provider",
            "market": "market",
            "active_profile": "active_profile",
            "symbol": "symbol",
            "status": "status",
            "trigger_source": "trigger_source",
            "client_request_id": "client_request_id",
            "exit_trigger": "exit_trigger",
            "related_order_id": "related_order_id",
            "broker_order_id": "broker_order_id",
            "block_reason": "block_reason",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"ix_strategy_live_auto_exit_attempts_{name} "
                    f"ON strategy_live_auto_exit_attempts ({column})"
                )
            )


def _seed_strategy_profiles_if_needed():
    from app.services.strategy_profile_service import StrategyProfileService

    db = SessionLocal()
    try:
        StrategyProfileService().ensure_seeded(db)
    finally:
        db.close()


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
                    message_type VARCHAR(80) NOT NULL DEFAULT 'plain_text',
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


def _create_agent_chat_order_actions_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_order_actions (
                    id INTEGER PRIMARY KEY,
                    conversation_key VARCHAR(80) NOT NULL,
                    user_message_id INTEGER,
                    assistant_message_id INTEGER,
                    action_type VARCHAR(60) NOT NULL DEFAULT 'chat_confirmed_live_order',
                    provider VARCHAR(20) NOT NULL DEFAULT 'kis',
                    market VARCHAR(10) NOT NULL DEFAULT 'KR',
                    symbol VARCHAR(20) NOT NULL,
                    symbol_name VARCHAR(160),
                    side VARCHAR(10) NOT NULL,
                    order_type VARCHAR(20) NOT NULL DEFAULT 'market',
                    quantity FLOAT,
                    notional_amount FLOAT,
                    currency VARCHAR(10) NOT NULL DEFAULT 'KRW',
                    estimated_price FLOAT,
                    estimated_notional FLOAT,
                    status VARCHAR(40) NOT NULL DEFAULT 'pending_confirmation',
                    scope_hash VARCHAR(64) NOT NULL,
                    confirmation_phrase VARCHAR(200) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    confirmed_at DATETIME,
                    submitted_at DATETIME,
                    last_state_change_at DATETIME,
                    last_sync_at DATETIME,
                    related_order_id INTEGER,
                    broker_order_id VARCHAR(100),
                    validation_payload_json TEXT,
                    risk_payload_json TEXT,
                    request_payload_json TEXT,
                    response_payload_json TEXT,
                    last_sync_payload_json TEXT,
                    safety_payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(agent_chat_order_actions)"))
        }
        for column_name, column_sql in {
            "conversation_key": "VARCHAR(80)",
            "user_message_id": "INTEGER",
            "assistant_message_id": "INTEGER",
            "action_type": "VARCHAR(60) DEFAULT 'chat_confirmed_live_order'",
            "provider": "VARCHAR(20) DEFAULT 'kis'",
            "market": "VARCHAR(10) DEFAULT 'KR'",
            "symbol": "VARCHAR(20)",
            "symbol_name": "VARCHAR(160)",
            "side": "VARCHAR(10)",
            "order_type": "VARCHAR(20) DEFAULT 'market'",
            "quantity": "FLOAT",
            "notional_amount": "FLOAT",
            "currency": "VARCHAR(10) DEFAULT 'KRW'",
            "estimated_price": "FLOAT",
            "estimated_notional": "FLOAT",
            "status": "VARCHAR(40) DEFAULT 'pending_confirmation'",
            "scope_hash": "VARCHAR(64)",
            "confirmation_phrase": "VARCHAR(200)",
            "expires_at": "DATETIME",
            "confirmed_at": "DATETIME",
            "submitted_at": "DATETIME",
            "last_state_change_at": "DATETIME",
            "last_sync_at": "DATETIME",
            "related_order_id": "INTEGER",
            "broker_order_id": "VARCHAR(100)",
            "validation_payload_json": "TEXT",
            "risk_payload_json": "TEXT",
            "request_payload_json": "TEXT",
            "response_payload_json": "TEXT",
            "last_sync_payload_json": "TEXT",
            "safety_payload_json": "TEXT",
            "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        }.items():
            if column_name not in existing_columns:
                conn.execute(
                    text(
                        f"ALTER TABLE agent_chat_order_actions "
                        f"ADD COLUMN {column_name} {column_sql}"
                    )
                )
                existing_columns.add(column_name)

        for name, column in {
            "conversation_key": "conversation_key",
            "user_message_id": "user_message_id",
            "assistant_message_id": "assistant_message_id",
            "status": "status",
            "symbol": "symbol",
            "scope_hash": "scope_hash",
            "expires_at": "expires_at",
            "last_sync_at": "last_sync_at",
            "related_order_id": "related_order_id",
            "broker_order_id": "broker_order_id",
        }.items():
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_agent_chat_order_actions_{name} "
                    f"ON agent_chat_order_actions ({column})"
                )
            )


def _create_agent_chat_live_order_settings_audits_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_live_order_settings_audits (
                    id INTEGER PRIMARY KEY,
                    changed_by VARCHAR(80) NOT NULL DEFAULT 'operator_ui',
                    source VARCHAR(80) NOT NULL DEFAULT 'agent_chat_live_order_settings',
                    preset VARCHAR(80),
                    confirm_operator_ack BOOLEAN NOT NULL DEFAULT 0,
                    before_snapshot_json TEXT NOT NULL,
                    after_snapshot_json TEXT NOT NULL,
                    request_payload_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        for name, column in {
            "changed_by": "changed_by",
            "source": "source",
            "preset": "preset",
            "created_at": "created_at",
        }.items():
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    f"ix_agent_chat_live_order_settings_audits_{name} "
                    f"ON agent_chat_live_order_settings_audits ({column})"
                )
            )


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


def _create_agent_review_queue_state_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_review_queue_state (
                    id INTEGER PRIMARY KEY,
                    queue_key VARCHAR(120) NOT NULL UNIQUE,
                    item_type VARCHAR(60) NOT NULL,
                    source_id INTEGER,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    reviewed_at DATETIME,
                    dismissed_at DATETIME,
                    reviewer_note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_review_queue_state_queue_key "
                "ON agent_review_queue_state (queue_key)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_review_queue_state_item_type "
                "ON agent_review_queue_state (item_type)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_review_queue_state_source_id "
                "ON agent_review_queue_state (source_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_review_queue_state_status "
                "ON agent_review_queue_state (status)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_agent_review_queue_state_created_at "
                "ON agent_review_queue_state (created_at)"
            )
        )
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
    _create_strategy_tables_if_missing()
    _create_agent_chat_strategy_actions_table_if_missing()
    _create_strategy_performance_snapshots_table_if_missing()
    _create_strategy_live_auto_buy_attempts_table_if_missing()
    _create_strategy_auto_buy_promotions_table_if_missing()
    _create_strategy_live_auto_exit_attempts_table_if_missing()
    _seed_strategy_profiles_if_needed()
    _create_kis_shadow_exit_review_queue_state_table_if_missing()
    _create_broker_auth_tokens_table_if_missing()
    _create_trade_run_logs_table_if_missing()
    _create_agent_command_logs_table_if_missing()
    _create_agent_chat_tables_if_missing()
    _create_agent_chat_order_actions_table_if_missing()
    _create_agent_chat_live_order_settings_audits_table_if_missing()
    _create_agent_plan_tables_if_missing()
    _create_agent_execution_tables_if_missing()
    _create_agent_review_queue_state_table_if_missing()

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
        "agent_chat_live_order_enabled": "BOOLEAN DEFAULT 0",
        "agent_chat_live_order_kis_enabled": "BOOLEAN DEFAULT 0",
        "agent_chat_live_order_buy_enabled": "BOOLEAN DEFAULT 0",
        "agent_chat_live_order_sell_enabled": "BOOLEAN DEFAULT 0",
        "agent_chat_live_order_requires_confirm": "BOOLEAN DEFAULT 1",
        "agent_chat_live_order_confirm_ttl_seconds": "INTEGER DEFAULT 120",
        "agent_chat_live_order_max_orders_per_day": "INTEGER DEFAULT 1",
        "agent_chat_live_order_max_notional_pct": "FLOAT DEFAULT 0.03",
        "agent_chat_live_order_max_notional_krw": "FLOAT DEFAULT 50000",
        "agent_chat_live_order_allow_market_order": "BOOLEAN DEFAULT 1",
        "agent_chat_live_order_allow_limit_order": "BOOLEAN DEFAULT 0",
        "agent_chat_live_order_requires_recent_price": "BOOLEAN DEFAULT 1",
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
        "strategy_live_auto_buy_enabled": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_buy_requires_recent_dry_run": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_buy_recent_dry_run_ttl_minutes": "INTEGER DEFAULT 30",
        "strategy_live_auto_buy_max_orders_per_day": "INTEGER DEFAULT 1",
        "strategy_live_auto_buy_max_notional_krw": "FLOAT DEFAULT 50000",
        "strategy_live_auto_buy_max_notional_pct": "FLOAT DEFAULT 0.03",
        "strategy_live_auto_buy_allowed_profiles": "TEXT DEFAULT '[\"safe\", \"balanced\"]'",
        "strategy_live_auto_buy_allow_aggressive": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_buy_requires_operator_confirm": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_buy_block_after_loss_limit": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_buy_block_after_target_hit": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_buy_scheduler_enabled": "BOOLEAN DEFAULT 0",
        "strategy_auto_buy_scheduler_enabled": "BOOLEAN DEFAULT 0",
        "strategy_auto_buy_scheduler_dry_run_only": "BOOLEAN DEFAULT 1",
        "strategy_auto_buy_scheduler_allow_live_orders": "BOOLEAN DEFAULT 0",
        "strategy_auto_buy_scheduler_profile_source": "VARCHAR(20) DEFAULT 'active'",
        "strategy_auto_buy_scheduler_max_runs_per_day": "INTEGER DEFAULT 3",
        "strategy_auto_buy_scheduler_min_minutes_between_runs": "INTEGER DEFAULT 60",
        "strategy_auto_buy_scheduler_promotion_ttl_minutes": "INTEGER DEFAULT 45",
        "strategy_auto_buy_scheduler_create_promotion_on_would_buy": "BOOLEAN DEFAULT 1",
        "strategy_auto_buy_scheduler_block_when_kill_switch": "BOOLEAN DEFAULT 1",
        "strategy_auto_buy_scheduler_block_when_market_closed": "BOOLEAN DEFAULT 1",
        "strategy_auto_buy_scheduler_block_after_no_new_entry_time": "BOOLEAN DEFAULT 1",
        "strategy_auto_buy_scheduler_no_new_entry_after": "VARCHAR(5) DEFAULT '15:00'",
        "strategy_auto_buy_scheduler_allowed_profiles": "TEXT DEFAULT '[\"safe\", \"balanced\"]'",
        "strategy_auto_buy_scheduler_allow_aggressive": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_enabled": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_requires_operator_confirm": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_exit_max_orders_per_day": "INTEGER DEFAULT 1",
        "strategy_live_auto_exit_max_notional_krw": "FLOAT DEFAULT 50000",
        "strategy_live_auto_exit_max_position_pct": "FLOAT DEFAULT 1.0",
        "strategy_live_auto_exit_allow_stop_loss": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_exit_allow_take_profit": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_allow_max_holding_days": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_allow_monthly_loss_exit": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_exit_allow_target_hit_reduce": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_allowed_profiles": "TEXT DEFAULT '[\"safe\", \"balanced\"]'",
        "strategy_live_auto_exit_allow_aggressive": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_scheduler_enabled": "BOOLEAN DEFAULT 0",
        "strategy_live_auto_exit_requires_cost_basis": "BOOLEAN DEFAULT 1",
        "strategy_live_auto_exit_min_quantity": "INTEGER DEFAULT 1",
        "position_management_scheduler_enabled": "BOOLEAN DEFAULT 0",
        "position_management_scheduler_dry_run_only": "BOOLEAN DEFAULT 1",
        "position_management_scheduler_allow_live_orders": "BOOLEAN DEFAULT 0",
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
