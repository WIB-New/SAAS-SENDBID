"""
SAAS SENDBID — Security utilities
- Password hashing (PBKDF2-HMAC-SHA256, stdlib)
- JWT session tokens for the client dashboard
- API credential generation
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from app.config import settings

PBKDF2_ITERATIONS = 200_000
SESSION_TTL_DAYS = 7
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return 'salt$hash' — both hex-encoded."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return hmac.compare_digest(candidate, digest)


def generate_api_credentials() -> tuple[str, str]:
    """Return (api_key, hmac_secret) for a new client key."""
    return f"shk_{secrets.token_hex(20)}", secrets.token_hex(32)


def create_session_token(client_id: str) -> str:
    payload = {
        "sub": client_id,
        "type": "dashboard",
        "exp": datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.hmac_secret, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> Optional[str]:
    """Return client_id or None."""
    try:
        payload = jwt.decode(token, settings.hmac_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "dashboard":
        return None
    return payload.get("sub")
