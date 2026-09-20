"""
SQLAlchemy database engines, session factories, and dependency injectors.
Provides both AsyncSession for modern FastAPI routes and SyncSession for legacy scripts.
"""

from __future__ import annotations

from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

# Asynchronous engine and session factory
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Synchronous engine and session factory (for migrations, scripts, sync helpers)
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.SYNC_DATABASE_URL else {},
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Creates database tables if they do not exist yet."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
