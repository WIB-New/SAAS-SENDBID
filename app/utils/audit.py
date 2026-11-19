"""
StorageHub — Audit logging for sensitive file access
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def log_access(
    db: AsyncSession,
    file_id: str,
    requester_user_id: str,
    requester_role: str,
    action: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    details: Optional[str] = None,
) -> models.AuditLog:
    """Persist an audit log entry for sensitive file operations."""
    entry = models.AuditLog(
        file_id=file_id,
        requester_user_id=requester_user_id[:255],
        requester_role=requester_role[:50],
        action=action[:50],
        ip_address=ip_address[:64] if ip_address else None,
        user_agent=user_agent[:512] if user_agent else None,
        timestamp=datetime.utcnow(),
        success=success,
        details=details,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
