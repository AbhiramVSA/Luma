"""Database session management for Neon/Postgres."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (  # type: ignore[attr-defined]
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase  # type: ignore[attr-defined]

from config.config import settings


class Base(DeclarativeBase):
    """Base model for ORM declarations."""


if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured for authentication.")

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Ensure all ORM models are created."""

    from db import models  # noqa: F401 - ensures models are registered

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
