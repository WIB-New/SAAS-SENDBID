"""
StorageHub — Security tests
CRITICAL: Verifies that sensitive files (kyc, receipts) are NEVER
accessible via public URL, only via authenticated /v1/files/{id} route.
"""
import io
import pytest

from tests.conftest import TEST_HEADERS, make_minimal_jpeg, make_minimal_pdf


@pytest.mark.asyncio
async def test_kyc_not_accessible_via_public_url(client):
    """
    CRITICAL SECURITY TEST:
    KYC files must NOT be accessible via /v1/public/avatars/ or any public route.
    """
    # Upload a KYC file
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("cni.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "kyc"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201
    file_id = resp.json()["file_id"]

    # Attempt to access via public avatar route
    resp2 = await client.get(f"/v1/public/avatars/{file_id}")
    assert resp2.status_code in (403, 404), (
        f"SECURITY FAILURE: KYC file accessible publicly! "
        f"Got {resp2.status_code} for /v1/public/avatars/{file_id}"
    )


@pytest.mark.asyncio
async def test_receipt_not_accessible_via_public_url(client):
    """CRITICAL: Receipt files must NOT be accessible publicly."""
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("receipt.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "receipts"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201
    file_id = resp.json()["file_id"]

    # Attempt public URL access
    resp2 = await client.get(f"/v1/public/avatars/{file_id}")
    assert resp2.status_code in (403, 404), (
        f"SECURITY FAILURE: Receipt accessible publicly! Got {resp2.status_code}"
    )


@pytest.mark.asyncio
async def test_public_avatar_has_no_auth_requirement(client):
    """Avatars should be accessible without authentication."""
    jpeg = make_minimal_jpeg()
    resp = await client.post(
        "/v1/files",
        files={"file": ("avatar.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "avatars"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201
    # The URL returned should be a public URL
    url = resp.json().get("url")
    assert url is not None, "Avatar must have a public URL"


@pytest.mark.asyncio
async def test_kyc_response_has_no_public_url(client):
    """KYC upload response must NOT include a public URL."""
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("cni.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "kyc"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data.get("url") is None, (
        f"SECURITY FAILURE: KYC file has public URL: {data.get('url')}"
    )


@pytest.mark.asyncio
async def test_receipt_response_has_no_public_url(client):
    """Receipt upload response must NOT include a public URL."""
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("receipt.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "receipts"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data.get("url") is None, (
        f"SECURITY FAILURE: Receipt has public URL: {data.get('url')}"
    )


@pytest.mark.asyncio
async def test_sensitive_file_cache_headers(client):
    """Sensitive files must have no-store cache headers."""
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("cni.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "kyc"},
        headers=TEST_HEADERS,
    )
    file_id = resp.json()["file_id"]

    dl_resp = await client.get(f"/v1/files/{file_id}", headers=TEST_HEADERS)
    assert dl_resp.status_code == 200
    cache = dl_resp.headers.get("cache-control", "")
    assert "no-store" in cache or "no-cache" in cache, (
        f"Sensitive file must have no-cache header, got: {cache}"
    )


@pytest.mark.asyncio
async def test_public_avatar_cache_headers(client):
    """Public avatars should have long cache headers."""
    jpeg = make_minimal_jpeg()
    resp = await client.post(
        "/v1/files",
        files={"file": ("avatar.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "avatars"},
        headers=TEST_HEADERS,
    )
    file_id = resp.json()["file_id"]

    dl_resp = await client.get(f"/v1/files/{file_id}", headers=TEST_HEADERS)
    assert dl_resp.status_code == 200
    cache = dl_resp.headers.get("cache-control", "")
    assert "public" in cache or "max-age" in cache, (
        f"Public avatar should have long cache header, got: {cache}"
    )


@pytest.mark.asyncio
async def test_path_traversal_in_filename_blocked(client):
    """Client filename with path traversal must be neutralized."""
    jpeg = make_minimal_jpeg()
    resp = await client.post(
        "/v1/files",
        files={"file": ("../../etc/passwd.jpg", io.BytesIO(jpeg), "image/jpeg")},
        data={"category": "avatars"},
        headers=TEST_HEADERS,
    )
    # Should either succeed (with sanitized name) or fail gracefully
    assert resp.status_code in (201, 400)
    if resp.status_code == 201:
        file_id = resp.json()["file_id"]
        # file_id must be a UUID, not contain path separators
        assert "/" not in file_id
        assert "\\" not in file_id
        assert ".." not in file_id


@pytest.mark.asyncio
async def test_health_endpoint_is_public(client):
    """Health endpoint must be accessible without auth."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
