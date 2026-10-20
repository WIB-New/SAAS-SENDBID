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

        await conn.run_sync(_migrate)
