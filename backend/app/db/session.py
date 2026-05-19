"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def resolve_database_url() -> str:
    """Compose the sqlalchemy URL with the password from the secret file mixed in.

    Shared between the async engine here and the sync Alembic env, so both
    code paths authenticate the same way against Postgres.
    """
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


engine = create_async_engine(resolve_database_url(), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one request-scoped async session."""
    async with SessionLocal() as session:
        yield session
