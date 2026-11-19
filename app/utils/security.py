"""
StorageHub — Security utilities
- Password hashing (PBKDF2-HMAC-SHA256, stdlib)
- JWT session tokens for the client dashboard
- API credential generation
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from app.utils.time import utcnow
from typing import Optional

from jose import JWTError, jwt

from app.config import settings

PBKDF2_ITERATIONS = 200_000
SESSION_TTL_DAYS = 7
JWT_ALGORITHM = "HS256"


def derive_secret(purpose: str) -> str:
    """
    Séparation des domaines cryptographiques : le HMAC_SECRET maître dérive
    un secret distinct par usage (JWT dashboard, URLs signées). Une fuite
    d'un domaine ne permet pas de forger les artefacts des autres.
    """
    return hmac.new(
        settings.hmac_secret.encode(),
        f"storagehub:{purpose}".encode(),
        hashlib.sha256,
    ).hexdigest()


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


def hash_api_key(api_key: str) -> str:
    """
    Empreinte SHA-256 d'une clé API — c'est ce qui est stocké en base.
    Une fuite de la table api_keys n'expose plus les clés utilisables.
    """
    return "sha256$" + hashlib.sha256(api_key.encode()).hexdigest()


def api_key_hint(api_key: str) -> str:
    """Forme masquée affichable : 'shk_ab12…wxyz'."""
    return f"{api_key[:10]}…{api_key[-4:]}" if len(api_key) > 14 else "…"


def create_session_token(client_id: str) -> str:
    payload = {
        "sub": client_id,
        "type": "dashboard",
        "exp": utcnow() + timedelta(days=SESSION_TTL_DAYS),
        "iat": utcnow(),
    }
    return jwt.encode(payload, derive_secret("dashboard-jwt"), algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> Optional[str]:
    """Return client_id or None."""
    try:
        payload = jwt.decode(token, derive_secret("dashboard-jwt"), algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "dashboard":
        return None
    return payload.get("sub")
