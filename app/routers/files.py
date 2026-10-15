"""
StorageHub — Files router v2
POST   /v1/files                              Upload (multipart) — avec virus scan, chiffrement, thumbnail, tags
POST   /v1/files/bulk                         Upload multiple fichiers
POST   /v1/files/from-url                     Importer depuis une URL distante
GET    /v1/files                              Liste paginée des fichiers
GET    /v1/files/{file_id}                    Stream (auth requise)
GET    /v1/files/{file_id}/thumbnail          Miniature JPEG
GET    /v1/files/{file_id}/meta               Métadonnées JSON
PATCH  /v1/files/{file_id}/tags               Mettre à jour les tags
GET    /v1/files/{file_id}/signed             Génère une URL signée
GET    /v1/files/{file_id}/download           Download via URL signée
GET    /v1/files/{file_id}/versions           Historique des versions
POST   /v1/files/{file_id}/replace            Remplacer (nouvelle version)
DELETE /v1/files/{file_id}                    Suppression logique
"""
import json
import uuid
from datetime import datetime
from typing import Optional

import aiofiles
import httpx
from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.auth import AuthContext, get_auth_context
from app.config import get_plan, settings
from app.database import get_db
from app.ratelimit import upload_limit, bulk_limit, url_limit
from app.utils.audit import log_access
from app.utils.encryption import decrypt_bytes, encrypt_bytes, should_encrypt
from app.utils.file_validation import validate_upload, prevent_path_traversal, validate_category
from app.utils.image_processing import strip_exif_and_reencode
from app.utils.storage import (
    generate_signed_url,
    verify_signed_url,
    build_stored_path,
    save_file_to_disk,
    delete_file_from_disk,
)
from app.utils.thumbnails import generate_thumbnail, save_thumbnail, get_thumbnail_url
from app.utils.virus_scanner import scan_content, scan_with_virustotal

router = APIRouter(prefix="/v1/files", tags=["files"])


