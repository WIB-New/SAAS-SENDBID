"""
SAAS SENDBID — Pydantic schemas (request/response)
Toutes les réponses suivent un contrat cohérent pour l'intégration.
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models import FileCategory


# ──────────────────────────────────────────────
#  Enveloppe de réponse standardisée
# ──────────────────────────────────────────────
class ApiResponse(BaseModel):
    """Enveloppe commune à toutes les réponses de succès."""
    success: bool = True
    request_id: Optional[str] = None
    data: Any = None


class ApiError(BaseModel):
    """Enveloppe commune à toutes les réponses d'erreur."""
    success: bool = False
    request_id: Optional[str] = None
    error: str
    code: str                   # Machine-readable error code (ex: FILE_TOO_LARGE)
    detail: Optional[str] = None
    field: Optional[str] = None # Champ concerné si erreur de validation


# ──────────────────────────────────────────────
#  Codes d'erreur standardisés
# ──────────────────────────────────────────────
class ErrorCode:
    # Auth
    MISSING_API_KEY        = "MISSING_API_KEY"
    INVALID_API_KEY        = "INVALID_API_KEY"
    INVALID_HMAC           = "INVALID_HMAC"
    HMAC_REQUIRED          = "HMAC_REQUIRED"
    FORBIDDEN              = "FORBIDDEN"
    # Upload
    EMPTY_FILE             = "EMPTY_FILE"
    FILE_TOO_LARGE         = "FILE_TOO_LARGE"
    INVALID_MIME           = "INVALID_MIME"
    DANGEROUS_FILE         = "DANGEROUS_FILE"
    INVALID_CATEGORY       = "INVALID_CATEGORY"
    IMAGE_PROCESSING_ERROR = "IMAGE_PROCESSING_ERROR"
    # Access
    FILE_NOT_FOUND         = "FILE_NOT_FOUND"
    ACCESS_DENIED          = "ACCESS_DENIED"
    # Signed URL
    SIGNED_URL_INVALID     = "SIGNED_URL_INVALID"
    SIGNED_URL_EXPIRED     = "SIGNED_URL_EXPIRED"
    # Server
    INTERNAL_ERROR         = "INTERNAL_ERROR"
    DATABASE_ERROR         = "DATABASE_ERROR"
    STORAGE_ERROR          = "STORAGE_ERROR"


# ──────────────────────────────────────────────
#  Upload
# ──────────────────────────────────────────────
class FileUploadResponse(BaseModel):
    file_id: str
    category: str
    size: int
    mime: str
    checksum: str
    url: Optional[str] = None       # URL publique CDN — avatars seulement
    public: bool = False            # True si le fichier est public
    message: str = "Upload successful"


# ──────────────────────────────────────────────
#  Métadonnées fichier
# ──────────────────────────────────────────────
class FileMetaResponse(BaseModel):
    file_id: str
    owner_user_id: str
    category: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    created_at: datetime
    is_deleted: bool
    is_public: bool
    url: Optional[str] = None       # URL publique si avatars, null sinon

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
#  URL signée
# ──────────────────────────────────────────────
class SignedURLResponse(BaseModel):
    file_id: str
    signed_url: str
    expires_at: datetime
    ttl_seconds: int
    method: str = "GET"


# ──────────────────────────────────────────────
#  Suppression
# ──────────────────────────────────────────────
class DeleteResponse(BaseModel):
    file_id: str
    deleted: bool = True
    message: str = "File marked for deletion"


# ──────────────────────────────────────────────
#  Health
# ──────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"              # ok | degraded | error
    version: str = "1.0.0"
    env: str
    uptime_seconds: Optional[float] = None
    db: str                         # ok | error: ...
    disk_usage: dict
    categories: dict
    checks: dict = {}               # résultats détaillés des checks


# ──────────────────────────────────────────────
#  Audit
# ──────────────────────────────────────────────
class AuditLogEntry(BaseModel):
    id: int
    file_id: str
    requester_user_id: str
    requester_role: str
    action: str
    ip_address: Optional[str]
    timestamp: datetime
    success: bool
    details: Optional[str]

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
#  Ping (liveness check minimal)
# ──────────────────────────────────────────────
class PingResponse(BaseModel):
    pong: bool = True
    version: str = "1.0.0"
    service: str = "sendbid-storage"
