from sqlalchemy import inspect, text

from app.db.database import engine
from app.db.models import Base


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


def _create_runtime_settings_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runtime_settings (
                    id INTEGER PRIMARY KEY,
                    bot_enabled BOOLEAN NOT NULL DEFAULT 1,
                    kill_switch BOOLEAN NOT NULL DEFAULT 0,
                    default_symbol VARCHAR(20) NOT NULL DEFAULT 'AAPL',
                    default_gate_level INTEGER NOT NULL DEFAULT 2,
                    max_trades_per_day INTEGER NOT NULL DEFAULT 3,
                    global_daily_entry_limit INTEGER NOT NULL DEFAULT 2,
                    per_symbol_daily_entry_limit INTEGER NOT NULL DEFAULT 1,
                    per_slot_new_entry_limit INTEGER NOT NULL DEFAULT 1,
                    max_open_positions INTEGER NOT NULL DEFAULT 3,
                    near_close_block_minutes INTEGER NOT NULL DEFAULT 15,
                    same_direction_cooldown_minutes INTEGER NOT NULL DEFAULT 120,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )


def _create_trade_run_logs_table_if_missing():
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS trade_run_logs (
                    id INTEGER PRIMARY KEY,
                    run_key VARCHAR(64) NOT NULL,
                    trigger_source VARCHAR(20) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    mode VARCHAR(30) NOT NULL DEFAULT 'entry_scan',
                    parent_run_key VARCHAR(64),
                    symbol_role VARCHAR(30),
                    gate_level INTEGER,
                    stage VARCHAR(20) NOT NULL DEFAULT 'precheck',
                    result VARCHAR(20) NOT NULL DEFAULT 'pending',
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
    _create_runtime_settings_table_if_missing()
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
        "kill_switch": "BOOLEAN DEFAULT 0",
        "default_symbol": "VARCHAR(20) DEFAULT 'AAPL'",
        "default_gate_level": "INTEGER DEFAULT 2",
        "max_trades_per_day": "INTEGER DEFAULT 3",
        "global_daily_entry_limit": "INTEGER DEFAULT 2",
        "per_symbol_daily_entry_limit": "INTEGER DEFAULT 1",
        "per_slot_new_entry_limit": "INTEGER DEFAULT 1",
        "max_open_positions": "INTEGER DEFAULT 3",
        "near_close_block_minutes": "INTEGER DEFAULT 15",
        "same_direction_cooldown_minutes": "INTEGER DEFAULT 120",
    }

    trade_run_log_columns = {
        "mode": "VARCHAR(30) DEFAULT 'entry_scan'",
        "parent_run_key": "VARCHAR(64)",
        "symbol_role": "VARCHAR(30)",
    }

    for name, ddl in signal_columns.items():
        _add_column_if_missing("signals", name, ddl)

    for name, ddl in market_analysis_columns.items():
        _add_column_if_missing("market_analysis", name, ddl)

    for name, ddl in runtime_setting_columns.items():
        _add_column_if_missing("runtime_settings", name, ddl)

    for name, ddl in trade_run_log_columns.items():
        _add_column_if_missing("trade_run_logs", name, ddl)

    _create_trade_run_logs_optional_indexes_if_possible()