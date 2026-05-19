"""Pytest setup: seed minimal env so `app.core.config.settings` constructs
without requiring real secrets, then provide reusable DB fixtures.
"""

from __future__ import annotations

import base64
import os
import secrets as _secrets
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Provide a tmp master-key file in the same shape an operator gets from
# `openssl rand -base64 32 > master.key` — base64 of 32 random bytes plus
# a trailing newline. Mirrors the documented bootstrap procedure.
_TMP = Path(tempfile.mkdtemp(prefix="tacacs-web-tests-"))
_MASTER_KEY = _TMP / "master.key"
_MASTER_KEY.write_bytes(base64.b64encode(_secrets.token_bytes(32)) + b"\n")

os.environ.setdefault("MASTER_KEY_FILE", str(_MASTER_KEY))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/tacacs_test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Cookies emitted by Set-Cookie with Secure=true are stripped on http://;
# tests run over http via TestClient, so opt out of Secure here.
os.environ.setdefault("SESSION_COOKIE_SECURE", "false")
# TLS settings module writes cert/key files; point that at a tmp path so
# tests don't reach the production /var/lib/tacacs-web/tls volume mount.
_TLS_TMP = _TMP / "tls"
_TLS_TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TACACS_WEB_TLS_DIR", str(_TLS_TMP))
# Same trick for the tac_plus-ng dynamic hosts.cfg path.
_NAS_CONFIG_TMP = _TMP / "tac_plus-ng"
_NAS_CONFIG_TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TACACS_WEB_NAS_CONFIG_DIR", str(_NAS_CONFIG_TMP))


from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db import models  # noqa: E402, F401  (registers ORM models on Base.metadata)
from app.db.base import Base  # noqa: E402


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with every ORM table created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture
async def async_db_session() -> AsyncIterator[AsyncSession]:
    """Async SQLite session for endpoint integration tests.

    Each test gets a fresh in-memory DB so write ordering between tests
    can't leak. The session is bound to a single connection so the FastAPI
    handler sees the same view as the test's bootstrap inserts.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
