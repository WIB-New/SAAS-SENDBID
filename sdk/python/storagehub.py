"""
StorageHub Python SDK
Permet d'intégrer le service de stockage en quelques lignes.

Usage :
    from storagehub import StorageHub

    hub = StorageHub(api_key="sk-...", base_url="https://storage.sendbid.com")

    # Upload d'une image
    result = hub.upload("photo.jpg", category="avatars")
    print(result["url"])

    # Upload depuis bytes
    with open("id.pdf", "rb") as f:
        result = hub.upload_bytes(f.read(), "id.pdf", category="kyc")

    # Lister ses fichiers
    files = hub.list_files(category="avatars", page=1, limit=20)

    # URL signée temporaire (60 secondes)
    signed = hub.get_signed_url(result["file_id"], ttl=60)

    # Supprimer
    hub.delete(result["file_id"])
"""
import mimetypes
import os
from pathlib import Path
from typing import Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import urllib.request, urllib.error, json as _json
    _HAS_HTTPX = False


class StorageHubError(Exception):
    """Erreur retournée par l'API StorageHub."""
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code}] {code}: {message}")


class StorageHub:
    """Client officiel pour l'API StorageHub."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8080",
        user_id: str = "sdk-user",
        role: str = "user",
        timeout: float = 30.0,
    ):
        self.api_key  = api_key
        self.base_url = base_url.rstrip("/")
        self.user_id  = user_id
        self.role     = role
        self.timeout  = timeout

    @property
    def _headers(self) -> dict:
        return {
            "X-API-Key":   self.api_key,
            "X-User-Id":   self.user_id,
            "X-User-Role": self.role,
        }

    def _raise_if_error(self, status_code: int, data: dict):
        if not data.get("success", True) or status_code >= 400:
            raise StorageHubError(
                status_code=status_code,
                code=data.get("code", "UNKNOWN"),
                message=data.get("error", "Unknown error"),
            )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        if _HAS_HTTPX:
            with httpx.Client(timeout=self.timeout) as client:
                resp = getattr(client, method)(url, headers=self._headers, **kwargs)
                data = resp.json()
                self._raise_if_error(resp.status_code, data)
                return data
        else:
            raise RuntimeError("httpx is required. Install with: pip install httpx")

    # ── Upload ─────────────────────────────────────────────────────────────────
    def upload(
        self,
        file_path: str,
        category: str,
        tags: Optional[dict] = None,
        replaces_file_id: Optional[str] = None,
    ) -> dict:
        """Upload un fichier depuis le système de fichiers local."""
        path = Path(file_path)
        with open(path, "rb") as f:
            content = f.read()
        return self.upload_bytes(content, path.name, category, tags, replaces_file_id)

    def upload_bytes(
        self,
        content: bytes,
        filename: str,
        category: str,
        tags: Optional[dict] = None,
        replaces_file_id: Optional[str] = None,
    ) -> dict:
        """Upload des bytes avec un nom de fichier."""
        import io, json as _json
        mime, _ = mimetypes.guess_type(filename)
        mime = mime or "application/octet-stream"

        data = {"category": category}
        if tags:
            data["tags"] = _json.dumps(tags)
        if replaces_file_id:
            data["replaces_file_id"] = replaces_file_id

        return self._request(
            "post", "/v1/files",
            files={"file": (filename, io.BytesIO(content), mime)},
            data=data,
        )

    def upload_from_url(self, url: str, category: str, tags: Optional[dict] = None) -> dict:
        """Importe un fichier depuis une URL distante."""
        payload: dict = {"url": url, "category": category}
        if tags:
            payload["tags"] = tags
        return self._request("post", "/v1/files/from-url", json=payload)

    def upload_bulk(self, file_paths: list[str], category: str) -> dict:
        """Upload plusieurs fichiers en une seule requête."""
        import io
        files = []
        for fp in file_paths:
            p = Path(fp)
            mime, _ = mimetypes.guess_type(fp)
            mime = mime or "application/octet-stream"
            files.append(("files", (p.name, open(p, "rb"), mime)))
        try:
            return self._request("post", "/v1/files/bulk", files=files, data={"category": category})
        finally:
            for _, (_, fobj, _) in files:
                fobj.close()

    # ── Lecture ────────────────────────────────────────────────────────────────
    def list_files(
        self,
        category: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at:desc",
    ) -> dict:
        """Liste les fichiers avec pagination."""
        params: dict = {"page": page, "limit": limit, "sort": sort}
        if category:
            params["category"] = category
        return self._request("get", "/v1/files", params=params)

    def get_meta(self, file_id: str) -> dict:
        """Métadonnées d'un fichier."""
        return self._request("get", f"/v1/files/{file_id}/meta")

    def get_versions(self, file_id: str) -> list:
        """Historique des versions d'un fichier."""
        return self._request("get", f"/v1/files/{file_id}/versions")

    def get_signed_url(self, file_id: str, ttl: Optional[int] = None) -> dict:
        """Génère une URL signée temporaire."""
        params = {}
        if ttl:
            params["ttl"] = ttl
        return self._request("get", f"/v1/files/{file_id}/signed", params=params)

    def download(self, file_id: str) -> bytes:
        """Télécharge le contenu d'un fichier."""
        url = f"{self.base_url}/v1/files/{file_id}"
        if _HAS_HTTPX:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers)
                resp.raise_for_status()
                return resp.content
        raise RuntimeError("httpx is required")

    # ── Modification ──────────────────────────────────────────────────────────
    def update_tags(self, file_id: str, tags: dict) -> dict:
        """Met à jour les tags d'un fichier."""
        return self._request("patch", f"/v1/files/{file_id}/tags", json={"tags": tags})

    def replace(self, file_id: str, file_path: str) -> dict:
        """Remplace un fichier par une nouvelle version."""
        import io
        p = Path(file_path)
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"
        with open(p, "rb") as f:
            content = f.read()
        return self._request(
            "post", f"/v1/files/{file_id}/replace",
            files={"file": (p.name, io.BytesIO(content), mime)},
        )

    def delete(self, file_id: str) -> dict:
        """Supprime (soft delete) un fichier."""
        return self._request("delete", f"/v1/files/{file_id}")

    # ── Webhooks ──────────────────────────────────────────────────────────────
    def create_webhook(self, url: str, events: str = "*", secret: Optional[str] = None) -> dict:
        """Enregistre un endpoint webhook."""
        payload: dict = {"url": url, "events": events}
        if secret:
            payload["secret"] = secret
        return self._request("post", "/v1/webhooks", json=payload)

    def list_webhooks(self) -> list:
        """Liste les webhooks enregistrés."""
        return self._request("get", "/v1/webhooks")

    def delete_webhook(self, webhook_id: str) -> dict:
        """Supprime un webhook."""
        return self._request("delete", f"/v1/webhooks/{webhook_id}")

    # ── Compte ────────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Statistiques d'usage du compte."""
        return self._request("get", "/v1/accounts/stats")

    def health(self) -> dict:
        """État de santé du service."""
        return self._request("get", "/health")

    def ping(self) -> bool:
        """Vérifie que le service répond."""
        result = self._request("get", "/v1/ping")
        return result.get("pong", False)
