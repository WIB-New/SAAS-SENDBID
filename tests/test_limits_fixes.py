"""
StorageHub — Tests des corrections de limites résiduelles
- Gates de plan (bulk Pro+, webhooks Starter+)
- Suppression en cascade des chaînes de versions
- Rétention des logs d'audit
- SSRF : épinglage d'IP / blocage IP privées
- Billing non configuré → 503
- Rate limiter mémoire
"""
import io
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from tests.conftest import TEST_HEADERS, make_minimal_jpeg


async def _register_client(client, email="plan@test.dev"):
    """Crée un vrai compte client (plan free) → (api_key, jwt)."""
    resp = await client.post(
        "/v1/accounts/register",
        json={"email": email, "password": "motdepasse123"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["api_key"], data["access_token"]


@pytest.mark.asyncio
async def test_bulk_requires_pro_plan(client):
    """Le bulk upload doit refuser le plan free."""
    api_key, _ = await _register_client(client)
    jpeg = make_minimal_jpeg()
    resp = await client.post(
        "/v1/files/bulk",
        files=[("files", ("a.jpg", io.BytesIO(jpeg), "image/jpeg"))],
        data={"category": "avatars"},
        headers={"X-API-Key": api_key, "X-User-Id": "u1"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_webhooks_require_starter_plan(client):
    """Créer un webhook en plan free → 403."""
    _, token = await _register_client(client, "wh@test.dev")
    resp = await client.post(
        "/v1/webhooks",
        json={"url": "https://example.com/hook", "events": "*"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_delete_cascades_version_chain(client):
    """Supprimer un fichier supprime toute sa chaîne de versions."""
    jpeg = make_minimal_jpeg()
    v1 = await client.post(
        "/v1/files",
        files={"file": ("doc.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    v1_id = v1.json()["file_id"]
    v2 = await client.post(
        "/v1/files",
        files={"file": ("doc_v2.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "files", "replaces_file_id": v1_id},
        headers=TEST_HEADERS,
    )
    v2_id = v2.json()["file_id"]
    assert v2.json()["version"] == 2

    # Suppression de la racine → les deux versions sont retirées
    resp = await client.delete(f"/v1/files/{v1_id}", headers=TEST_HEADERS)
    assert resp.status_code == 200
    for fid in (v1_id, v2_id):
        meta = await client.get(f"/v1/files/{fid}/meta", headers=TEST_HEADERS)
        assert meta.status_code == 404, f"{fid} devrait être supprimé"


@pytest.mark.asyncio
async def test_audit_retention_purge(client):
    """purge_old_audit_logs supprime les logs au-delà de la rétention."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import AuditLog
    from app.tasks.purge import purge_old_audit_logs

    # Il faut un vrai file_id pour la FK
    up = await client.post(
        "/v1/files",
        files={"file": ("f.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        data={"category": "avatars"},
        headers=TEST_HEADERS,
    )
    fid = up.json()["file_id"]

    async with AsyncSessionLocal() as session:
        session.add(AuditLog(
            file_id=fid, requester_user_id="u", requester_role="user",
            action="download", timestamp=datetime.utcnow() - timedelta(days=4000),
        ))
        session.add(AuditLog(
            file_id=fid, requester_user_id="u", requester_role="user",
            action="download", timestamp=datetime.utcnow(),
        ))
        await session.commit()

    deleted = await purge_old_audit_logs()
    assert deleted == 1

    async with AsyncSessionLocal() as session:
        remaining = (await session.execute(select(AuditLog))).scalars().all()
    # Reste le log "upload" créé par l'API + le log récent inséré manuellement
    assert len(remaining) == 2
    assert all(r.timestamp > datetime.utcnow() - timedelta(days=365) for r in remaining)


@pytest.mark.asyncio
async def test_ssrf_private_ip_pinned_rejected(client):
    """resolve_pinned_url bloque toujours les IPs privées/metadata."""
    from app.utils.url_safety import resolve_pinned_url
    with pytest.raises(HTTPException):
        await resolve_pinned_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(HTTPException):
        await resolve_pinned_url("http://127.0.0.1:8000/admin")


@pytest.mark.asyncio
async def test_ssrf_pinned_url_rewrites_to_ip(client):
    """Une IP publique littérale est épinglée avec Host header conservé."""
    from app.utils.url_safety import resolve_pinned_url
    pinned = await resolve_pinned_url("http://93.184.216.34/docs/spec?q=1")
    assert pinned["url"].startswith("http://93.184.216.34/")
    assert pinned["headers"]["Host"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_billing_unconfigured_returns_503(client):
    """Sans clés Stripe, /v1/billing/checkout → 503 (feature inactive)."""
    _, token = await _register_client(client, "bill@test.dev")
    resp = await client.post(
        "/v1/billing/checkout",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_inmemory_rate_limiter_blocks():
    """Le limiteur mémoire rejette au-delà du quota (async)."""
    from app.ratelimit import _InMemoryRateLimiter
    store = _InMemoryRateLimiter()
    for _ in range(3):
        await store.check("t:key", 3, 60)
    with pytest.raises(HTTPException) as exc:
        await store.check("t:key", 3, 60)
    assert exc.value.status_code == 429
