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

from app.db.database import Base
from app.db import models  # noqa: F401
from app.db.init_db import init_db

init_db()


def pytest_sessionfinish(session, exitstatus):
    try:
        from app.db.database import engine

        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_TEST_DB_RUN_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_file_backed_test_database():
    from app.db.database import engine

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
