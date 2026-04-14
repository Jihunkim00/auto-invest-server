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


def init_db():
    Base.metadata.create_all(bind=engine)
    _create_reference_site_cache_table_if_missing()

    # Lightweight SQLite-friendly migration for existing signals table
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
        "signal_status": "VARCHAR(30)",
        "trigger_source": "VARCHAR(30)",
        "timeframe": "VARCHAR(20)",
    }

    for name, ddl in signal_columns.items():
        _add_column_if_missing("signals", name, ddl)