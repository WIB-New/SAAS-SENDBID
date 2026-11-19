"""
StorageHub — Public files router (avatars only, no auth required)
GET /v1/public/avatars/{file_id}

NOTE: In production this is served by Nginx directly from disk.
This route exists for development/testing only.
IMPORTANT: Nginx MUST NOT serve /kyc/ or /receipts/ paths publicly.
"""
import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.database import get_db
from app.ratelimit import global_limit

router = APIRouter(tags=["public"])


@router.get("/v1/public/avatars/{file_id}", dependencies=[Depends(global_limit)])
async def serve_public_avatar(file_id: str, db: AsyncSession = Depends(get_db)):
    """
    Serve a public avatar file (no authentication required).
    Lookup direct en base : seuls les fichiers enregistrés en catégorie
    'avatars' et non supprimés sont servis — avec leur vrai type MIME.
    """
    result = await db.execute(
        select(models.StoredFile).where(
            models.StoredFile.id == file_id,
            models.StoredFile.category == "avatars",
            models.StoredFile.is_deleted == False,
        )
    )
    stored_file = result.scalar_one_or_none()
    if not stored_file:
        raise HTTPException(status_code=404, detail="Avatar not found")

    from app.utils.backends import get_storage_backend, LocalBackend
    backend = get_storage_backend()

    if isinstance(backend, LocalBackend):
        abs_path = settings.upload_path / stored_file.stored_path
        # Sécurité : le chemin doit rester strictement dans le dossier avatars
        avatars_root = settings.upload_path / "avatars"
        try:
            abs_path.resolve().relative_to(avatars_root.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

        if not abs_path.exists():
            raise HTTPException(status_code=404, detail="Avatar not found on disk")

        async def file_iterator():
            async with aiofiles.open(abs_path, "rb") as f:
                while chunk := await f.read(65536):
                    yield chunk
    else:
        if not await backend.exists(stored_file.stored_path):
            raise HTTPException(status_code=404, detail="Avatar not found in storage")

        async def file_iterator():
            yield await backend.read(stored_file.stored_path)

    return StreamingResponse(
        file_iterator(),
        media_type=stored_file.mime_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(stored_file.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )
