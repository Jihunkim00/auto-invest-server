import os
import shutil
import tempfile
from pathlib import Path

os.environ.setdefault("ALPACA_API_KEY", "test-key")
os.environ.setdefault("ALPACA_SECRET_KEY", "test-secret")
os.environ.setdefault("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# app.db.database builds its SQLAlchemy engine at import time, so tests must
# point DATABASE_URL at an isolated writable DB before any app DB imports.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_DB_ROOT = _REPO_ROOT / ".tmp_pytest_auto_invest"
_TEST_DB_ROOT.mkdir(exist_ok=True)
_TEST_DB_RUN_DIR = Path(
    tempfile.mkdtemp(prefix="run_", dir=str(_TEST_DB_ROOT))
).resolve()
_TEST_DB_PATH = _TEST_DB_RUN_DIR / "test_auto_invest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

get_settings.cache_clear()

from app.db.database import Base, engine
from app.db import models  # noqa: F401
from app.db.init_db import init_db

def _assert_safe_test_database() -> None:
    raw_path = engine.url.database

    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError(
            f"REFUSING pytest DB access: unexpected database={engine.url}"
        )

    if not raw_path or raw_path == ":memory:":
        raise RuntimeError(
            f"REFUSING pytest DB access: invalid database={engine.url}"
        )

    db_path = Path(raw_path).resolve()
    test_root = _TEST_DB_ROOT.resolve()

    try:
        db_path.relative_to(test_root)
    except ValueError as exc:
        raise RuntimeError(
            f"REFUSING destructive pytest access outside test DB: {db_path}"
        ) from exc

    if db_path.name != "test_auto_invest.db":
        raise RuntimeError(
            f"REFUSING unexpected pytest DB file: {db_path}"
        )

_assert_safe_test_database()
init_db()


def pytest_sessionfinish(session, exitstatus):
    try:
        
        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_TEST_DB_RUN_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_file_backed_test_database():
    _assert_safe_test_database()
    from app.services.market_data_snapshot_service import MarketDataSnapshotService

    MarketDataSnapshotService.clear_process_cache()

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
