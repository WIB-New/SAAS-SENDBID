"""
StorageHub — Génération de miniatures (thumbnails)
Génère une miniature JPEG 256x256 au moment de l'upload pour les fichiers image.
Stockées dans uploads/thumbnails/{file_id}.jpg
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image

THUMB_SIZE = (256, 256)
THUMB_QUALITY = 82
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def generate_thumbnail(content: bytes, mime_type: str) -> Optional[bytes]:
    """
    Génère un thumbnail JPEG 256x256 depuis les bytes d'une image.
    Retourne None si le fichier n'est pas une image ou en cas d'erreur.
    """
    if mime_type not in IMAGE_MIMES:
        return None
    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=THUMB_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


async def save_thumbnail(thumb_bytes: bytes, file_id: str) -> Optional[str]:
    """
    Sauvegarde le thumbnail sur le disque.
    Retourne le chemin relatif (ex: 'thumbnails/abc123.jpg') ou None en cas d'erreur.
    """
    import aiofiles
    from app.config import settings

    thumb_dir: Path = settings.upload_path / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    relative = f"thumbnails/{file_id}.jpg"
    abs_path = settings.upload_path / relative
    try:
        async with aiofiles.open(abs_path, "wb") as f:
            await f.write(thumb_bytes)
        return relative
    except Exception:
        return None


def get_thumbnail_url(file_id: str, base_url: str) -> str:
    """Construit l'URL publique de la miniature."""
    return f"{base_url}/v1/files/{file_id}/thumbnail"
