"""
StorageHub — Authentication middleware
- Per-client API key + HMAC-SHA256 verification (service-to-service)
- Master API key from env (internal/admin use)
- JWT session auth for the client dashboard
- User identity extraction (X-User-Id / X-User-Role)
"""
import hashlib
import hmac
import time
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app import models
from app.utils.security import decode_session_token


class AuthContext:
    """Extracted auth info from a request."""

    def __init__(
        self,
        user_id: str,
        role: str = "user",
        is_service: bool = False,
        client_id: Optional[str] = None,
        plan: str = "internal",
    ):
        self.user_id = user_id
        self.role = role
        self.is_service = is_service
        self.client_id = client_id  # tenant (None for master key)
        self.plan = plan

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "kyc_agent")

    def can_access_file(self, file_owner_id: str, file_client_id: Optional[str] = None) -> bool:
        """Check if this caller may access a file."""
        if self.user_id == file_owner_id or self.is_admin:
            return True
        # A client key can access files uploaded through that same client
        if self.client_id and file_client_id and self.client_id == file_client_id:
            return True
        return False


def _verify_hmac_signature(
    api_key: str,
    timestamp: str,
    signature: str,
    body: bytes,
    secret: str,
) -> bool:
    """
    Verify service-to-service HMAC-SHA256 signature.
    Message = api_key + ":" + timestamp + ":" + sha256(body)
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    # Timestamp tolerance check
    tolerance = settings.hmac_timestamp_tolerance_seconds
    if abs(time.time() - ts) > tolerance:
        return False

    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{api_key}:{timestamp}:{body_hash}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature)


async def _resolve_api_key(
    db: AsyncSession, api_key: str
) -> tuple[Optional[str], Optional[str], str]:
    """
    Resolve an API key to (hmac_secret, client_id, plan).
    Returns (None, None, "") if unknown.
    """
    # Master key from env — internal/admin use, no quota
    if hmac.compare_digest(api_key, settings.api_key):
        return settings.hmac_secret, None, "internal"

    # Client key in DB
    result = await db.execute(
        select(models.ApiKey).where(
            models.ApiKey.api_key == api_key,
            models.ApiKey.revoked == False,
        )
    )
    key_row = result.scalar_one_or_none()
    if not key_row:
        return None, None, ""

    # Key's client must be active
    result = await db.execute(
        select(models.Client).where(models.Client.id == key_row.client_id)
    )
    client = result.scalar_one_or_none()
    if not client or not client.is_active:
        return None, None, ""

    key_row.last_used_at = datetime.utcnow()
    await db.commit()
    return key_row.hmac_secret, key_row.client_id, client.plan


async def get_auth_context(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency that validates auth and returns an AuthContext.

    Two modes:
    1. Full service-to-service: X-API-Key + X-Timestamp + X-Signature
       The backend passes the end-user identity via X-User-Id / X-User-Role.
    2. Simple API key (dev/test only): X-API-Key alone.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    hmac_secret, client_id, plan = await _resolve_api_key(db, x_api_key)
    if hmac_secret is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    # HMAC verification (production mode)
    if x_timestamp and x_signature:
        try:
            body = await request.body()
        except RuntimeError:
            # Multipart uploads: FastAPI consumes the stream while parsing
            # form fields before this dependency runs. The client signs
            # sha256(b"") for uploads, so treat the body as empty.
            body = b""
        if not _verify_hmac_signature(
            x_api_key, x_timestamp, x_signature, body, hmac_secret
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired HMAC signature",
            )
        is_service = True
    else:
        # Dev mode: simple API key only
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="HMAC signature required in production",
            )
        is_service = False

    user_id = x_user_id or "anonymous"
    role = x_user_role or "user"

    return AuthContext(
        user_id=user_id, role=role, is_service=is_service,
        client_id=client_id, plan=plan,
    )


async def get_current_client(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> models.Client:
    """Dashboard session auth — Bearer JWT → Client."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    client_id = decode_session_token(authorization[7:])
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    result = await db.execute(
        select(models.Client).where(models.Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client or not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or disabled",
        )
    return client
