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


class Client(Base):
    """Compte client SaaS — chaque client possède ses propres credentials API."""
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="client", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Client {self.email} plan={self.plan}>"


class ApiKey(Base):
    """Credential API d'un client — paire api_key + hmac_secret."""
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Default key")
    api_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    hmac_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="free")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey {self.api_key[:12]}… client={self.client_id}>"


class StoredFile(Base):
    __tablename__ = "stored_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    client_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=True, index=True
    )
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
