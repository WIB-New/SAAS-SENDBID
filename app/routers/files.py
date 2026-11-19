"""
StorageHub — Files router v2
POST   /v1/files                              Upload (multipart) — avec virus scan, chiffrement, thumbnail, tags
POST   /v1/files/bulk                         Upload multiple fichiers
POST   /v1/files/from-url                     Importer depuis une URL distante
GET    /v1/files                              Liste paginée (filtres: category, folder, q)
GET    /v1/files/folders                      Arborescence des dossiers logiques
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
import re
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

import aiofiles
import httpx
from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import models, schemas
import asyncio
from app.auth import AuthContext, get_auth_context
from app.config import get_plan, settings
from app.database import get_db
from app.ratelimit import bulk_limit, url_limit, plan_upload_limit
from app.utils.audit import log_access
from app.utils.encryption import decrypt_bytes, encrypt_bytes, should_encrypt, looks_encrypted
from app.utils.file_validation import validate_upload, prevent_path_traversal, validate_category, sanitize_folder
from app.utils.image_processing import strip_exif_and_reencode
from app.utils.storage import (
    generate_signed_url,
    verify_signed_url,
    build_stored_path,
    save_file_to_disk,
    compute_sha256,
)
from app.utils.thumbnails import generate_thumbnail, save_thumbnail, get_thumbnail_url
from app.utils.url_safety import resolve_pinned_url
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


# Fichier "feuille" = dernière version de sa chaîne : aucun enfant vivant.
# (parent_id pointe vers la version PRÉCÉDENTE — la racine n'est affichée que
# si elle n'a jamais été remplacée.)
def _latest_version_filter():
    child = aliased(models.StoredFile)
    return ~select(child.id).where(
        child.parent_id == models.StoredFile.id,
        child.is_deleted == False,
    ).exists()


async def _has_live_child(db: AsyncSession, file_id: str) -> bool:
    """True si une version plus récente non supprimée existe déjà."""
    r = await db.execute(
        select(func.count(models.StoredFile.id)).where(
            models.StoredFile.parent_id == file_id,
            models.StoredFile.is_deleted == False,
        )
    )
    return (r.scalar() or 0) > 0


async def _chain_root(db: AsyncSession, f: models.StoredFile) -> models.StoredFile:
    """Remonte la chaîne parent_id jusqu'à la racine (protection anti-cycle)."""
    visited = {f.id}
    while f.parent_id and f.parent_id not in visited:
        visited.add(f.parent_id)
        r = await db.execute(
            select(models.StoredFile).where(models.StoredFile.id == f.parent_id)
        )
        nxt = r.scalar_one_or_none()
        if not nxt:
            break
        f = nxt
    return f


async def _chain_rows(db: AsyncSession, root_id: str) -> list[models.StoredFile]:
    """Collecte toute la chaîne de versions (racine + descendants, BFS)."""
    rows: dict[str, models.StoredFile] = {}
    frontier = [root_id]
    while frontier:
        r = await db.execute(
            select(models.StoredFile).where(
                (models.StoredFile.id.in_(frontier))
                | (models.StoredFile.parent_id.in_(frontier))
            )
        )
        new = {row.id: row for row in r.scalars().all() if row.id not in rows}
        if not new:
            break
        rows.update(new)
        frontier = list(new)
    return list(rows.values())


def _cd_filename(name: Optional[str]) -> str:
    """
    Paramètre filename sûr pour Content-Disposition (RFC 6266/5987) —
    supprime guillemets, backslashes, CR/LF (injection de header) et
    bascule les noms non-ASCII vers filename*=UTF-8.
    """
    base = re.sub(r'[\r\n";\\]', "_", (name or "").strip())[:200] or "file"
    if base.isascii():
        return f'filename="{base}"'
    return f"filename=\"file\"; filename*=UTF-8''{quote(base)}"


_MAX_TAGS_BYTES = 4096


