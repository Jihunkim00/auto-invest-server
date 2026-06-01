from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

connect_args = {}

if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}


def _sqlite_database_path(database_url: str) -> Path | None:
    try:
        url = make_url(database_url)
    except Exception:
        return None
    if url.get_backend_name() != "sqlite":
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    database_path = _sqlite_database_path(database_url)
    if database_path is None:
        return
    parent = database_path.expanduser().parent
    if str(parent) in {"", "."}:
        return
    parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
