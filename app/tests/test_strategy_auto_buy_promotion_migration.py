from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.db import init_db as init_db_module


def test_strategy_auto_buy_promotion_migration_adds_trace_columns(
    tmp_path: Path,
    monkeypatch,
):
    db_path = tmp_path / "promotion_migration.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    monkeypatch.setattr(init_db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE strategy_auto_buy_promotions (
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
                    request_payload TEXT,
                    response_payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )

    init_db_module._create_strategy_auto_buy_promotions_table_if_missing()
    init_db_module._create_strategy_auto_buy_promotions_table_if_missing()

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("strategy_auto_buy_promotions")
    }
    assert {
        "converted_live_attempt_id",
        "converted_order_id",
        "converted_at",
        "conversion_status",
        "last_sync_at",
        "last_sync_status",
        "trace_payload_json",
    }.issubset(columns)
    engine.dispose()
