"""
SAAS SENDBID — Database setup (SQLAlchemy async)
"""
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
    """Create all tables on startup."""
    async with engine.begin() as conn:
        from app import models  # noqa: F401 — triggers model registration
        await conn.run_sync(Base.metadata.create_all)
