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


def init_db():
    Base.metadata.create_all(bind=engine)
    _create_reference_site_cache_table_if_missing()
    _create_company_events_table_if_missing()
    _create_runtime_settings_table_if_missing()
    _create_kis_shadow_exit_review_queue_state_table_if_missing()
    _create_broker_auth_tokens_table_if_missing()
    _create_trade_run_logs_table_if_missing()

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
