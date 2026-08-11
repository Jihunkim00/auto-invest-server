from __future__ import annotations

import importlib

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db.models import StrategyProfile


def _create_legacy_strategy_profiles_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE strategy_profiles (
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
                    is_builtin BOOLEAN NOT NULL DEFAULT 1
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO strategy_profiles (
                    id, profile_name, display_name, description,
                    monthly_target_return_pct, monthly_target_min_pct,
                    monthly_target_max_pct, monthly_max_loss_pct,
                    daily_max_loss_pct, max_order_notional_pct,
                    max_order_notional_krw, max_trades_per_day, max_positions,
                    buy_score_threshold, sell_score_threshold, stop_loss_pct,
                    take_profit_pct, max_holding_days, is_active, is_builtin
                ) VALUES (
                    77, 'legacy-safe', 'Legacy safe', 'keep this row',
                    0.03, 0.01, 0.05, 0.05,
                    0.02, 0.03, 50000, 2, 1,
                    62, 55, -0.03, 0.06, 10, 1, 1
                )
                """
            )
        )


def test_legacy_strategy_profile_startup_migration_is_idempotent(monkeypatch):
    init_db_module = importlib.import_module("app.db.init_db")
    engine = create_engine("sqlite:///:memory:", future=True)
    _create_legacy_strategy_profiles_table(engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        future=True,
    )
    monkeypatch.setattr(init_db_module, "engine", engine)
    monkeypatch.setattr(init_db_module, "SessionLocal", session_factory)

    try:
        init_db_module.init_db()
        init_db_module.init_db()

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("strategy_profiles")
        }
        assert {
            "profile_key",
            "custom_name",
            "provider",
            "market",
            "enabled",
            "custom_status",
            "settings_json",
            "created_at",
            "updated_at",
        }.issubset(columns)

        with session_factory() as db:
            legacy = db.get(StrategyProfile, 77)
            assert legacy is not None
            assert legacy.profile_name == "legacy-safe"
            assert legacy.display_name == "Legacy safe"
            assert legacy.description == "keep this row"
            assert legacy.created_at is not None
            assert legacy.updated_at is not None
            assert db.query(StrategyProfile).count() >= 4
    finally:
        engine.dispose()
