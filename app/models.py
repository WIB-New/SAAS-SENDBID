"""
SAAS SENDBID — SQLAlchemy ORM models
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import func
import enum

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class FileCategory(str, enum.Enum):
    avatars = "avatars"
    kyc = "kyc"
    receipts = "receipts"


class StoredFile(Base):
    __tablename__ = "stored_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=True)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relations
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="file", lazy="select"
    )

    def is_public(self) -> bool:
        return self.category == FileCategory.avatars.value

    def __repr__(self) -> str:
        return f"<StoredFile id={self.id} category={self.category} owner={self.owner_user_id}>"


class AuditLog(Base):
    """Journal d'accès aux fichiers sensibles."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("stored_files.id"), nullable=False, index=True)
    requester_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "download", "delete", "upload"
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped["StoredFile"] = relationship("StoredFile", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog file={self.file_id} action={self.action} by={self.requester_user_id}>"
