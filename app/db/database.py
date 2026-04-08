from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

connect_args = {}

if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

print("DATABASE_URL =", settings.database_url)

if settings.database_url.startswith("sqlite:///"):
    raw_path = settings.database_url.replace("sqlite:///", "", 1)
    print("SQLITE_RAW_PATH =", raw_path)
    print("SQLITE_ABS_PATH =", Path(raw_path).resolve())

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