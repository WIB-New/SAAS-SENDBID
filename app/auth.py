"""
SAAS SENDBID — Authentication middleware
- API key validation
- HMAC + timestamp verification (service-to-service)
- User identity extraction
"""
import hashlib
import hmac
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import settings


class AuthContext:
    """Extracted auth info from a request."""

    def __init__(
        self,
        user_id: str,
        role: str = "user",
        is_service: bool = False,
    ):
        self.user_id = user_id
        self.role = role
        self.is_service = is_service

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "kyc_agent")

    def can_access_file(self, file_owner_id: str) -> bool:
        """Check if this caller may access a file owned by file_owner_id."""
        return self.user_id == file_owner_id or self.is_admin


def _verify_api_key(api_key: str) -> bool:
    return hmac.compare_digest(api_key, settings.api_key)


def _verify_hmac_signature(
    api_key: str,
    timestamp: str,
    signature: str,
    body: bytes = b"",
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
    expected = hmac.new(
        settings.hmac_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def get_auth_context(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_timestamp: Optional[str] = Header(None, alias="X-Timestamp"),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> AuthContext:
    """
    FastAPI dependency that validates auth and returns an AuthContext.

    Two modes:
    1. Full service-to-service: X-API-Key + X-Timestamp + X-Signature
       The Django backend passes the end-user identity via X-User-Id / X-User-Role.
    2. Simple API key (dev/test only): X-API-Key alone.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    if not _verify_api_key(x_api_key):
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
        if not _verify_hmac_signature(x_api_key, x_timestamp, x_signature, body):
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

    return AuthContext(user_id=user_id, role=role, is_service=is_service)
