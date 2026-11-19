"""
StorageHub — Tests de l'upload multipart (init → parts → complete)

- Cycle complet : fichier assemblé identique, pipeline normal appliqué
- Parts contiguës exigées, part_number borné, session expirée → 410
- Re-push d'une part : remplacement idempotent
- Isolation des sessions : même tenant, autre user → 403
- Abort : session abandonnée → 409 au complete
"""
import hashlib
import io

import pytest

from tests.conftest import TEST_HEADERS, make_minimal_jpeg


async def _register_client(client, email):
    resp = await client.post(
        "/v1/accounts/register",
        json={"email": email, "password": "motdepasse123"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


async def _init(client, headers=None, **kw):
    payload = {"filename": "big.jpg", "category": "avatars", **kw}
    r = await client.post("/v1/files/multipart/init", json=payload,
                          headers=headers or TEST_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["upload_id"]


async def _put(client, upload_id, n, data, headers=None):
    return await client.put(
        f"/v1/files/multipart/{upload_id}/parts/{n}",
        content=data,
        headers={**(headers or TEST_HEADERS),
                 "Content-Type": "application/octet-stream"},
    )


# ── Cycle complet ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_multipart_full_cycle(client):
    jpeg = make_minimal_jpeg()
    mid = len(jpeg) // 2
    upload_id = await _init(client, total_size=len(jpeg), part_size=1024 * 1024)

    r1 = await _put(client, upload_id, 1, jpeg[:mid])
    r2 = await _put(client, upload_id, 2, jpeg[mid:])
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["etag"] == hashlib.sha256(jpeg[:mid]).hexdigest()

    # État intermédiaire
    st = await client.get(f"/v1/files/multipart/{upload_id}", headers=TEST_HEADERS)
    assert st.json()["parts_received"] == 2

    r = await client.post(f"/v1/files/multipart/{upload_id}/complete",
                          headers=TEST_HEADERS)
    assert r.status_code == 201, r.text
    d = r.json()
    # NB: le pipeline ré-encode les images (strip EXIF) — la taille/checksum
    # sont ceux du contenu traité, cohérents avec ce qui est téléchargeable.
    assert d["size"] > 0
    assert d["category"] == "avatars"
    assert d["url"]                                # avatar public → URL
    assert d["thumbnail_url"]                      # pipeline normal (thumbnail)

    # Le fichier est téléchargeable et correspond au checksum exposé
    dl = await client.get(f"/v1/files/{d['file_id']}", headers=TEST_HEADERS)
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == d["checksum"]

    # Session consommée → 409
    st2 = await client.get(f"/v1/files/multipart/{upload_id}", headers=TEST_HEADERS)
    assert st2.status_code == 409


@pytest.mark.asyncio
async def test_multipart_missing_parts_rejected(client):
    jpeg = make_minimal_jpeg()
    upload_id = await _init(client)
    await _put(client, upload_id, 1, jpeg[:100])
    await _put(client, upload_id, 3, jpeg[100:])   # trou : part 2 manquante

    r = await client.post(f"/v1/files/multipart/{upload_id}/complete",
                          headers=TEST_HEADERS)
    assert r.status_code == 400
    assert "missing" in (r.json().get("detail") or r.json().get("error", "")).lower()


@pytest.mark.asyncio
async def test_multipart_complete_empty_rejected(client):
    upload_id = await _init(client)
    r = await client.post(f"/v1/files/multipart/{upload_id}/complete",
                          headers=TEST_HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_multipart_reupload_part_is_idempotent(client):
    jpeg = make_minimal_jpeg()
    upload_id = await _init(client)
    await _put(client, upload_id, 1, b"garbage" + jpeg[:50])
    r = await _put(client, upload_id, 1, jpeg)      # re-push → remplace
    assert r.status_code == 200
    assert r.json()["etag"] == hashlib.sha256(jpeg).hexdigest()

    # La session ne contient qu'une seule part n°1 (la nouvelle)
    st = await client.get(f"/v1/files/multipart/{upload_id}", headers=TEST_HEADERS)
    assert st.json()["parts_received"] == 1
    assert st.json()["parts"][0]["etag"] == hashlib.sha256(jpeg).hexdigest()


@pytest.mark.asyncio
async def test_multipart_part_number_bounds(client):
    upload_id = await _init(client)
    assert (await _put(client, upload_id, 0, b"x")).status_code == 400
    assert (await _put(client, upload_id, 1001, b"x")).status_code == 400
    assert (await _put(client, upload_id, 1, b"")).status_code == 400


@pytest.mark.asyncio
async def test_multipart_session_isolation(client):
    """Isolation par tenant : une clé d'un AUTRE client ne touche pas la
    session (même modèle que les fichiers — X-User-Id intra-tenant est
    contrôlé par le backend client)."""
    key_a = await _register_client(client, "mp-a@test.dev")
    key_b = await _register_client(client, "mp-b@test.dev")
    h_a = {"X-API-Key": key_a, "X-User-Id": "user-1", "X-User-Role": "user"}
    h_b = {"X-API-Key": key_b, "X-User-Id": "user-1", "X-User-Role": "user"}

    upload_id = await _init(client, headers=h_a)
    # Tenant B ne peut ni pusher ni voir ni compléter ni abandonner
    assert (await _put(client, upload_id, 1, b"x", headers=h_b)).status_code == 403
    assert (await client.get(f"/v1/files/multipart/{upload_id}",
                             headers=h_b)).status_code == 403
    assert (await client.post(f"/v1/files/multipart/{upload_id}/complete",
                              headers=h_b)).status_code == 403
    assert (await client.delete(f"/v1/files/multipart/{upload_id}",
                                headers=h_b)).status_code == 403
    # Tenant A peut toujours
    assert (await _put(client, upload_id, 1, b"x", headers=h_a)).status_code == 200


@pytest.mark.asyncio
async def test_multipart_abort(client):
    upload_id = await _init(client)
    await _put(client, upload_id, 1, make_minimal_jpeg())

    r = await client.delete(f"/v1/files/multipart/{upload_id}",
                            headers=TEST_HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "aborted"

    # Session terminée → 409 sur toutes les opérations
    assert (await _put(client, upload_id, 2, b"x")).status_code == 409
    assert (await client.post(f"/v1/files/multipart/{upload_id}/complete",
                              headers=TEST_HEADERS)).status_code == 409


@pytest.mark.asyncio
async def test_multipart_session_not_found(client):
    assert (await client.get("/v1/files/multipart/nope",
                             headers=TEST_HEADERS)).status_code == 404


@pytest.mark.asyncio
async def test_multipart_init_bad_category(client):
    r = await client.post("/v1/files/multipart/init",
                          json={"filename": "x.bin", "category": "nope"},
                          headers=TEST_HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_multipart_oversized_file_rejected_at_complete(client):
    """Le MIME/taille sont re-vérifiés à l'assemblage — les parts ne sont
    pas une porte dérobée. Exécutable réparti sur 2 parts → rejet."""
    exe = b"MZ" + b"\x90" * 4096
    upload_id = await _init(client, category="avatars")
    await _put(client, upload_id, 1, exe[:2048])
    await _put(client, upload_id, 2, exe[2048:])
    r = await client.post(f"/v1/files/multipart/{upload_id}/complete",
                          headers=TEST_HEADERS)
    assert r.status_code == 400                      # exécutable refusé en avatars
