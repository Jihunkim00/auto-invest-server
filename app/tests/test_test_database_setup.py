from pathlib import Path

from sqlalchemy import text

from app.db.database import engine, settings


def test_pytest_database_uses_writable_temp_sqlite_file():
    database_url = settings.database_url

    assert database_url.startswith("sqlite:///")
    assert ".tmp_pytest_auto_invest" in database_url
    assert not database_url.endswith("sqlite:///./test_auto_invest.db")

    raw_path = database_url.replace("sqlite:///", "", 1)
    db_path = Path(raw_path)
    assert db_path.name == "test_auto_invest.db"
    assert db_path.parent.exists()

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS pytest_write_probe"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS pytest_write_probe "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        conn.execute(text("DELETE FROM pytest_write_probe"))
        conn.execute(text("INSERT INTO pytest_write_probe (value) VALUES ('ok')"))
        value = conn.execute(text("SELECT value FROM pytest_write_probe")).scalar_one()
        conn.execute(text("DROP TABLE pytest_write_probe"))

    assert value == "ok"
