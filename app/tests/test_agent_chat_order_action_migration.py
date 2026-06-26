from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.db import init_db as init_db_module


@pytest.fixture()
def migration_engine(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "agent_chat_order_actions_migration.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    monkeypatch.setattr(init_db_module, "engine", engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_legacy_table_without_last_sync_at_is_migrated_idempotently(
    migration_engine,
):
    _create_legacy_pr67_table(migration_engine)

    init_db_module._create_agent_chat_order_actions_table_if_missing()
    init_db_module._create_agent_chat_order_actions_table_if_missing()

    columns = _columns(migration_engine)
    indexes = _indexes(migration_engine)
    assert "last_sync_at" in columns
    assert "last_sync_payload_json" in columns
    assert "ix_agent_chat_order_actions_last_sync_at" in indexes
    assert _row_count(migration_engine) == 1
    with migration_engine.connect() as conn:
        row = conn.execute(
            text("SELECT conversation_key, symbol FROM agent_chat_order_actions WHERE id = 1")
        ).one()
    assert row[0] == "legacy-conversation"
    assert row[1] == "005930"


def test_partial_sync_columns_table_gets_only_missing_sync_column(
    migration_engine,
):
    _create_partial_pr68_table(migration_engine)

    init_db_module._create_agent_chat_order_actions_table_if_missing()
    init_db_module._create_agent_chat_order_actions_table_if_missing()

    columns = _columns(migration_engine)
    assert "last_state_change_at" in columns
    assert "last_sync_at" in columns
    assert "last_sync_payload_json" in columns
    assert "ix_agent_chat_order_actions_last_sync_at" in _indexes(migration_engine)
    assert _row_count(migration_engine) == 1


def test_fresh_agent_chat_order_actions_table_has_sync_index(
    migration_engine,
):
    init_db_module._create_agent_chat_order_actions_table_if_missing()
    init_db_module._create_agent_chat_order_actions_table_if_missing()

    columns = _columns(migration_engine)
    assert "last_sync_at" in columns
    assert "last_sync_payload_json" in columns
    assert "ix_agent_chat_order_actions_last_sync_at" in _indexes(migration_engine)


def _create_legacy_pr67_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE agent_chat_order_actions (
                    id INTEGER PRIMARY KEY,
                    conversation_key VARCHAR(80) NOT NULL,
                    user_message_id INTEGER,
                    action_type VARCHAR(60) NOT NULL DEFAULT 'chat_confirmed_live_order',
                    provider VARCHAR(20) NOT NULL DEFAULT 'kis',
                    market VARCHAR(10) NOT NULL DEFAULT 'KR',
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    status VARCHAR(40) NOT NULL DEFAULT 'pending_confirmation',
                    scope_hash VARCHAR(64) NOT NULL,
                    confirmation_phrase VARCHAR(200) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    related_order_id INTEGER,
                    broker_order_id VARCHAR(100),
                    request_payload_json TEXT,
                    response_payload_json TEXT,
                    safety_payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_chat_order_actions (
                    id, conversation_key, user_message_id, symbol, side,
                    status, scope_hash, confirmation_phrase, expires_at
                )
                VALUES (
                    1, 'legacy-conversation', 7, '005930', 'buy',
                    'submitted', 'legacy-scope', 'CONFIRM',
                    '2026-06-26T00:00:00'
                )
                """
            )
        )


def _create_partial_pr68_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE agent_chat_order_actions (
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
                    status VARCHAR(40) NOT NULL DEFAULT 'pending_confirmation',
                    scope_hash VARCHAR(64) NOT NULL,
                    confirmation_phrase VARCHAR(200) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    last_state_change_at DATETIME,
                    related_order_id INTEGER,
                    broker_order_id VARCHAR(100),
                    last_sync_payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_chat_order_actions (
                    id, conversation_key, user_message_id, assistant_message_id,
                    symbol, side, status, scope_hash, confirmation_phrase,
                    expires_at, last_state_change_at, last_sync_payload_json
                )
                VALUES (
                    1, 'partial-conversation', 7, 8, '005930', 'buy',
                    'sync_required', 'partial-scope', 'CONFIRM',
                    '2026-06-26T00:00:00', '2026-06-25T00:00:00',
                    '{"sync_status":"pending"}'
                )
                """
            )
        )


def _columns(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(agent_chat_order_actions)"))
        }


def _indexes(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA index_list(agent_chat_order_actions)"))
        }


def _row_count(engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(text("SELECT COUNT(*) FROM agent_chat_order_actions")).scalar_one()
        )
