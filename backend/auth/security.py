"""
auth/security.py — Password hashing and JWT, using only the standard library.

WHY STDLIB:
  Keeping auth dependency-free (no bcrypt C-extension, no PyJWT) means the
  account system installs and runs cleanly on every platform, including the
  Windows machines this project is developed on.

  - Passwords:  PBKDF2-HMAC-SHA256, 240k iterations, per-user random salt.
  - Tokens:     compact HS256 JWTs signed with a server secret.

These are the same primitives the popular libraries use under the hood.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

# ── Server secret ───────────────────────────────────────────────────────────────
# Read from env in production. For local dev we generate one once and persist it
# so issued tokens survive a server restart.
_SECRET_FILE = Path(__file__).resolve().parent.parent / ".auth_secret"


def _load_secret() -> bytes:
    env = os.getenv("ALPHASTOCK_SECRET")
    if env:
        return env.encode("utf-8")
    try:
        if _SECRET_FILE.exists():
            return _SECRET_FILE.read_bytes()
        token = secrets.token_bytes(48)
        _SECRET_FILE.write_bytes(token)
        return token
    except OSError:
        # Fall back to a process-lifetime secret if the file can't be written.
        return secrets.token_bytes(48)


_SECRET = _load_secret()

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

# ── Password hashing ────────────────────────────────────────────────────────────
_PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ── JWT (HS256) ─────────────────────────────────────────────────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": str(user_id), "email": email, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(_SECRET, signing_input, hashlib.sha256).digest()
    segments.append(_b64url(signature))
    return ".".join(segments)


def decode_token(token: str) -> dict | None:
    """Return the payload if the token is valid and unexpired, else None."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(_SECRET, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