# ──────────────────────────────────────────────
#  Helpers internes
# ──────────────────────────────────────────────
async def _get_file_or_404(db: AsyncSession, file_id: str) -> models.StoredFile:
    result = await db.execute(
        select(models.StoredFile).where(
            models.StoredFile.id == file_id,
            models.StoredFile.is_deleted == False,
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return f


def _check_access(auth: AuthContext, stored_file: models.StoredFile):
    if not auth.can_access_file(stored_file.owner_user_id, stored_file.client_id):
        raise HTTPException(status_code=403, detail="Access denied: you do not own this file")


def _file_meta(f: models.StoredFile) -> schemas.FileMetaResponse:
    pub = f.is_public()
    url = f"{settings.cdn_base_url}/v1/public/avatars/{f.id}" if pub else None
    thumb = get_thumbnail_url(f.id, settings.cdn_base_url) if f.thumbnail_path else None
    return schemas.FileMetaResponse(
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
        thumbnail_url=thumb,
        tags=f.tags,
        version=f.version,
        parent_id=f.parent_id,
        is_encrypted=f.is_encrypted,
    )


async def _do_upload(
    content: bytes,
    mime_type: str,
    category: str,
    original_filename: Optional[str],
    auth: AuthContext,
    db: AsyncSession,
    tags: Optional[dict] = None,
    parent_id: Optional[str] = None,
    parent_version: int = 0,
) -> schemas.FileUploadResponse:
    """Logique commune d'upload — utilisée par upload_file, bulk et from-url."""

    # 1. Scan antivirus
    safe, reason = scan_content(content, original_filename or "")
    if not safe:
        raise HTTPException(status_code=400, detail=f"File rejected: {reason}")

    # VirusTotal optionnel
    if settings.virustotal_api_key:
        vt_safe, vt_reason = await scan_with_virustotal(
            content, original_filename or "", settings.virustotal_api_key
        )
        if not vt_safe:
            raise HTTPException(status_code=400, detail=f"File rejected: {vt_reason}")

    # 2. Traitement image (strip EXIF)
    content = strip_exif_and_reencode(content, mime_type)

    # 3. Génération du thumbnail (avant chiffrement)
    thumb_bytes = generate_thumbnail(content, mime_type)

    # 4. Chiffrement KYC / reçus
    encrypted_content = encrypt_bytes(content, category)
    is_enc = should_encrypt(category)

    # 5. Persistance sur disque
    file_id = str(uuid.uuid4())
    abs_path, checksum = await save_file_to_disk(encrypted_content, category, file_id)
    relative_path = build_stored_path(category, file_id)

    # 6. Thumbnail
    thumb_relative = None
    if thumb_bytes:
        thumb_relative = await save_thumbnail(thumb_bytes, file_id)

    # 7. Métadonnées en base
    stored_file = models.StoredFile(
        id=file_id,
        client_id=auth.client_id,
        owner_user_id=auth.user_id,
        category=category,
        original_filename=prevent_path_traversal(original_filename or "")[:512] or None,
        stored_path=relative_path,
        mime_type=mime_type,
        size_bytes=len(content),       # taille non chiffrée
        checksum_sha256=checksum,
        thumbnail_path=thumb_relative,
        is_encrypted=is_enc,
        tags=tags,
        parent_id=parent_id,
        version=parent_version + 1,
    )
    db.add(stored_file)
    await db.commit()
    await db.refresh(stored_file)

    pub = (category == "avatars")
    url = f"{settings.cdn_base_url}/v1/public/avatars/{file_id}" if pub else None
    thumb_url = get_thumbnail_url(file_id, settings.cdn_base_url) if thumb_relative else None

    return schemas.FileUploadResponse(
        file_id=file_id,
        category=category,
        size=len(content),
        mime=mime_type,
        checksum=checksum,
        url=url,
        thumbnail_url=thumb_url,
        public=pub,
        version=parent_version + 1,
    )


# ──────────────────────────────────────────────
#  POST /v1/files — Upload simple
# ──────────────────────────────────────────────
@router.post("", response_model=schemas.FileUploadResponse, status_code=201,
             summary="Upload un fichier (avatar, KYC, reçu)")
async def upload_file(
    request: Request,
    _rl=Depends(upload_limit),
    file: UploadFile = File(...),
    category: str = Form(...),
    owner_user_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None, description="JSON object de tags, ex: {\"order_id\":\"123\"}"),
    replaces_file_id: Optional[str] = Form(None, description="ID du fichier à remplacer (nouvelle version)"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    # Quota SaaS
    content, mime_type = await validate_upload(file, category)
    if auth.client_id:
        await _check_quota(db, auth, len(content))

    # Tags parsing
    tags_dict = None
    if tags:
        try:
            tags_dict = json.loads(tags)
            if not isinstance(tags_dict, dict):
                raise ValueError
        except Exception:
            raise HTTPException(status_code=400, detail="tags must be a valid JSON object")

    # Versioning
    parent_version = 0
    parent_id = None
    if replaces_file_id:
        parent_file = await _get_file_or_404(db, replaces_file_id)
        _check_access(auth, parent_file)
        parent_id = replaces_file_id
        parent_version = parent_file.version

    result = await _do_upload(content, mime_type, category, file.filename, auth, db, tags_dict, parent_id, parent_version)

    await log_access(
        db, result.file_id, auth.user_id, auth.role, "upload",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # Webhook
    try:
        from app.routers.webhooks import fire_event
        await fire_event("file.uploaded", {
            "file_id": result.file_id, "category": category, "size": result.size
        }, auth.client_id, db)
    except Exception:
        pass

    return result


# ──────────────────────────────────────────────
#  POST /v1/files/bulk — Upload multiple
# ──────────────────────────────────────────────
@router.post("/bulk", response_model=schemas.BulkUploadResponse, status_code=201,
             summary="Upload plusieurs fichiers en une seule requête")
async def upload_bulk(
    request: Request,
    _rl=Depends(bulk_limit),
    files: list[UploadFile] = File(...),
    category: str = Form(...),
    tags: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    validate_category(category)
    tags_dict = None
    if tags:
        try:
            tags_dict = json.loads(tags)
        except Exception:
            raise HTTPException(status_code=400, detail="tags must be a valid JSON object")

    results = []
    uploaded, failed = 0, 0

    for f in files:
        try:
            content, mime_type = await validate_upload(f, category)
            if auth.client_id:
                await _check_quota(db, auth, len(content))
            res = await _do_upload(content, mime_type, category, f.filename, auth, db, tags_dict)
            results.append(schemas.BulkUploadResult(
                filename=f.filename,
                success=True,
                file_id=res.file_id,
                url=res.url,
                thumbnail_url=res.thumbnail_url,
            ))
            uploaded += 1
        except HTTPException as exc:
            results.append(schemas.BulkUploadResult(
                filename=f.filename, success=False, error=str(exc.detail)
            ))
            failed += 1

    return schemas.BulkUploadResponse(uploaded=uploaded, failed=failed, results=results)


# ──────────────────────────────────────────────
#  POST /v1/files/from-url — Import depuis URL
# ──────────────────────────────────────────────
@router.post("/from-url", response_model=schemas.FileUploadResponse, status_code=201,
             summary="Importer un fichier depuis une URL distante")
async def upload_from_url(
    request: Request,
    _rl=Depends(url_limit),
    url: str = Body(..., embed=True),
    category: str = Body(..., embed=True),
    tags: Optional[dict] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    validate_category(category)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    max_bytes = settings.max_sizes_bytes[category]
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client_http:
            async with client_http.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(65536):
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Remote file too large (max {max_bytes // 1024 // 1024} MB)"
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    filename = url.split("/")[-1].split("?")[0] or "remote_file"

    # Valider le contenu téléchargé comme un vrai upload
    from fastapi.datastructures import UploadFile as FUploadFile
    import io
    from app.utils.file_validation import validate_category as _vc, detect_mime_from_magic, is_dangerous_file
    from app.utils.file_validation import VALID_CATEGORIES

    _vc(category)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if is_dangerous_file(content):
        raise HTTPException(status_code=400, detail="Executable files are not allowed")
    mime_type = detect_mime_from_magic(content)
    if not mime_type or mime_type not in settings.allowed_mimes.get(category, []):
        raise HTTPException(status_code=400, detail=f"File type not allowed for category '{category}'")

    if auth.client_id:
        await _check_quota(db, auth, len(content))

    return await _do_upload(content, mime_type, category, filename, auth, db, tags)


# ──────────────────────────────────────────────
#  GET /v1/files — Liste paginée
# ──────────────────────────────────────────────
@router.get("", response_model=schemas.PaginatedFiles,
            summary="Lister les fichiers (paginé)")
async def list_files(
    category: Optional[str] = None,
    page: int = Query(1, ge=1, description="Numéro de page"),
    limit: int = Query(20, ge=1, le=100, description="Fichiers par page"),
    sort: str = Query("created_at:desc", description="Tri : champ:asc|desc"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    query = select(models.StoredFile).where(
        models.StoredFile.is_deleted == False,
        models.StoredFile.parent_id.is_(None),  # Ne montrer que la dernière version (v1 ou remplacée)
    )

    if auth.client_id:
        query = query.where(models.StoredFile.client_id == auth.client_id)
        if not auth.is_admin:
            query = query.where(models.StoredFile.owner_user_id == auth.user_id)
    elif not auth.is_admin:
        query = query.where(models.StoredFile.owner_user_id == auth.user_id)

    if category:
        query = query.where(models.StoredFile.category == category)

    # Total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Tri
    sort_field, _, sort_dir = sort.partition(":")
    sort_col = getattr(models.StoredFile, sort_field, models.StoredFile.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Pagination
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    files = result.scalars().all()

    return schemas.PaginatedFiles(
        items=[_file_meta(f) for f in files],
        total=total,
        page=page,
        limit=limit,
        pages=max(1, (total + limit - 1) // limit),
    )


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/thumbnail
# ──────────────────────────────────────────────
@router.get("/{file_id}/thumbnail", summary="Miniature JPEG du fichier")
async def get_thumbnail(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    if not stored_file.thumbnail_path:
        raise HTTPException(status_code=404, detail="No thumbnail available for this file")

    abs_path = settings.upload_path / stored_file.thumbnail_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found on disk")

    async with aiofiles.open(abs_path, "rb") as f:
        data = await f.read()

    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/meta
# ──────────────────────────────────────────────
@router.get("/{file_id}/meta", response_model=schemas.FileMetaResponse,
            summary="Métadonnées d'un fichier")
async def get_file_meta(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)
    return _file_meta(stored_file)


# ──────────────────────────────────────────────
#  PATCH /v1/files/{file_id}/tags
# ──────────────────────────────────────────────
@router.patch("/{file_id}/tags", response_model=schemas.FileMetaResponse,
              summary="Mettre à jour les tags d'un fichier")
async def update_tags(
    file_id: str,
    tags: dict = Body(..., embed=True, description="Objet JSON de tags"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)
    stored_file.tags = tags
    await db.commit()
    await db.refresh(stored_file)
    return _file_meta(stored_file)


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id} — Stream authentifié
# ──────────────────────────────────────────────
@router.get("/{file_id}", summary="Télécharger un fichier (authentifié)")
async def stream_file(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    if not stored_file.is_public():
        await log_access(
            db, file_id, auth.user_id, auth.role, "download",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    return await _stream_response(stored_file)


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/versions
# ──────────────────────────────────────────────
@router.get("/{file_id}/versions", response_model=list[schemas.FileMetaResponse],
            summary="Historique des versions d'un fichier")
async def list_versions(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    current = await _get_file_or_404(db, file_id)
    _check_access(auth, current)

    # Trouver la racine de la chaîne
    root_id = current.id
    visited = {current.id}
    f = current
    while f.parent_id and f.parent_id not in visited:
        visited.add(f.parent_id)
        r = await db.execute(select(models.StoredFile).where(models.StoredFile.id == f.parent_id))
        f = r.scalar_one_or_none()
        if f:
            root_id = f.id

    # Récupérer toutes les versions
    result = await db.execute(
        select(models.StoredFile).where(
            (models.StoredFile.id == root_id) | (models.StoredFile.parent_id == root_id)
        ).order_by(models.StoredFile.version.asc())
    )
    versions = result.scalars().all()
    return [_file_meta(v) for v in versions]


# ──────────────────────────────────────────────
#  POST /v1/files/{file_id}/replace — Nouvelle version
# ──────────────────────────────────────────────
@router.post("/{file_id}/replace", response_model=schemas.FileUploadResponse, status_code=201,
             summary="Remplacer un fichier par une nouvelle version")
async def replace_file(
    file_id: str,
    request: Request,
    _rl=Depends(upload_limit),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    parent = await _get_file_or_404(db, file_id)
    _check_access(auth, parent)

    content, mime_type = await validate_upload(file, parent.category)
    if auth.client_id:
        await _check_quota(db, auth, len(content))

    return await _do_upload(
        content, mime_type, parent.category, file.filename, auth, db,
        tags=parent.tags, parent_id=parent.id, parent_version=parent.version
    )


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/signed
# ──────────────────────────────────────────────
@router.get("/{file_id}/signed", response_model=schemas.SignedURLResponse,
            summary="Générer une URL signée temporaire")
async def get_signed_url(
    file_id: str,
    ttl: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    if auth.client_id:
        max_ttl = get_plan(auth.plan).get("signed_url_max_ttl", 60)
        effective_ttl = min(ttl, max_ttl) if ttl else None
    else:
        effective_ttl = ttl

    signed_url, expires_at = generate_signed_url(file_id, effective_ttl)
    return schemas.SignedURLResponse(
        file_id=file_id,
        signed_url=signed_url,
        expires_at=expires_at,
        ttl_seconds=effective_ttl or settings.signed_url_ttl,
    )


# ──────────────────────────────────────────────
#  GET /v1/files/{file_id}/download — Via URL signée
# ──────────────────────────────────────────────
@router.get("/{file_id}/download", summary="Télécharger via URL signée (sans auth header)")
async def download_via_signed_url(
    file_id: str,
    expires: str,
    sig: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not verify_signed_url(file_id, expires, sig):
        raise HTTPException(status_code=403, detail="Signed URL is invalid or has expired")

    stored_file = await _get_file_or_404(db, file_id)
    await log_access(
        db, file_id, "signed_url", "signed_url", "download_signed",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=f"expires={expires}",
    )
    return await _stream_response(stored_file)


# ──────────────────────────────────────────────
#  DELETE /v1/files/{file_id}
# ──────────────────────────────────────────────
@router.delete("/{file_id}", response_model=schemas.DeleteResponse,
               summary="Suppression logique d'un fichier")
async def delete_file(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    stored_file = await _get_file_or_404(db, file_id)
    _check_access(auth, stored_file)

    stored_file.is_deleted = True
    stored_file.deleted_at = datetime.utcnow()
    await db.commit()

    await log_access(
        db, file_id, auth.user_id, auth.role, "delete",
        ip_address=request.client.host if request.client else None,
    )

    # Webhook
    try:
        from app.routers.webhooks import fire_event
        await fire_event("file.deleted", {"file_id": file_id}, auth.client_id, db)
    except Exception:
        pass

    return schemas.DeleteResponse(file_id=file_id)


# ──────────────────────────────────────────────
#  Helpers privés
# ──────────────────────────────────────────────
async def _check_quota(db: AsyncSession, auth: AuthContext, new_bytes: int):
    """Vérifie le quota de stockage du plan SaaS."""
    plan = get_plan(auth.plan)
    limit_bytes = plan["storage_mb"] * 1024 * 1024
    result = await db.execute(
        select(func.coalesce(func.sum(models.StoredFile.size_bytes), 0)).where(
            models.StoredFile.client_id == auth.client_id,
            models.StoredFile.is_deleted == False,
        )
    )
    used = result.scalar() or 0
    if used + new_bytes > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Storage quota exceeded for plan '{plan['name']}' "
                f"({plan['storage_mb']} MB). Upgrade via POST /v1/accounts/plan."
            ),
        )


async def _stream_response(stored_file: models.StoredFile) -> StreamingResponse:
    abs_path = settings.upload_path / stored_file.stored_path

    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File data not found on disk")

    # Chiffrement : lire + déchiffrer avant de streamer
    if stored_file.is_encrypted:
        async with aiofiles.open(abs_path, "rb") as f:
            encrypted = await f.read()
        data = decrypt_bytes(encrypted, stored_file.category)

        headers = {
            "Content-Disposition": f'attachment; filename="{stored_file.original_filename or stored_file.id}"',
            "Content-Length": str(len(data)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow",
        }
        return StreamingResponse(iter([data]), media_type=stored_file.mime_type, headers=headers)

    # Fichier non chiffré : streaming par chunks
    async def file_iterator():
        async with aiofiles.open(abs_path, "rb") as f:
            while chunk := await f.read(65536):
                yield chunk

    headers = {
        "Content-Disposition": f'inline; filename="{stored_file.original_filename or stored_file.id}"',
        "Content-Length": str(stored_file.size_bytes),
        "X-Content-Type-Options": "nosniff",
    }
    if not stored_file.is_public():
        headers.update({
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": "default-src 'none'",
        })
    else:
        headers["Cache-Control"] = "public, max-age=31536000, immutable"

    return StreamingResponse(file_iterator(), media_type=stored_file.mime_type, headers=headers)
