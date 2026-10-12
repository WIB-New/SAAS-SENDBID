"""
StorageHub — File validation utilities
- Magic bytes MIME detection
- Path traversal protection
- Executable rejection
- Size limits
"""
import io
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.config import settings

# Magic bytes signatures (offset, bytes, mime)
MAGIC_SIGNATURES = [
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"RIFF", "image/webp"),  # RIFF....WEBP
    (0, b"%PDF", "application/pdf"),
    (0, b"\x25\x50\x44\x46", "application/pdf"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
]

# Dangerous magic bytes — always reject these
DANGEROUS_SIGNATURES = [
    b"MZ",            # PE executable (Windows)
    b"\x7fELF",       # ELF executable (Linux)
    b"#!/",           # Shell scripts
    b"#!",            # Scripts
    b"PK\x03\x04",   # ZIP (could be JAR, DOCX with macro, etc.) — warn
]

# Allowed categories
VALID_CATEGORIES = {"avatars", "kyc", "receipts"}


def detect_mime_from_magic(data: bytes) -> Optional[str]:
    """Detect MIME type from first bytes of file content."""
    for offset, sig, mime in MAGIC_SIGNATURES:
        chunk = data[offset: offset + len(sig)]
        if chunk == sig:
            # Extra check for WebP
            if mime == "image/webp":
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime
    return None


def is_dangerous_file(data: bytes) -> bool:
    """Return True if file looks like an executable or script."""
    for sig in DANGEROUS_SIGNATURES:
        if data[:len(sig)] == sig:
            return True
    return False


def validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}",
        )
    return category


async def validate_upload(
    file: UploadFile,
    category: str,
) -> tuple[bytes, str]:
    """
    Read, validate and return (file_bytes, detected_mime).
    Raises HTTPException on any validation failure.
    """
    validate_category(category)

    # Read file into memory for validation
    content = await file.read()

    # 1. Size check
    max_bytes = settings.max_sizes_bytes[category]
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large: {len(content) / 1024 / 1024:.2f} MB. "
                f"Max for '{category}': {max_bytes / 1024 / 1024} MB"
            ),
        )

    # 2. Dangerous executable check
    if is_dangerous_file(content):
        raise HTTPException(
            status_code=400,
            detail="Executable or script files are not allowed",
        )

    # 3. Real MIME detection via magic bytes
    detected_mime = detect_mime_from_magic(content)
    if detected_mime is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot determine file type from content. File may be corrupted or unsupported.",
        )

    # 4. MIME whitelist check
    allowed = settings.allowed_mimes.get(category, [])
    if detected_mime not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{detected_mime}' not allowed for category '{category}'. "
                f"Allowed: {', '.join(allowed)}"
            ),
        )

    return content, detected_mime


def safe_filename(category: str) -> str:
    """
    Generate a safe, server-side filename (UUID-based).
    Never use client-supplied filenames.
    """
    import uuid
    from datetime import datetime

    now = datetime.utcnow()
    year_month = now.strftime("%Y/%m")
    uid = str(uuid.uuid4()).replace("-", "")
    return f"{year_month}/{uid}"


def prevent_path_traversal(path: str) -> str:
    """Strip any path traversal attempts."""
    # Remove any directory separators
    cleaned = re.sub(r"[/\\]", "_", path)
    # Remove null bytes
    cleaned = cleaned.replace("\x00", "")
    # Remove relative path indicators
    cleaned = re.sub(r"\.\.", "", cleaned)
    return cleaned
