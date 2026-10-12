"""
StorageHub — Database setup (SQLAlchemy async)
"""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Support both SQLite (dev) and PostgreSQL (prod)
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
    """Create all tables on startup + apply lightweight column migrations."""
    async with engine.begin() as conn:
        from app import models  # noqa: F401 — triggers model registration
        await conn.run_sync(Base.metadata.create_all)

        # create_all never alters existing tables — add missing columns
        def _migrate(sync_conn):
            insp = inspect(sync_conn)
            cols = {c["name"] for c in insp.get_columns("stored_files")}
            if "client_id" not in cols:
                sync_conn.execute(
                    text("ALTER TABLE stored_files ADD COLUMN client_id VARCHAR(36)")
                )
            sync_conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_stored_files_client_id "
                     "ON stored_files (client_id)")
            )

        await conn.run_sync(_migrate)
