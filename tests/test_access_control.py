"""
StorageHub — Access control tests
Tests: owner access, other user denied, admin access, signed URL
"""
import io
import pytest

from tests.conftest import (
    TEST_HEADERS,
    ADMIN_HEADERS,
    OTHER_USER_HEADERS,
    make_minimal_jpeg,
    make_minimal_pdf,
)


async def upload_file(client, headers, category="kyc"):
    """Helper to upload a file and return file_id."""
    if category == "avatars":
        content = make_minimal_jpeg()
        filename = "avatar.jpg"
        mime = "image/jpeg"
    elif category == "kyc":
        content = make_minimal_pdf()
        filename = "cni.pdf"
        mime = "application/pdf"
    else:
        content = make_minimal_pdf()
        filename = "receipt.pdf"
        mime = "application/pdf"

    resp = await client.post(
        "/v1/files",
        files={"file": (filename, io.BytesIO(content), mime)},
        data={"category": category},
        headers=headers,
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


@pytest.mark.asyncio
async def test_owner_can_access_kyc_file(client):
    """File owner must be able to download their own KYC file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}", headers=TEST_HEADERS)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_other_user_cannot_access_kyc_file(client):
    """Another user must NOT be able to access someone else's KYC file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    # Different user tries to access
    resp = await client.get(f"/v1/files/{file_id}", headers=OTHER_USER_HEADERS)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_admin_can_access_any_file(client):
    """Admin user must be able to access any file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_file(client):
    """Unauthenticated request must be rejected."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_owner_can_get_meta(client):
    """Owner can retrieve file metadata."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}/meta", headers=TEST_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_id"] == file_id
    assert data["category"] == "kyc"
    assert data["url"] is None  # Sensitive file has no public URL


@pytest.mark.asyncio
async def test_owner_can_get_signed_url(client):
    """Owner can get a signed URL for their sensitive file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}/signed", headers=TEST_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "signed_url" in data
    assert "expires_at" in data
    assert data["ttl_seconds"] > 0


@pytest.mark.asyncio
async def test_signed_url_allows_download(client):
    """A valid signed URL must allow download without auth headers."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    # Get signed URL
    resp = await client.get(f"/v1/files/{file_id}/signed", headers=TEST_HEADERS)
    signed_url = resp.json()["signed_url"]

    # Extract query params from signed URL
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(signed_url)
    params = parse_qs(parsed.query)
    expires = params["expires"][0]
    sig = params["sig"][0]

    # Download via signed URL (no auth headers)
    dl_resp = await client.get(
        f"/v1/files/{file_id}/download",
        params={"expires": expires, "sig": sig},
    )
    assert dl_resp.status_code == 200


@pytest.mark.asyncio
async def test_tampered_signed_url_rejected(client):
    """Tampered signed URL must be rejected."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.get(f"/v1/files/{file_id}/signed", headers=TEST_HEADERS)
    data = resp.json()

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(data["signed_url"])
    params = parse_qs(parsed.query)
    expires = params["expires"][0]

    dl_resp = await client.get(
        f"/v1/files/{file_id}/download",
        params={"expires": expires, "sig": "tampered_signature"},
    )
    assert dl_resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_delete_own_file(client):
    """Owner can soft-delete their own file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.delete(f"/v1/files/{file_id}", headers=TEST_HEADERS)
    assert resp.status_code == 200

    # File should no longer be accessible
    resp2 = await client.get(f"/v1/files/{file_id}", headers=TEST_HEADERS)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_other_user_cannot_delete(client):
    """Another user must not be able to delete someone else's file."""
    file_id = await upload_file(client, TEST_HEADERS, "kyc")
    resp = await client.delete(f"/v1/files/{file_id}", headers=OTHER_USER_HEADERS)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_files_only_shows_own(client):
    """User listing files should only see their own files."""
    # Upload as user-001
    await upload_file(client, TEST_HEADERS, "avatars")
    await upload_file(client, TEST_HEADERS, "kyc")

    # Upload as user-002
    await upload_file(client, OTHER_USER_HEADERS, "kyc")

    # user-001 lists files
    resp = await client.get("/v1/files", headers=TEST_HEADERS)
    assert resp.status_code == 200
    files = resp.json()["items"]
    for f in files:
        assert f["owner_user_id"] == "user-001", f"Saw file from wrong owner: {f}"


@pytest.mark.asyncio
async def test_admin_sees_all_files(client):
    """Admin listing files should see all users' files."""
    await upload_file(client, TEST_HEADERS, "kyc")
    await upload_file(client, OTHER_USER_HEADERS, "kyc")

    resp = await client.get("/v1/files", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    files = resp.json()["items"]
    owner_ids = {f["owner_user_id"] for f in files}
    assert len(owner_ids) >= 2, "Admin should see files from multiple owners"
