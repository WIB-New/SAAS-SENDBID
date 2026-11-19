"""
StorageHub — Tests de l'audit sécurité/robustesse/performance
- Chaîne de versions profonde (v3+) : listing = dernière version,
  versions = chaîne complète, delete = cascade totale, replace → 409 sur non-feuille
- Checksum exposé = SHA-256 du plaintext (même pour les fichiers chiffrés)
- Clés API hachées au repos (sha256$) + authentification toujours fonctionnelle
- Injection de header via original_filename → Content-Disposition assaini
- Paramètre sort arbitraire → pas de 500
- Webhook vers IP privée → 400 (anti-SSRF)
- owner_user_id honoré
- Rate limit login/register
"""
import hashlib
import io

import pytest
from sqlalchemy import select

from tests.conftest import TEST_HEADERS, make_minimal_jpeg
from app import models
from app.database import AsyncSessionLocal


async def _register_client(client, email="h@test.dev"):
    resp = await client.post(
        "/v1/accounts/register",
        json={"email": email, "password": "motdepasse123"},
    )
    assert resp.status_code == 201, resp.text
    d = resp.json()
    return d["api_key"], d["access_token"]


async def _upload(client, filename="a.jpg", category="avatars", headers=None, **form):
    jpeg = make_minimal_jpeg()
    return await client.post(
        "/v1/files",
        files={"file": (filename, io.BytesIO(jpeg), "image/jpeg")},
        data={"category": category, **form},
        headers=headers or TEST_HEADERS,
    )


