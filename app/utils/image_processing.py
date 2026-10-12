"""
SAAS SENDBID — Image processing utilities
- EXIF metadata stripping (GPS, device info, etc.)
- Re-encoding to strip hidden payloads
"""
import io
from typing import Optional

from fastapi import HTTPException
from PIL import Image


def strip_exif_and_reencode(content: bytes, mime_type: str) -> bytes:
    """
    Strip all EXIF metadata from image and re-encode.
    This removes GPS coordinates, device info, timestamps, etc.
    Returns cleaned image bytes.
    """
    if mime_type not in ("image/jpeg", "image/png", "image/webp"):
        # Non-image files (PDFs) — return as-is
        return content

    try:
        img = Image.open(io.BytesIO(content))

        # Convert to RGB if needed (handles RGBA, P mode, etc.)
        if img.mode in ("RGBA", "LA", "P"):
            # Keep alpha for PNG
            if mime_type == "image/png":
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Re-encode without metadata
        output = io.BytesIO()

        if mime_type == "image/jpeg":
            img.save(output, format="JPEG", quality=92, optimize=True)
        elif mime_type == "image/png":
            img.save(output, format="PNG", optimize=True)
        elif mime_type == "image/webp":
            img.save(output, format="WEBP", quality=92)
        else:
            img.save(output, format=img.format or "JPEG")

        cleaned = output.getvalue()
        return cleaned

    except Exception as e:
        # If processing fails, reject — don't silently pass corrupted files
        raise HTTPException(status_code=400, detail=f"Image processing failed: {e}")


def get_image_dimensions(content: bytes) -> Optional[tuple[int, int]]:
    """Return (width, height) or None."""
    try:
        img = Image.open(io.BytesIO(content))
        return img.size
    except Exception:
        return None