def _check_tags_size(tags_dict: Optional[dict]):
    if tags_dict is not None and len(json.dumps(tags_dict, default=str)) > _MAX_TAGS_BYTES:
        raise HTTPException(status_code=400, detail="tags too large (max 4 KB serialized)")


def _file_meta(f: models.StoredFile) -> schemas.FileMetaResponse:
    pub = f.is_public()
    url = f"{settings.cdn_base_url}/v1/public/avatars/{f.id}" if pub else None
    thumb = get_thumbnail_url(f.id, settings.cdn_base_url) if f.thumbnail_path else None
    return schemas.FileMetaResponse(
        file_id=f.id,
        owner_user_id=f.owner_user_id,
        category=f.category,
        original_filename=f.original_filename,
        folder=f.folder,
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
    folder: Optional[str] = None,
    owner_user_id: Optional[str] = None,
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

    # 4. Chiffrement KYC / reçus (AES-256-GCM, clé dérivée par tenant)
    is_enc = should_encrypt(category)
    encrypted_content = encrypt_bytes(content, category, tenant=auth.client_id)

    # 5. Persistance — le checksum exposé au client est celui du contenu
    #    ORIGINAL (plaintext), pas du ciphertext stocké.
    file_id = str(uuid.uuid4())
    checksum = compute_sha256(content)
    await save_file_to_disk(encrypted_content, category, file_id)
    relative_path = build_stored_path(category, file_id)

    # 6. Thumbnail — chiffrée au repos pour les catégories sensibles
    thumb_relative = None
    if thumb_bytes:
        thumb_store = encrypt_bytes(thumb_bytes, category, tenant=auth.client_id)
        thumb_relative = await save_thumbnail(thumb_store, file_id)

    # 7. Métadonnées en base
    stored_file = models.StoredFile(
        id=file_id,
        client_id=auth.client_id,
        owner_user_id=owner_user_id or auth.user_id,
        category=category,
        original_filename=prevent_path_traversal(original_filename or "")[:512] or None,
        folder=sanitize_folder(folder) if folder else None,
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
    try:
        await db.commit()
        await db.refresh(stored_file)
    except Exception:
        # Commit échoué → l'objet existe déjà sur le stockage mais sans
        # ligne en base : il serait orphelin pour toujours. Nettoyer.
        from app.utils.storage import delete_file_from_disk
        await delete_file_from_disk(relative_path)
        if thumb_relative:
            await delete_file_from_disk(thumb_relative)
        raise

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
             summary="Upload un fichier (avatars, kyc, receipts, files)")
async def upload_file(
    request: Request,
    _rl=Depends(plan_upload_limit),
    file: UploadFile = File(...),
    category: str = Form(...),
    owner_user_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None, description="JSON object de tags, ex: {\"order_id\":\"123\"}"),
    folder: Optional[str] = Form(None, description="Chemin relatif du dossier (upload de dossier)"),
    replaces_file_id: Optional[str] = Form(None, description="ID du fichier à remplacer (nouvelle version)"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    # Quota SaaS
    content, mime_type = await validate_upload(file, category)
    if auth.client_id:
        _check_file_size(auth, len(content))
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
    _check_tags_size(tags_dict)

    # Chemin de dossier (upload de dossier) — colonne dédiée, jamais sur disque
    clean_folder = sanitize_folder(folder) if folder else None

    # Upload au nom d'un utilisateur final — équivalent à X-User-Id (le client
    # contrôle déjà l'identité déclarée). Limité à 255 chars (colonne DB).
    owner = (owner_user_id or "").strip()[:255] or None

    # Versioning — on ne peut remplacer que la DERNIÈRE version d'une chaîne,
    # sinon le graphe de versions devient un arbre (plusieurs "latest").
    parent_version = 0
    parent_id = None
    if replaces_file_id:
        parent_file = await _get_file_or_404(db, replaces_file_id)
        _check_access(auth, parent_file)
        if await _has_live_child(db, parent_file.id):
            raise HTTPException(
                status_code=409,
                detail="Only the latest version can be replaced — a newer version already exists",
            )
        parent_id = replaces_file_id
        parent_version = parent_file.version

    result = await _do_upload(content, mime_type, category, file.filename, auth, db,
                              tags_dict, parent_id, parent_version,
                              folder=clean_folder, owner_user_id=owner)

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
    folder: Optional[str] = Form(None, description="Chemin relatif du dossier (upload de dossier)"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    validate_category(category)
    if auth.client_id and not get_plan(auth.plan).get("bulk_upload", False):
        raise HTTPException(
            status_code=403,
            detail="Bulk upload requires the Pro plan or higher. Upgrade via POST /v1/accounts/plan.",
        )
    if len(files) > 200:
        raise HTTPException(status_code=400, detail="Bulk upload is limited to 200 files per request")

    tags_dict = None
    if tags:
        try:
            tags_dict = json.loads(tags)
            if not isinstance(tags_dict, dict):
                raise ValueError
        except Exception:
            raise HTTPException(status_code=400, detail="tags must be a valid JSON object")
    _check_tags_size(tags_dict)

    clean_folder = sanitize_folder(folder) if folder else None

    results = []
    uploaded, failed = 0, 0

    for f in files:
        try:
            content, mime_type = await validate_upload(f, category)
            if auth.client_id:
                _check_file_size(auth, len(content))
                await _check_quota(db, auth, len(content))
            res = await _do_upload(content, mime_type, category, f.filename, auth, db,
                                   tags_dict, folder=clean_folder)
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
#  POST /v1/files/from-url — Import depuis URL# ──────────────────────────────────────────────
@router.post("/from-url", response_model=schemas.FileUploadResponse, status_code=201,
             summary="Importer un fichier depuis une URL distante")
async def upload_from_url(
    request: Request,
    _rl=Depends(url_limit),
    url: str = Body(..., embed=True),
    category: str = Body(..., embed=True),
    tags: Optional[dict] = Body(None, embed=True),
    folder: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    validate_category(category)
    _check_tags_size(tags)

    max_bytes = settings.max_sizes_bytes[category]

    async def _download() -> bytes:
        # Redirections suivies manuellement : chaque hop est re-validé et
        # épinglé sur l'IP résolue (anti DNS-rebinding) — une 302 peut
        # rebasculer vers une IP privée.
        current = url
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client_http:
            for _ in range(4):
                pinned = await resolve_pinned_url(current)
                req_kwargs: dict = {"headers": pinned["headers"]}
                if pinned["sni_hostname"]:
                    req_kwargs["extensions"] = {"sni_hostname": pinned["sni_hostname"]}
                async with client_http.stream("GET", pinned["url"], **req_kwargs) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise HTTPException(status_code=400, detail="Invalid redirect from remote URL")
                        current = urljoin(current, location)
                        continue
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
                    return b"".join(chunks)
            raise HTTPException(status_code=400, detail="Too many redirects")

    try:
        content = await asyncio.wait_for(_download(), timeout=20.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Remote file download took too long")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")

    filename = url.split("/")[-1].split("?")[0] or "remote_file"

    # Valider le contenu téléchargé comme un vrai upload
    from app.utils.file_validation import detect_mime_from_magic, is_dangerous_file

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    allowed = settings.allowed_mimes.get(category, [])
    if category != "files" and is_dangerous_file(content):
        raise HTTPException(status_code=400, detail="Executable files are not allowed")
    mime_type = detect_mime_from_magic(content)
    if not mime_type:
        if "*" in allowed:
            mime_type = "application/octet-stream"
        else:
            raise HTTPException(status_code=400, detail=f"File type not allowed for category '{category}'")
    if "*" not in allowed and mime_type not in allowed:
        raise HTTPException(status_code=400, detail=f"File type not allowed for category '{category}'")

    if auth.client_id:
        _check_file_size(auth, len(content))
        await _check_quota(db, auth, len(content))

    return await _do_upload(content, mime_type, category, filename, auth, db,
                            tags, folder=folder)


# ──────────────────────────────────────────────
#  GET /v1/files — Liste paginée
# ──────────────────────────────────────────────
@router.get("", response_model=schemas.PaginatedFiles,
            summary="Lister les fichiers (paginé)")
async def list_files(
    category: Optional[str] = None,
    folder: Optional[str] = Query(None, description="Filtrer par dossier (chemin exact)"),
    q: Optional[str] = Query(None, description="Recherche sur le nom de fichier"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    limit: int = Query(20, ge=1, le=100, description="Fichiers par page"),
    sort: str = Query("created_at:desc", description="Tri : champ:asc|desc"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    query = select(models.StoredFile).where(
        models.StoredFile.is_deleted == False,
        _latest_version_filter(),  # Ne montrer que la DERNIÈRE version de chaque chaîne
    )

    if auth.client_id:
        query = query.where(models.StoredFile.client_id == auth.client_id)
        if not (auth.is_admin or auth.is_tenant_admin):
            query = query.where(models.StoredFile.owner_user_id == auth.user_id)
    elif not auth.is_admin:
        query = query.where(models.StoredFile.owner_user_id == auth.user_id)

    if category:
        query = query.where(models.StoredFile.category == category)

    if folder is not None:
        clean = sanitize_folder(folder)
        if clean:
            query = query.where(models.StoredFile.folder == clean)
        else:
            # Chaîne vide après assainissement = racine (fichiers sans dossier)
            query = query.where(models.StoredFile.folder.is_(None))

    if q:
        query = query.where(models.StoredFile.original_filename.ilike(f"%{q}%"))

    # Total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Tri — whitelist : getattr arbitraire sur le modèle pouvait retourner des
    # relations/attributs non-colonnes → erreur SQL 500.
    _SORTABLE = {"created_at", "size_bytes", "original_filename",
                 "category", "mime_type", "version", "id"}
    sort_field, _, sort_dir = sort.partition(":")
    sort_col = getattr(models.StoredFile, sort_field, None)
    if sort_field not in _SORTABLE or sort_col is None:
        sort_col = models.StoredFile.created_at
    query = query.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

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
#  GET /v1/files/folders — Arborescence des dossiers
# ──────────────────────────────────────────────
@router.get("/folders", response_model=list[schemas.FolderInfo],
            summary="Lister les dossiers logiques avec stats")
async def list_folders(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    query = select(
        models.StoredFile.folder,
        func.count().label("file_count"),
        func.coalesce(func.sum(models.StoredFile.size_bytes), 0).label("total_bytes"),
    ).where(
        models.StoredFile.is_deleted == False,
        _latest_version_filter(),
        models.StoredFile.folder.isnot(None),
    )

    if auth.client_id:
        query = query.where(models.StoredFile.client_id == auth.client_id)
        if not (auth.is_admin or auth.is_tenant_admin):
            query = query.where(models.StoredFile.owner_user_id == auth.user_id)
    elif not auth.is_admin:
        query = query.where(models.StoredFile.owner_user_id == auth.user_id)

    query = query.group_by(models.StoredFile.folder).order_by(models.StoredFile.folder)
    result = await db.execute(query)
    return [
        schemas.FolderInfo(folder=row.folder, file_count=row.file_count,
                           total_bytes=row.total_bytes)
        for row in result.all()
    ]


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

    from app.utils.backends import get_storage_backend
    backend = get_storage_backend()
    if not await backend.exists(stored_file.thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found in storage")

    data = await backend.read(stored_file.thumbnail_path)

    # Miniatures des fichiers sensibles : chiffrées au repos → déchiffrer à la volée
    if stored_file.is_encrypted and looks_encrypted(data):
        data = decrypt_bytes(data, stored_file.category, tenant=stored_file.client_id)

    cache = ("public, max-age=86400" if stored_file.is_public()
             else "no-store, no-cache, must-revalidate, private")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": cache})


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
    _check_tags_size(tags)
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

    # Chaîne complète : remonter à la racine puis collecter tous les
    # descendants en BFS — parent_id référence le parent IMMÉDIAT, les
    # versions profondes (v3+) étaient invisibles avec un lookup plat.
    root = await _chain_root(db, current)
    versions = [
        v for v in await _chain_rows(db, root.id)
        if not v.is_deleted
    ]
    versions.sort(key=lambda v: v.version)
    return [_file_meta(v) for v in versions]


# ──────────────────────────────────────────────
#  POST /v1/files/{file_id}/replace — Nouvelle version
# ──────────────────────────────────────────────
@router.post("/{file_id}/replace", response_model=schemas.FileUploadResponse, status_code=201,
             summary="Remplacer un fichier par une nouvelle version")
async def replace_file(
    file_id: str,
    request: Request,
    _rl=Depends(plan_upload_limit),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    parent = await _get_file_or_404(db, file_id)
    _check_access(auth, parent)

    # On ne peut remplacer que la dernière version — sinon la chaîne
    # devient un arbre et "latest" n'est plus défini.
    if await _has_live_child(db, parent.id):
        raise HTTPException(
            status_code=409,
            detail="Only the latest version can be replaced — a newer version already exists",
        )

    content, mime_type = await validate_upload(file, parent.category)
    if auth.client_id:
        _check_file_size(auth, len(content))
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
    ttl: Optional[int] = Query(None, ge=1, le=86400),
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

    # Supprimer un fichier supprime toute sa chaîne de versions —
    # sinon les anciennes versions resteraient orphelines en base.
    # La chaîne est une liste chaînée (parent → version précédente) :
    # remonter à la racine puis collecter tous les descendants en BFS.
    root = await _chain_root(db, stored_file)
    now = datetime.utcnow()
    for f in await _chain_rows(db, root.id):
        if not f.is_deleted:
            f.is_deleted = True
            f.deleted_at = now
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
def _check_file_size(auth: AuthContext, size_bytes: int):
    """Applique la limite max_file_size_mb du plan (en plus de la limite par catégorie)."""
    max_bytes = get_plan(auth.plan).get("max_file_size_mb", 0) * 1024 * 1024
    if max_bytes and size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File exceeds the {get_plan(auth.plan)['max_file_size_mb']} MB "
                f"limit of plan '{get_plan(auth.plan)['name']}'. "
                "Upgrade via POST /v1/accounts/plan."
            ),
        )


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
    from app.utils.backends import get_storage_backend, LocalBackend
    backend = get_storage_backend()

    if not await backend.exists(stored_file.stored_path):
        raise HTTPException(status_code=404, detail="File data not found in storage")

    # Chiffrement : lire + déchiffrer avant de streamer
    if stored_file.is_encrypted:
        encrypted = await backend.read(stored_file.stored_path)
        data = decrypt_bytes(encrypted, stored_file.category, tenant=stored_file.client_id)

        headers = {
            "Content-Disposition": f'attachment; {_cd_filename(stored_file.original_filename or stored_file.id)}',
            "Content-Length": str(len(data)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow",
        }
        return StreamingResponse(iter([data]), media_type=stored_file.mime_type, headers=headers)

    # Non chiffré : streaming par chunks (local) ou lecture unique (S3)
    if isinstance(backend, LocalBackend):
        abs_path = settings.upload_path / stored_file.stored_path

        async def file_iterator():
            async with aiofiles.open(abs_path, "rb") as f:
                while chunk := await f.read(65536):
                    yield chunk
        content_stream = file_iterator()
    else:
        async def remote_iterator():
            yield await backend.read(stored_file.stored_path)
        content_stream = remote_iterator()

    headers = {
        "Content-Disposition": f'inline; {_cd_filename(stored_file.original_filename or stored_file.id)}',
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

    return StreamingResponse(content_stream, media_type=stored_file.mime_type, headers=headers)