# ── Chaîne de versions ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_shows_latest_version_not_root(client):
    """Après replace x2, GET /v1/files doit montrer v3 (pas v1)."""
    r1 = await _upload(client, "v1.jpg")
    f1 = r1.json()["file_id"]
    r2 = await client.post(
        f"/v1/files/{f1}/replace",
        files={"file": ("v2.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )
    assert r2.status_code == 201, r2.text
    f2 = r2.json()["file_id"]
    r3 = await client.post(
        f"/v1/files/{f2}/replace",
        files={"file": ("v3.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )
    assert r3.status_code == 201, r3.text

    lst = (await client.get("/v1/files", headers=TEST_HEADERS)).json()
    assert lst["total"] == 1
    item = lst["items"][0]
    assert item["version"] == 3
    assert item["original_filename"] == "v3.jpg"


@pytest.mark.asyncio
async def test_versions_list_includes_deep_chain(client):
    """GET /versions doit retourner v1+v2+v3 (parent immédiat ≠ racine)."""
    f1 = (await _upload(client)).json()["file_id"]
    f2 = (await client.post(
        f"/v1/files/{f1}/replace",
        files={"file": ("v2.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )).json()["file_id"]
    f3 = (await client.post(
        f"/v1/files/{f2}/replace",
        files={"file": ("v3.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )).json()["file_id"]

    versions = (await client.get(
        f"/v1/files/{f3}/versions", headers=TEST_HEADERS)).json()
    assert sorted(v["version"] for v in versions) == [1, 2, 3]


@pytest.mark.asyncio
async def test_replace_non_leaf_rejected(client):
    """Remplacer une ancienne version (non-feuille) → 409."""
    f1 = (await _upload(client)).json()["file_id"]
    f2 = (await client.post(
        f"/v1/files/{f1}/replace",
        files={"file": ("v2.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )).json()["file_id"]

    # v1 n'est plus la feuille → 409
    r = await client.post(
        f"/v1/files/{f1}/replace",
        files={"file": ("x.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_delete_cascades_deep_chain(client):
    """Delete sur v3 soft-delete aussi v1 et v2."""
    f1 = (await _upload(client)).json()["file_id"]
    f2 = (await client.post(
        f"/v1/files/{f1}/replace",
        files={"file": ("v2.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )).json()["file_id"]
    f3 = (await client.post(
        f"/v1/files/{f2}/replace",
        files={"file": ("v3.jpg", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        headers=TEST_HEADERS,
    )).json()["file_id"]

    d = await client.delete(f"/v1/files/{f3}", headers=TEST_HEADERS)
    assert d.status_code == 200

    for fid in (f1, f2, f3):
        r = await client.get(f"/v1/files/{fid}/meta", headers=TEST_HEADERS)
        assert r.status_code == 404, f"{fid} devrait être supprimé"


# ── Checksum plaintext pour fichiers chiffrés ────────────────────────────────
@pytest.mark.asyncio
async def test_checksum_is_plaintext_sha256(client):
    """Le checksum exposé = SHA-256 du contenu original, pas du ciphertext."""
    jpeg = make_minimal_jpeg()
    r = await client.post(
        "/v1/files",
        files={"file": ("doc.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "kyc"},   # chiffré au repos
        headers=TEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    fid = r.json()["file_id"]

    # Le strip EXIF ré-encode le JPEG → le checksum est calculé sur le
    # contenu stocké (plaintext, après nettoyage), pas sur le ciphertext.

    # Télécharger puis re-hacher le contenu reçu (déchiffré)
    body = (await client.get(f"/v1/files/{fid}", headers=TEST_HEADERS)).content
    meta = (await client.get(f"/v1/files/{fid}/meta", headers=TEST_HEADERS)).json()
    assert meta["checksum_sha256"] == hashlib.sha256(body).hexdigest()
    assert meta["checksum_sha256"] == r.json()["checksum"]


# ── Clés API hachées au repos ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_key_stored_hashed(client):
    """La colonne api_keys.api_key ne contient pas la clé en clair."""
    api_key, _ = await _register_client(client, "hash@test.dev")

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(models.ApiKey))).scalars().all()
    assert rows, "aucune clé créée"
    for row in rows:
        assert row.api_key.startswith("sha256$")
        assert api_key not in row.api_key
        assert row.key_hint.startswith("shk_")
        assert "…" in row.key_hint

    # Et l'authentification avec la clé en clair fonctionne toujours
    r = await client.get("/v1/files", headers={
        "X-API-Key": api_key, "X-User-Id": "u1",
    })
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_key_hint_masked_in_me(client):
    """GET /accounts/me masque la clé (pas de hash complet exposé)."""
    _, token = await _register_client(client, "mask@test.dev")
    me = (await client.get(
        "/v1/accounts/me", headers={"Authorization": f"Bearer {token}"})).json()
    for k in me["api_keys"]:
        assert "…" in k["api_key"] or k["api_key"] == "••••••••"
        assert k["hmac_secret"] == "••••••••"


# ── Injection de header via filename ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_filename_header_injection_sanitized(client):
    """Un filename contenant \" et CRLF ne casse pas Content-Disposition."""
    evil = 'x"\r\nSet-Cookie: pwned=yes.jpg'
    r = await client.post(
        "/v1/files",
        files={"file": (evil, io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        data={"category": "kyc"},
        headers=TEST_HEADERS,
    )
    assert r.status_code == 201, r.text
    fid = r.json()["file_id"]

    resp = await client.get(f"/v1/files/{fid}", headers=TEST_HEADERS)
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "\r" not in cd and "\n" not in cd
    assert "pwned" not in resp.headers.get("set-cookie", "")


# ── Paramètre sort arbitraire ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sort_arbitrary_field_no_500(client):
    """sort=audit_logs / __tablename__ ne doit pas crasher en 500."""
    await _upload(client)
    for bad in ("audit_logs:asc", "__tablename__:desc", "nope", "1;DROP TABLE x"):
        r = await client.get(f"/v1/files?sort={bad}", headers=TEST_HEADERS)
        assert r.status_code == 200, f"sort={bad} → {r.status_code}"


# ── Webhook SSRF ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_private_ip_rejected(client):
    """Enregistrer un webhook vers 127.0.0.1 / metadata → 400."""
    _, token = await _register_client(client, "whssrf@test.dev")
    # Upgrade en starter pour passer le gate de plan
    async with AsyncSessionLocal() as s:
        c = (await s.execute(select(models.Client))).scalars().all()[-1]
        c.plan = "starter"
        await s.commit()

    for bad in ("http://127.0.0.1/hook", "http://169.254.169.254/meta",
                "ftp://example.com/x", "notaurl"):
        r = await client.post(
            "/v1/webhooks",
            json={"url": bad, "events": "*"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400, f"{bad} → {r.status_code}: {r.text}"


# ── owner_user_id honoré ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_owner_user_id_override(client):
    """Le champ owner_user_id du formulaire définit le propriétaire."""
    r = await _upload(client, owner_user_id="end-user-42")
    assert r.status_code == 201, r.text
    # Le fichier appartient à end-user-42 — le lire avec cette identité
    meta = (await client.get(
        f"/v1/files/{r.json()['file_id']}/meta",
        headers={**TEST_HEADERS, "X-User-Id": "end-user-42"},
    )).json()
    assert meta["owner_user_id"] == "end-user-42"


# ── Caps ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tags_size_capped(client):
    """tags > 4 Ko sérialisés → 400."""
    big = {"k": "x" * 5000}
    import json as _json
    r = await _upload(client, tags=_json.dumps(big))
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_login_rate_limited(client):
    """11 tentatives de login dans la minute → 429."""
    last = None
    for i in range(11):
        last = await client.post(
            "/v1/accounts/login",
            json={"email": "nobody@x.dev", "password": "badpassword1"},
        )
    assert last.status_code == 429, last.text


# ── Rétrogradation resynchronise les clés ────────────────────────────────────
@pytest.mark.asyncio
async def test_downgrade_resyncs_key_plan(client):
    """Passer en free resynchronise le snapshot plan des clés actives."""
    api_key, token = await _register_client(client, "downgrade@test.dev")
    async with AsyncSessionLocal() as s:
        c = (await s.execute(select(models.Client))).scalars().all()[-1]
        c.plan = "pro"
        await s.commit()
        k = (await s.execute(
            select(models.ApiKey).where(models.ApiKey.client_id == c.id))).scalar()
        k.plan = "pro"
        await s.commit()

    r = await client.post("/v1/accounts/plan", json={"plan": "free"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    async with AsyncSessionLocal() as s:
        k = (await s.execute(
            select(models.ApiKey).where(models.ApiKey.client_id == c.id))).scalar()
        assert k.plan == "free"
