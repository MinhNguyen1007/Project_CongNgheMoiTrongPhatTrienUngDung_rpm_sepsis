"""Async SQLAlchemy engine + session factory.

WHY async: FastAPI endpoint async, dùng sync session sẽ block event loop khi
query Postgres. asyncpg là driver async nhanh nhất cho Postgres.

WHY pool_size=10, max_overflow=20: 1 worker FastAPI + thread consumer + scheduler
+ websocket cùng dùng pool. 10+20 đủ cho dev, AWS RDS free tier max 20 connection
nên có thể giảm xuống 5+10 khi deploy.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Phát hiện stale connection sau khi Postgres restart
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Giữ object accessible sau commit (FastAPI response)
)


class Base(DeclarativeBase):
    """Base class cho tất cả ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. `Depends(get_db)` trong endpoint."""
    async with AsyncSessionLocal() as session:
        yield session
