"""
auth/db.py — Database engine and session factory.

We use SQLite by default (a single file, zero external services) so the
account system works out of the box on any machine. Point DATABASE_URL at
Postgres in production and nothing else changes.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Default: a SQLite file living next to the backend package.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "alpha_stock.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")

# check_same_thread is a SQLite-only quirk; FastAPI may touch the session
# from different threads, and this is the documented way to allow it.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (no-op if they exist)."""
    # Import models so they register on Base.metadata before create_all.
    from auth import models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
