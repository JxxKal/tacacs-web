"""FastAPI app entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="tacacs-web",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/healthz", tags=["health"])
