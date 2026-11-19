"""
StorageHub — Storage utilities
- File persistence to disk
- Checksum computation
- Signed URL generation
"""
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from app.config import settings
from app.utils.security import derive_secret


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_stored_path(category: str, file_id: str) -> str:
    """
    Build a relative path like: avatars/2024/10/abcdef...
    Avoids huge flat directories.
    """
    now = datetime.utcnow()
    year_month = now.strftime("%Y/%m")
    return f"{category}/{year_month}/{file_id}"


async def save_file_to_disk(
    content: bytes,
    category: str,
    file_id: str,
) -> tuple[Path, str]:
    """
    Persist file bytes via le backend configuré (local ou S3/R2/MinIO).
    Returns (path_ou_clé, checksum_sha256).
    """
    from app.utils.backends import get_storage_backend
    relative_path = build_stored_path(category, file_id)
    return await get_storage_backend().save(content, relative_path)


def delete_file_from_disk(stored_path: str) -> bool:
    """Delete a file via le backend configuré. Returns True if deleted."""
    from app.utils.backends import get_storage_backend
    return get_storage_backend().delete(stored_path)


def generate_signed_url(file_id: str, ttl_seconds: Optional[int] = None) -> tuple[str, datetime]:
    """
    Generate an HMAC-signed URL for temporary access to a sensitive file.
    Returns (signed_url, expires_at).
    """
    ttl = ttl_seconds or settings.signed_url_ttl
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    expires_ts = int(expires_at.timestamp())

    # Sign: HMAC(secret dérivé, file_id + ":" + expires_ts)
    message = f"{file_id}:{expires_ts}"
    sig = hmac.new(
        derive_secret("signed-url").encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()  # type: ignore[attr-defined]

    params = urlencode({"expires": expires_ts, "sig": sig})
    url = f"{settings.base_url}/v1/files/{file_id}/download?{params}"
    return url, expires_at


def verify_signed_url(file_id: str, expires: str, sig: str) -> bool:
    """Verify a signed URL signature and check it hasn't expired."""
    try:
        expires_ts = int(expires)
    except (ValueError, TypeError):
        return False

    # Check expiry
    if time.time() > expires_ts:
        return False

    # Recompute signature
    message = f"{file_id}:{expires_ts}"
    expected_sig = hmac.new(
        derive_secret("signed-url").encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, sig)


def get_disk_usage_by_category() -> dict:
    """Return disk usage stats per category."""
    import shutil
    result = {}
    upload_root = settings.upload_path

    for category in ["avatars", "kyc", "receipts", "files"]:
        cat_path = upload_root / category
        if cat_path.exists():
            total_size = sum(
                f.stat().st_size
                for f in cat_path.rglob("*")
                if f.is_file()
            )
            count = sum(1 for f in cat_path.rglob("*") if f.is_file())
            result[category] = {
                "size_bytes": total_size,
                "size_mb": round(total_size / 1024 / 1024, 2),
                "file_count": count,
            }
        else:
            result[category] = {"size_bytes": 0, "size_mb": 0.0, "file_count": 0}

    # Overall disk usage for the partition
    try:
        disk = shutil.disk_usage(str(upload_root))
        result["_disk"] = {
            "total_gb": round(disk.total / 1024**3, 2),
            "used_gb": round(disk.used / 1024**3, 2),
            "free_gb": round(disk.free / 1024**3, 2),
            "percent": round(disk.used / disk.total * 100, 1),
            "alert": (disk.used / disk.total * 100) >= settings.disk_alert_threshold_percent,
        }
    except Exception as e:
        result["_disk"] = {"error": str(e)}

    return result
