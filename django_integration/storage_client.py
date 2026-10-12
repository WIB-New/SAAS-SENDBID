"""
SAAS SENDBID — Django integration client
Replaces Emergent Object Storage SDK.

Usage in Django views:
    from django_integration.storage_client import StorageClient

    client = StorageClient()
    result = client.upload_avatar(file_obj, owner_user_id=str(request.user.id))
    avatar_url = result["url"]
"""
import hashlib
import hmac
import os
import time
from typing import IO, Optional, BinaryIO
from urllib.parse import urljoin

import requests

# Load from Django settings or environment
STORAGE_BASE_URL = os.getenv("STORAGE_BASE_URL", "http://localhost:8080")
STORAGE_API_KEY = os.getenv("STORAGE_API_KEY", "dev-api-key-sendbid-2024")
STORAGE_HMAC_SECRET = os.getenv("STORAGE_HMAC_SECRET", "dev-hmac-secret-sendbid-2024")


class StorageError(Exception):
    """Raised when the storage service returns an error."""
    pass


class StorageClient:
    """
    HTTP client for the SENDBID Storage Service.
    Handles authentication (API key + HMAC) transparently.
    """

    def __init__(
        self,
        base_url: str = STORAGE_BASE_URL,
        api_key: str = STORAGE_API_KEY,
        hmac_secret: str = STORAGE_HMAC_SECRET,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.hmac_secret = hmac_secret
        self.timeout = timeout
        self.session = requests.Session()

    def _make_headers(
        self,
        user_id: str,
        role: str = "user",
        body: bytes = b"",
    ) -> dict:
        """Build auth headers with HMAC signature."""
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{self.api_key}:{timestamp}:{body_hash}"
        signature = hmac.new(
            self.hmac_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "X-User-Id": str(user_id),
            "X-User-Role": role,
        }

    def upload_avatar(
        self,
        file: BinaryIO,
        owner_user_id: str,
        filename: str = "avatar.jpg",
    ) -> dict:
        """Upload a user avatar. Returns {file_id, url, checksum, size, mime}."""
        return self._upload(file, "avatars", owner_user_id, filename)

    def upload_kyc(
        self,
        file: BinaryIO,
        owner_user_id: str,
        filename: str = "kyc.jpg",
    ) -> dict:
        """Upload a KYC document (CNI). Returns {file_id, checksum, size, mime}."""
        return self._upload(file, "kyc", owner_user_id, filename)

    def upload_receipt(
        self,
        file: BinaryIO,
        owner_user_id: str,
        filename: str = "receipt.pdf",
    ) -> dict:
        """Upload a transaction receipt. Returns {file_id, checksum, size, mime}."""
        return self._upload(file, "receipts", owner_user_id, filename)

    def _upload(
        self,
        file: BinaryIO,
        category: str,
        owner_user_id: str,
        filename: str,
    ) -> dict:
        """Internal upload method."""
        content = file.read() if hasattr(file, "read") else file

        # For multipart, body for HMAC is empty (file content is streamed separately)
        headers = self._make_headers(owner_user_id, body=b"")

        resp = self.session.post(
            f"{self.base_url}/v1/files",
            files={"file": (filename, content)},
            data={"category": category, "owner_user_id": owner_user_id},
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    def get_file_url(
        self,
        file_id: str,
        user_id: str,
        role: str = "user",
        ttl: int = 60,
    ) -> str:
        """
        For sensitive files: get a signed URL (valid for `ttl` seconds).
        For public files (avatars): return the CDN URL directly.
        """
        headers = self._make_headers(user_id, role)
        resp = self.session.get(
            f"{self.base_url}/v1/files/{file_id}/signed",
            params={"ttl": ttl},
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()["signed_url"]

    def get_file_meta(self, file_id: str, user_id: str, role: str = "user") -> dict:
        """Get metadata for a file."""
        headers = self._make_headers(user_id, role)
        resp = self.session.get(
            f"{self.base_url}/v1/files/{file_id}/meta",
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    def delete_file(self, file_id: str, user_id: str, role: str = "user") -> bool:
        """Soft-delete a file."""
        headers = self._make_headers(user_id, role)
        resp = self.session.delete(
            f"{self.base_url}/v1/files/{file_id}",
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return True

    def list_files(
        self,
        user_id: str,
        role: str = "user",
        category: Optional[str] = None,
    ) -> list:
        """List files owned by user."""
        headers = self._make_headers(user_id, role)
        params = {}
        if category:
            params["category"] = category
        resp = self.session.get(
            f"{self.base_url}/v1/files",
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: requests.Response):
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise StorageError(
                f"Storage service error {resp.status_code}: {detail}"
            )


# ── Django model mixin (optional usage)
class StorageFileMixin:
    """
    Mixin for Django models that have a file stored in the storage service.
    Add to any Django model that references a storage file.

    Example:
        class UserProfile(StorageFileMixin, models.Model):
            avatar_file_id = models.CharField(max_length=36, blank=True)
    """
    _storage_client = None

    @classmethod
    def get_storage_client(cls) -> StorageClient:
        if cls._storage_client is None:
            cls._storage_client = StorageClient()
        return cls._storage_client

    def get_avatar_url(self, user_id: str) -> Optional[str]:
        """Get the public avatar URL."""
        file_id = getattr(self, "avatar_file_id", None)
        if not file_id:
            return None
        return f"{STORAGE_BASE_URL}/v1/public/avatars/{file_id}"

    def get_kyc_url(self, user_id: str, role: str = "user", ttl: int = 60) -> Optional[str]:
        """Get a signed URL for the KYC document."""
        file_id = getattr(self, "kyc_file_id", None)
        if not file_id:
            return None
        return self.get_storage_client().get_file_url(file_id, user_id, role, ttl)
