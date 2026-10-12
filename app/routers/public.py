"""
StorageHub — Public files router (avatars only, no auth required)
GET /v1/public/avatars/{file_id}

NOTE: In production this is served by Nginx directly from disk.
This route exists for development/testing only.
IMPORTANT: Nginx MUST NOT serve /kyc/ or /receipts/ paths publicly.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import aiofiles

from app.config import settings

router = APIRouter(tags=["public"])


@router.get("/v1/public/avatars/{file_id}")
async def serve_public_avatar(file_id: str):
    """Serve a public avatar file (no authentication required)."""
    # Only allow avatars — strict enforcement
    # Search for the file in the avatars directory
    avatars_root = settings.upload_path / "avatars"

    if not avatars_root.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Find file by ID (could be in year/month subdirectory)
    found_path = None
    for f in avatars_root.rglob(file_id):
        if f.is_file():
            found_path = f
            break

    if not found_path:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Security check: ensure path is inside avatars directory only
    try:
        found_path.resolve().relative_to(avatars_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    async def file_iterator():
        async with aiofiles.open(found_path, "rb") as f:
            while chunk := await f.read(65536):
                yield chunk

    # Guess MIME from extension-less file
    size = found_path.stat().st_size

    return StreamingResponse(
        file_iterator(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(size),
            "X-Content-Type-Options": "nosniff",
        },
    )
