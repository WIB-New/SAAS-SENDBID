"""
StorageHub — Database setup (SQLAlchemy async)
"""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

db_url = settings.database_url
if db_url.startswith("sqlite"):
    engine = create_async_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=(settings.app_env == "development"),
    )
else:
    engine = create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        echo=(settings.app_env == "development"),
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Crée toutes les tables + migrations légères sur les colonnes existantes."""
    async with engine.begin() as conn:
        from app import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        def _migrate(sync_conn):
            insp = inspect(sync_conn)
            tables = insp.get_table_names()

            # ── stored_files ──────────────────────────────
            if "stored_files" in tables:
                sf_cols = {c["name"] for c in insp.get_columns("stored_files")}
                migrations = {
                    "client_id":      "VARCHAR(36)",
                    "folder":         "VARCHAR(512)",
                    "tags":           "TEXT",
                    "thumbnail_path": "VARCHAR(1024)",
                    "is_encrypted":   "BOOLEAN DEFAULT false",
                    "parent_id":      "VARCHAR(36)",
                    "version":        "INTEGER DEFAULT 1",
                }
                for col, typedef in migrations.items():
                    if col not in sf_cols:
                        sync_conn.execute(
                            text(f"ALTER TABLE stored_files ADD COLUMN {col} {typedef}")
                        )
                sync_conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_stored_files_client_id "
                         "ON stored_files (client_id)")
                )

            # ── webhook_deliveries ────────────────────────
            if "webhook_deliveries" in tables:
                wd_cols = {c["name"] for c in insp.get_columns("webhook_deliveries")}
                if "attempts" not in wd_cols:
                    sync_conn.execute(
                        text("ALTER TABLE webhook_deliveries ADD COLUMN attempts INTEGER DEFAULT 1")
                    )

            # ── api_keys : hachage des clés existantes ────
            if "api_keys" in tables:
                ak_cols = {c["name"] for c in insp.get_columns("api_keys")}
                if "key_hint" not in ak_cols:
                    sync_conn.execute(
                        text("ALTER TABLE api_keys ADD COLUMN key_hint VARCHAR(64)")
                    )
                # Convertir les clés en clair → empreinte SHA-256 + hint.
                rows = sync_conn.execute(
                    text("SELECT id, api_key FROM api_keys WHERE api_key NOT LIKE 'sha256$%'")
                ).fetchall()
                if rows:
                    from app.utils.security import hash_api_key, api_key_hint
                    for row_id, raw_key in rows:
                        sync_conn.execute(
                            text("UPDATE api_keys SET api_key = :h, key_hint = :hint WHERE id = :id"),
                            {"h": hash_api_key(raw_key), "hint": api_key_hint(raw_key), "id": row_id},
                        )

        await conn.run_sync(_migrate)
