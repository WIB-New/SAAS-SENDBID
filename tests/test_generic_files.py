"""
StorageHub — Generic 'files' category tests
Tests: arbitrary types, octet-stream, executables still blocked,
       folder upload metadata, privacy, regressions on strict categories.
"""
import io
import pytest

from tests.conftest import (
    TEST_HEADERS,
    make_minimal_jpeg,
    make_minimal_pdf,
)


@pytest.mark.asyncio
async def test_files_accepts_arbitrary_binary(client):
    """Unknown magic bytes → application/octet-stream, accepted."""
    blob = b"\x01\x02\x03\x04BINARYDATA" * 10
    resp = await client.post(
        "/v1/files",
        files={"file": ("data.bin", io.BytesIO(blob), "application/octet-stream")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["category"] == "files"
    assert data["mime"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_files_accepts_zip(client):
    """ZIP archive (PK magic) must be accepted in the generic category."""
    zip_bytes = b"PK\x03\x04" + b"\x00" * 100
    resp = await client.post(
        "/v1/files",
        files={"file": ("archive.zip", io.BytesIO(zip_bytes), "application/zip")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_files_accepts_pdf(client):
    """PDF under 'files' keeps its detected MIME."""
    pdf = make_minimal_pdf()
    resp = await client.post(
        "/v1/files",
        files={"file": ("doc.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["mime"] == "application/pdf"


@pytest.mark.asyncio
async def test_files_is_private_no_public_url(client):
    """'files' must never produce a public URL."""
    resp = await client.post(
        "/v1/files",
        files={"file": ("note.txt", io.BytesIO(b"hello world"), "text/plain")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["url"] is None
    assert data["public"] is False
    # Public avatar route must not serve it
    pub = await client.get(f"/v1/public/avatars/{data['file_id']}")
    assert pub.status_code == 404


@pytest.mark.asyncio
async def test_files_executable_still_blocked(client):
    """Windows PE (MZ) must be rejected by the antivirus scan even in 'files'."""
    pe = b"MZ" + b"\x00" * 200
    resp = await client.post(
        "/v1/files",
        files={"file": ("app.exe", io.BytesIO(pe), "application/octet-stream")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_files_elf_still_blocked(client):
    """ELF binary must be rejected in 'files' too."""
    elf = b"\x7fELF" + b"\x00" * 200
    resp = await client.post(
        "/v1/files",
        files={"file": ("run", io.BytesIO(elf), "application/octet-stream")},
        data={"category": "files"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_files_folder_metadata_preserved(client):
    """folder param is stored in tags and readable via /meta."""
    resp = await client.post(
        "/v1/files",
        files={"file": ("photo.png", io.BytesIO(make_minimal_jpeg()), "image/jpeg")},
        data={"category": "files", "folder": "vacances/2024"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    meta = await client.get(
        f"/v1/files/{resp.json()['file_id']}/meta", headers=TEST_HEADERS
    )
    assert meta.status_code == 200
    assert meta.json()["tags"]["folder"] == "vacances/2024"


@pytest.mark.asyncio
async def test_files_folder_traversal_sanitized(client):
    """'../../etc/evil' folder path must be neutralized."""
    resp = await client.post(
        "/v1/files",
        files={"file": ("f.bin", io.BytesIO(b"\x99data"), "application/octet-stream")},
        data={"category": "files", "folder": "../../etc/evil"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    meta = await client.get(
        f"/v1/files/{resp.json()['file_id']}/meta", headers=TEST_HEADERS
    )
    folder = meta.json()["tags"]["folder"]
    assert ".." not in folder
    assert folder == "etc/evil"


@pytest.mark.asyncio
async def test_files_bulk_upload(client):
    """Bulk endpoint accepts 'files' category with folder field."""
    resp = await client.post(
        "/v1/files/bulk",
        files=[
            ("files", ("a.txt", io.BytesIO(b"aaa"), "text/plain")),
            ("files", ("b.bin", io.BytesIO(b"\x00\x01"), "application/octet-stream")),
        ],
        data={"category": "files", "folder": "batch/import"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["uploaded"] == 2
    assert data["failed"] == 0


@pytest.mark.asyncio
async def test_strict_category_still_rejects_octet_stream(client):
    """Regression: 'avatars' must still reject unknown binary content."""
    resp = await client.post(
        "/v1/files",
        files={"file": ("x.bin", io.BytesIO(b"\x01\x02\x03"), "application/octet-stream")},
        data={"category": "avatars"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_strict_category_still_rejects_zip(client):
    """Regression: 'kyc' must still reject ZIP archives."""
    resp = await client.post(
        "/v1/files",
        files={"file": ("a.zip", io.BytesIO(b"PK\x03\x04" + b"\x00" * 50), "application/zip")},
        data={"category": "kyc"},
        headers=TEST_HEADERS,
    )
    assert resp.status_code == 400
