"""
auth/ — Authentication, user accounts, and per-user persistence.

This package is intentionally self-contained and dependency-light so the
account system runs even when the heavy ML stack is not loaded:

  db.py        SQLAlchemy engine + session (SQLite, zero-config)
  models.py    The User ORM model (credentials + personalization)
  security.py  PBKDF2 password hashing + HS256 JWT (stdlib only)
  schemas.py   Pydantic request/response contracts
  deps.py      FastAPI dependency that resolves the current user
  routes.py    /api/auth/* and /api/user/* endpoints
"""

from auth.db import Base, engine, init_db
from auth.routes import router as auth_router

__all__ = ["Base", "engine", "init_db", "auth_router"]
