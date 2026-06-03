"""
auth/models.py — The User ORM model.

One row per account. Personalization that used to live in the browser's
localStorage (watchlist + preferences) now belongs to the user, so the
experience follows them across devices. Saved portfolios let a user keep
named allocations from the optimizer.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, JSON

from auth.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Defaults applied to brand-new accounts.
DEFAULT_WATCHLIST = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "BHARTIARTL.NS"]
DEFAULT_PREFERENCES = {"horizon": "5d", "model": "ensemble_clf"}


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    display_name  = Column(String(120), nullable=False, default="")
    password_hash = Column(String(255), nullable=False)

    # Per-user personalization (JSON columns — SQLite stores these as TEXT).
    watchlist     = Column(JSON, nullable=False, default=list)
    preferences   = Column(JSON, nullable=False, default=dict)
    portfolios    = Column(JSON, nullable=False, default=list)

    created_at    = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    def to_public(self) -> dict:
        """Shape returned to the client — never includes the password hash."""
        return {
            "id":            self.id,
            "email":         self.email,
            "display_name":  self.display_name or self.email.split("@")[0],
            "watchlist":     self.watchlist or [],
            "preferences":   self.preferences or dict(DEFAULT_PREFERENCES),
            "portfolios":    self.portfolios or [],
            "created_at":    self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
