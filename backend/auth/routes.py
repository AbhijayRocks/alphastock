"""
auth/routes.py — Account + personalization endpoints.

  POST /api/auth/register   create an account, returns a session token
  POST /api/auth/login      authenticate, returns a session token
  GET  /api/auth/me         current account (requires token)
  PATCH /api/auth/me        update profile (display name)
  GET  /api/user/data       fetch this user's watchlist / preferences / portfolios
  PUT  /api/user/data       persist a partial update of the above
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.db import get_db
from auth.deps import get_current_user
from auth.models import User, DEFAULT_WATCHLIST, DEFAULT_PREFERENCES
from auth.schemas import (
    RegisterRequest, LoginRequest, AuthResponse, UserOut,
    ProfileUpdate, UserDataUpdate,
)
from auth.security import hash_password, verify_password, create_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _auth_response(user: User) -> AuthResponse:
    token = create_token(user.id, user.email)
    return AuthResponse(token=token, user=UserOut(**user.to_public()))


# ── Register ────────────────────────────────────────────────────────────────────
@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    display = (body.display_name or "").strip() or body.email.split("@")[0]
    user = User(
        email=body.email,
        display_name=display,
        password_hash=hash_password(body.password),
        watchlist=list(DEFAULT_WATCHLIST),
        preferences=dict(DEFAULT_PREFERENCES),
        portfolios=[],
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"New account registered: {user.email}")
    return _auth_response(user)


# ── Login ───────────────────────────────────────────────────────────────────────
@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        # Same message for both cases — don't leak which emails exist.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


# ── Current user ────────────────────────────────────────────────────────────────
@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(**user.to_public())


@router.patch("/auth/me", response_model=UserOut)
def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or user.display_name
    db.commit()
    db.refresh(user)
    return UserOut(**user.to_public())


# ── Personalization ─────────────────────────────────────────────────────────────
@router.get("/user/data", response_model=UserOut)
def get_user_data(user: User = Depends(get_current_user)):
    return UserOut(**user.to_public())


@router.put("/user/data", response_model=UserOut)
def update_user_data(
    body: UserDataUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.watchlist is not None:
        # De-dupe while preserving order; cap to a sane size.
        seen, cleaned = set(), []
        for t in body.watchlist:
            if t not in seen:
                seen.add(t)
                cleaned.append(t)
        user.watchlist = cleaned[:100]
    if body.preferences is not None:
        merged = dict(user.preferences or {})
        merged.update(body.preferences)
        user.preferences = merged
    if body.portfolios is not None:
        user.portfolios = body.portfolios[:50]
    db.commit()
    db.refresh(user)
    return UserOut(**user.to_public())
