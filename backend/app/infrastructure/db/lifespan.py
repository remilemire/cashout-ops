from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@dataclass(frozen=True)
class DatabaseResources:
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def db_lifespan() -> AsyncGenerator[DatabaseResources]:
    """Build the async engine and session factory; dispose the engine on exit."""
    engine = create_async_engine(settings.db.URL)
    sessionmaker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        yield DatabaseResources(engine=engine, sessionmaker=sessionmaker)
    finally:
        await engine.dispose()
