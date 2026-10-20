"""
StorageHub — Test configuration and fixtures
"""
import asyncio
import io
import os
import struct
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Point to in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["UPLOAD_ROOT"] = str(Path(tempfile.mkdtemp()) / "test_uploads")
os.environ["API_KEY"] = "test-api-key"
os.environ["HMAC_SECRET"] = "test-hmac-secret"
os.environ["APP_ENV"] = "development"

from app.main import app
from app.database import Base, engine, AsyncSessionLocal, get_db

TEST_API_KEY = "test-api-key"
TEST_HEADERS = {
    "X-API-Key": TEST_API_KEY,
    "X-User-Id": "user-001",
    "X-User-Role": "user",
}
ADMIN_HEADERS = {
    "X-API-Key": TEST_API_KEY,
    "X-User-Id": "admin-001",
    "X-User-Role": "admin",
}
OTHER_USER_HEADERS = {
    "X-API-Key": TEST_API_KEY,
    "X-User-Id": "user-002",
    "X-User-Role": "user",
}


def make_minimal_jpeg() -> bytes:
    """Generate a minimal valid JPEG file (1x1 pixel)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


def make_minimal_png() -> bytes:
    """Generate a minimal valid PNG file (1x1 pixel)."""
    import zlib
    import struct

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png_sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    ihdr = png_chunk(b"IHDR", ihdr_data)
    raw_data = b"\x00\xff\x00\xff"  # filter byte + RGB pixel
    idat = png_chunk(b"IDAT", zlib.compress(raw_data))
    iend = png_chunk(b"IEND", b"")
    return png_sig + ihdr + idat + iend


def make_minimal_pdf() -> bytes:
    """Generate a minimal valid PDF file."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n9\n%%EOF"
    )


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def client():
    """Async test client with fresh DB per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
