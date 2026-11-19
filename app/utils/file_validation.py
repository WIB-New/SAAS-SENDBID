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

# Allowed categories — "files" = catégorie générique (tout type non-exécutable)
VALID_CATEGORIES = {"avatars", "kyc", "receipts", "files"}


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

    # Lecture par chunks avec abort précoce : un body géant est rejeté dès que
    # la limite est franchie au lieu d'être entièrement bufferisé en RAM.
    max_bytes = settings.max_sizes_bytes[category]
    chunks = []
    total = 0
    while chunk := await file.read(65536):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File too large: exceeds {max_bytes / 1024 / 1024} MB "
                    f"max for '{category}'"
                ),
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")

    return content, validate_content(content, category)


def validate_content(content: bytes, category: str) -> str:
    """
    Valide des bytes déjà lus (upload multipart, from-url) et retourne
    le MIME détecté. Mêmes règles que la fin de validate_upload :
    exécutables interdits hors 'files', détection par magic bytes,
    whitelist MIME de la catégorie.
    """
    allowed = settings.allowed_mimes.get(category, [])

    # Dangerous executable check — sauf catégorie 'files' où l'antivirus
    # (scan_content) couvre les vrais exécutables ; is_dangerous_file bloque
    # aussi les conteneurs ZIP/DOCX, acceptables dans une catégorie générique.
    if category != "files" and is_dangerous_file(content):
        raise HTTPException(
            status_code=400,
            detail="Executable or script files are not allowed",
        )

    # Real MIME detection via magic bytes — 'files' accepte tout type,
    # y compris sans signature connue (application/octet-stream)
    detected_mime = detect_mime_from_magic(content)
    if detected_mime is None:
        if "*" in allowed:
            detected_mime = "application/octet-stream"
        else:
            raise HTTPException(
                status_code=400,
                detail="Cannot determine file type from content. File may be corrupted or unsupported.",
            )

    # MIME whitelist check
    if "*" not in allowed and detected_mime not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{detected_mime}' not allowed for category '{category}'. "
                f"Allowed: {', '.join(allowed)}"
            ),
        )

    return detected_mime


def safe_filename(category: str) -> str:
    """
    Generate a safe, server-side filename (UUID-based).
    Never use client-supplied filenames.
    """
    import uuid
    from app.utils.time import utcnow

    now = utcnow()
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


def sanitize_folder(path: str) -> str:
    """
    Normalise un chemin de dossier fourni par le client (upload de dossier).
    Conservé comme métadonnée (tags) uniquement — jamais utilisé comme
    chemin disque. Supprime '..', séparateurs redondants, NUL.
    """
    parts = [
        p for p in re.split(r"[/\\]+", path.replace("\x00", ""))
        if p not in ("", ".", "..")
    ]
    return "/".join(parts)[:512]
