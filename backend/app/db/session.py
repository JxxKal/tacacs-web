"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _resolve_url() -> str:
    url = settings.database_url
    password = settings.database_password()
    if not password:
        return url
    parsed = urlparse(url)
    user = parsed.username or ""
    host = parsed.hostname or ""
    netloc = f"{user}:{quote(password, safe='')}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


engine = create_async_engine(_resolve_url(), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one request-scoped async session."""
    async with SessionLocal() as session:
        yield session
