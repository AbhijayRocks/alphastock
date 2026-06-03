"""
auth/deps.py — FastAPI dependency that resolves the authenticated user.

Usage in a route:
    @router.get("/something")
    def handler(user: User = Depends(get_current_user)):
        ...
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from auth.db import get_db
from auth.models import User
from auth.security import decode_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user
