"""
StorageHub — Pydantic schemas (request/response)
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field
from app.models import FileCategory


# ── Enveloppe standard ─────────────────────────────────────────────────────────
class ApiResponse(BaseModel):
    success: bool = True
    request_id: Optional[str] = None
    data: Any = None


class ApiError(BaseModel):
    success: bool = False
    request_id: Optional[str] = None
    error: str
    code: str
    detail: Optional[str] = None
    field: Optional[str] = None


# ── Codes d'erreur ─────────────────────────────────────────────────────────────
class ErrorCode:
    MISSING_API_KEY        = "MISSING_API_KEY"
    INVALID_API_KEY        = "INVALID_API_KEY"
    INVALID_HMAC           = "INVALID_HMAC"
    HMAC_REQUIRED          = "HMAC_REQUIRED"
    FORBIDDEN              = "FORBIDDEN"
    EMPTY_FILE             = "EMPTY_FILE"
    FILE_TOO_LARGE         = "FILE_TOO_LARGE"
    INVALID_MIME           = "INVALID_MIME"
    DANGEROUS_FILE         = "DANGEROUS_FILE"
    MALWARE_DETECTED       = "MALWARE_DETECTED"
    INVALID_CATEGORY       = "INVALID_CATEGORY"
    IMAGE_PROCESSING_ERROR = "IMAGE_PROCESSING_ERROR"
    FILE_NOT_FOUND         = "FILE_NOT_FOUND"
    ACCESS_DENIED          = "ACCESS_DENIED"
    SIGNED_URL_INVALID     = "SIGNED_URL_INVALID"
    SIGNED_URL_EXPIRED     = "SIGNED_URL_EXPIRED"
    INTERNAL_ERROR         = "INTERNAL_ERROR"
    DATABASE_ERROR         = "DATABASE_ERROR"
    STORAGE_ERROR          = "STORAGE_ERROR"
    QUOTA_EXCEEDED         = "QUOTA_EXCEEDED"
    RATE_LIMIT_EXCEEDED    = "RATE_LIMIT_EXCEEDED"


# ── Upload ─────────────────────────────────────────────────────────────────────
class FileUploadResponse(BaseModel):
    file_id:       str
    category:      str
    size:          int
    mime:          str
    checksum:      str
    url:           Optional[str] = None
    thumbnail_url: Optional[str] = None
    public:        bool = False
    version:       int  = 1
    message:       str  = "Upload successful"


class BulkUploadResult(BaseModel):
    filename:  Optional[str] = None
    success:   bool
    file_id:   Optional[str]  = None
    error:     Optional[str]  = None
    thumbnail_url: Optional[str] = None
    url:       Optional[str]  = None


class BulkUploadResponse(BaseModel):
    uploaded: int
    failed:   int
    results:  list[BulkUploadResult]


# ── Métadonnées fichier ─────────────────────────────────────────────────────────
class FileMetaResponse(BaseModel):
    file_id:          str
    owner_user_id:    str
    category:         str
    mime_type:        str
    size_bytes:       int
    checksum_sha256:  str
    created_at:       datetime
    is_deleted:       bool
    is_public:        bool
    url:              Optional[str]  = None
    thumbnail_url:    Optional[str]  = None
    tags:             Optional[dict] = None
    version:          int = 1
    parent_id:        Optional[str]  = None
    is_encrypted:     bool = False

    class Config:
        from_attributes = True


class PaginatedFiles(BaseModel):
    items:  list[FileMetaResponse]
    total:  int
    page:   int
    limit:  int
    pages:  int


# ── URL signée ─────────────────────────────────────────────────────────────────
class SignedURLResponse(BaseModel):
    file_id:     str
    signed_url:  str
    expires_at:  datetime
    ttl_seconds: int
    method:      str = "GET"


# ── Suppression ────────────────────────────────────────────────────────────────
class DeleteResponse(BaseModel):
    file_id: str
    deleted: bool = True
    message: str  = "File marked for deletion"


# ── Health ─────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status:         str = "ok"
    version:        str = "2.0.0"
    env:            str
    uptime_seconds: Optional[float] = None
    db:             str
    disk_usage:     dict
    categories:     dict
    checks:         dict = {}


# ── Audit ──────────────────────────────────────────────────────────────────────
class AuditLogEntry(BaseModel):
    id:                int
    file_id:           str
    requester_user_id: str
    requester_role:    str
    action:            str
    ip_address:        Optional[str]
    timestamp:         datetime
    success:           bool
    details:           Optional[str]

    class Config:
        from_attributes = True


# ── Ping ───────────────────────────────────────────────────────────────────────
class PingResponse(BaseModel):
    pong:    bool = True
    version: str  = "2.0.0"
    service: str  = "storagehub"


# ── Webhooks ───────────────────────────────────────────────────────────────────
class WebhookCreate(BaseModel):
    url:    str   = Field(..., max_length=2048)
    secret: Optional[str] = Field(None, max_length=128, description="Secret HMAC pour signer les payloads")
    events: str   = Field("*", description="'*' ou liste CSV: 'file.uploaded,file.deleted'")


class WebhookResponse(BaseModel):
    id:         str
    url:        str
    events:     str
    is_active:  bool
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookDeliveryResponse(BaseModel):
    id:              int
    webhook_id:      str
    event:           str
    response_status: Optional[int]
    success:         bool
    error:           Optional[str]
    attempted_at:    datetime

    class Config:
        from_attributes = True


# ── Stats analytiques ──────────────────────────────────────────────────────────
class DailyUploadStat(BaseModel):
    date:       str
    count:      int
    size_bytes: int


class StatsResponse(BaseModel):
    total_files:      int
    active_files:     int
    deleted_files:    int
    total_size_bytes: int
    by_category:      dict
    uploads_by_day:   list[DailyUploadStat]
    encrypted_files:  int
    thumbnail_count:  int
