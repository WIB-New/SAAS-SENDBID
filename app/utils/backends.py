"""
StorageHub — Backend de stockage pluggable
Abstraction permettant de basculer entre disque local, S3, Cloudflare R2 ou MinIO
sans modifier le code métier.

Configuration via STORAGE_BACKEND dans .env :
  STORAGE_BACKEND=local          (par défaut)
  STORAGE_BACKEND=s3             (AWS S3 / Cloudflare R2 / MinIO)

Variables S3 :
  S3_BUCKET, S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY,
  S3_REGION, S3_PUBLIC_BASE_URL
"""
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union


class StorageBackend(ABC):
    """Interface commune à tous les backends."""

    @abstractmethod
    async def save(self, content: bytes, relative_path: str) -> tuple[Union[Path, str], str]:
        """Sauvegarde le contenu. Retourne (path_ou_key, sha256)."""
        ...

    @abstractmethod
    async def read(self, relative_path: str) -> bytes:
        """Lit le contenu depuis le stockage."""
        ...

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """Supprime le fichier. Retourne True si supprimé."""
        ...

    @abstractmethod
    def get_public_url(self, relative_path: str) -> Optional[str]:
        """Retourne une URL publique CDN ou None."""
        ...


class LocalBackend(StorageBackend):
    """Stockage disque local — comportement par défaut."""

    def __init__(self, upload_root: Path):
        self.upload_root = upload_root

    async def save(self, content: bytes, relative_path: str) -> tuple[Path, str]:
        import aiofiles
        abs_path = self.upload_root / relative_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(abs_path, "wb") as f:
            await f.write(content)
        checksum = hashlib.sha256(content).hexdigest()
        return abs_path, checksum

    async def read(self, relative_path: str) -> bytes:
        import aiofiles
        abs_path = self.upload_root / relative_path
        async with aiofiles.open(abs_path, "rb") as f:
            return await f.read()

    def delete(self, relative_path: str) -> bool:
        abs_path = self.upload_root / relative_path
        try:
            abs_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def get_public_url(self, relative_path: str) -> Optional[str]:
        return None  # URLs servies via l'API, pas directement


class S3Backend(StorageBackend):
    """Backend Amazon S3 / Cloudflare R2 / MinIO."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        region: str = "us-east-1",
        public_base_url: Optional[str] = None,
    ):
        import boto3
        self.bucket = bucket
        self.public_base_url = public_base_url
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region,
        )

    async def save(self, content: bytes, relative_path: str) -> tuple[str, str]:
        import asyncio
        checksum = hashlib.sha256(content).hexdigest()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.put_object(
                Bucket=self.bucket,
                Key=relative_path,
                Body=content,
            ),
        )
        return relative_path, checksum

    async def read(self, relative_path: str) -> bytes:
        import asyncio
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.get_object(Bucket=self.bucket, Key=relative_path),
        )
        return resp["Body"].read()

    def delete(self, relative_path: str) -> bool:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception:
            return False

    def get_public_url(self, relative_path: str) -> Optional[str]:
        if self.public_base_url:
            return f"{self.public_base_url}/{relative_path}"
        return None


# ── Singleton ──────────────────────────────────
_backend: Optional[StorageBackend] = None


def get_storage_backend() -> StorageBackend:
    """Retourne le backend configuré (singleton)."""
    global _backend
    if _backend is not None:
        return _backend

    from app.config import settings
    btype = getattr(settings, "storage_backend", "local")

    if btype == "s3":
        _backend = S3Backend(
            bucket=getattr(settings, "s3_bucket", "storagehub"),
            endpoint_url=getattr(settings, "s3_endpoint_url", None),
            aws_access_key=getattr(settings, "s3_access_key", None),
            aws_secret_key=getattr(settings, "s3_secret_key", None),
            region=getattr(settings, "s3_region", "us-east-1"),
            public_base_url=getattr(settings, "s3_public_base_url", None),
        )
    else:
        _backend = LocalBackend(settings.upload_path)

    return _backend
