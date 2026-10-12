"""
SAAS SENDBID — Files router
POST   /v1/files                              Upload (multipart)
GET    /v1/files                              Liste des fichiers de l'utilisateur
GET    /v1/files/{file_id}                    Stream (auth requise)
GET    /v1/files/{file_id}/meta               Métadonnées JSON
GET    /v1/files/{file_id}/signed             Génère une URL signée
GET    /v1/files/{file_id}/download?expires=&sig=  Download via URL signée (sans auth header)
DELETE /v1/files/{file_id}                    Suppression logique
"""
import uuid
from datetime import datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.auth import AuthContext, get_auth_context
from app.config import settings
from app.database import get_db
from app.utils.audit import log_access
from app.utils.file_validation import validate_upload, prevent_path_traversal
from app.utils.image_processing import strip_exif_and_reencode
from app.utils.storage import (
    save_file_to_disk,
    delete_file_from_disk,
    generate_signed_url,
    verify_signed_url,
    build_stored_path,
)

router = APIRouter(prefix="/v1/files", tags=["files"])


# ──────────────────────────────────────────────
#  POST /v1/files — Upload
# ──────────────────────────────────────────────
@router.post("", response_model=schemas.FileUploadResponse, status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    owner_user_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """Upload a file with validation, EXIF stripping, and secure storage."""
    # Determine effective owner
    effective_owner = owner_user_id or auth.user_id

    # Validate & read file
    content, mime_type = await validate_upload(file, category)

    # Strip EXIF metadata for images
    content = strip_exif_and_reencode(content, mime_type)

    # Generate server-side file ID and path
    file_id = str(uuid.uuid4())
    original_name = prevent_path_traversal(file.filename or "")

    # Persist to disk
    abs_path, checksum = await save_file_to_disk(content, category, file_id)
    relative_path = build_stored_path(category, file_id)

    # Save metadata to DB
    stored_file = models.StoredFile(
        id=file_id,
        owner_user_id=effective_owner,
        category=category,
        original_filename=original_name[:512] if original_name else None,
        stored_path=relative_path,
        mime_type=mime_type,
        size_bytes=len(content),
        checksum_sha256=checksum,
    )
    db.add(stored_file)
    await db.commit()
    await db.refresh(stored_file)

    # Audit log
    await log_access(
        db, file_id, auth.user_id, auth.role, "upload",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # URL publique uniquement pour les avatars
    url = None
    is_public = (category == "avatars")
    if is_public:
        url = f"{settings.cdn_base_url}/v1/public/avatars/{file_id}"

    return schemas.FileUploadResponse(
        file_id=file_id,
        category=category,
        size=len(content),
        mime=mime_type,
        checksum=checksum,
        url=url,
        public=is_public,
    )


# ──────────────────────────────────────────────
#  GET /v1/files — List user's files
# ──────────────────────────────────────────────
@router.get("", response_model=list[schemas.FileMetaResponse])
async def list_files(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """List files owned by the authenticated user (or all files for admin)."""
    query = select(models.StoredFile).where(models.StoredFile.is_deleted == False)

    if not auth.is_admin:
        query = query.where(models.StoredFile.owner_user_id == auth.user_id)

    if category:
        query = query.where(models.StoredFile.category == category)

    result = await db.execute(query.order_by(models.StoredFile.created_at.desc()).limit(100))
    files = result.scalars().all()

    items = []
    for f in files:
        pub = (f.category == "avatars")
        url = f"{settings.cdn_base_url}/v1/public/avatars/{f.id}" if pub else None
        items.append(schemas.FileMetaResponse(
            file_id=f.id,
            owner_user_id=f.owner_user_id,
            category=f.category,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            checksum_sha256=f.checksum_sha256,
            created_at=f.created_at,
            is_deleted=f.is_deleted,
            is_public=pub,
            url=url,
        ))
    return items


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/meta
# ──────────────────────────────────────────────
@router.get("/{file_id}/meta", response_model=schemas.FileMetaResponse)
async def get_file_meta(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    pub = (stored_file.category == "avatars")
    url = f"{settings.cdn_base_url}/v1/public/avatars/{stored_file.id}" if pub else None

    return schemas.FileMetaResponse(
        file_id=stored_file.id,
        owner_user_id=stored_file.owner_user_id,
        category=stored_file.category,
        mime_type=stored_file.mime_type,
        size_bytes=stored_file.size_bytes,
        checksum_sha256=stored_file.checksum_sha256,
        created_at=stored_file.created_at,
        is_deleted=stored_file.is_deleted,
        is_public=pub,
        url=url,
    )


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id} — Authenticated stream (sensitive files)
# ──────────────────────────────────────────────
@router.get("/{file_id}")
async def stream_file(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """Stream a file — performs authorization check for sensitive categories."""
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    # Audit every access to sensitive files
    if not stored_file.is_public():
        await log_access(
            db, file_id, auth.user_id, auth.role, "download",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    return await _stream_response(stored_file)


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/signed — Get signed URL
# ──────────────────────────────────────────────
@router.get("/{file_id}/signed", response_model=schemas.SignedURLResponse)
async def get_signed_url(
    file_id: str,
    ttl: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """Generate a short-lived signed URL for a sensitive file."""
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    signed_url, expires_at = generate_signed_url(file_id, ttl)
    return schemas.SignedURLResponse(
        file_id=file_id,
        signed_url=signed_url,
        expires_at=expires_at,
        ttl_seconds=ttl or settings.signed_url_ttl,
    )


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/download — Signed URL download (no auth header needed)
# ──────────────────────────────────────────────
@router.get("/{file_id}/download")
async def download_via_signed_url(
    file_id: str,
    expires: str,
    sig: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Download via signed URL (for sharing links with short TTL)."""
    if not verify_signed_url(file_id, expires, sig):
        raise HTTPException(
            status_code=403,
            detail="Signed URL is invalid or has expired",
        )

    stored_file = await _get_file_or_404(db, file_id)

    # Audit log
    await log_access(
        db, file_id, "signed_url", "signed_url", "download_signed",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=f"expires={expires}",
    )

    return await _stream_response(stored_file)


# ──────────────────────────────────────────────
#  DELETE /v1/files/{file_id} — Soft delete
# ──────────────────────────────────────────────
@router.delete("/{file_id}", response_model=schemas.DeleteResponse)
async def delete_file(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """Soft-delete a file (marks as deleted; purge happens via scheduled job)."""
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    stored_file.is_deleted = True
    stored_file.deleted_at = datetime.utcnow()
    await db.commit()

    await log_access(
        db, file_id, auth.user_id, auth.role, "delete",
        ip_address=request.client.host if request.client else None,
    )

    return schemas.DeleteResponse(file_id=file_id)


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────
async def _get_file_or_404(db: AsyncSession, file_id: str) -> models.StoredFile:
    result = await db.execute(
        select(models.StoredFile).where(
            models.StoredFile.id == file_id,
            models.StoredFile.is_deleted == False,
        )
    )
    stored_file = result.scalar_one_or_none()
    if not stored_file:
        raise HTTPException(status_code=404, detail="File not found")
    return stored_file


def _check_access(auth: AuthContext, stored_file: models.StoredFile):
    if not auth.can_access_file(stored_file.owner_user_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not own this file",
        )


async def _stream_response(stored_file: models.StoredFile) -> StreamingResponse:
    abs_path = settings.upload_path / stored_file.stored_path

    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File data not found on disk")

    async def file_iterator():
        async with aiofiles.open(abs_path, "rb") as f:
            while chunk := await f.read(65536):  # 64KB chunks
                yield chunk

    headers = {
        "Content-Disposition": f'inline; filename="{stored_file.id}"',
        "Content-Length": str(stored_file.size_bytes),
        "X-Content-Type-Options": "nosniff",
    }

    # Sensitive files: no caching, no indexing
    if not stored_file.is_public():
        headers.update({
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": "default-src 'none'",
        })
    else:
        headers["Cache-Control"] = "public, max-age=31536000, immutable"

    return StreamingResponse(
        file_iterator(),
        media_type=stored_file.mime_type,
        headers=headers,
    )
