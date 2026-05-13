"""FastAPI app entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, internal_mavis
from app.api.v1 import (
    authorizations,
    device_groups,
    devices,
    effective_permissions,
    privilege_profiles,
)
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
app.include_router(internal_mavis.router, prefix="/internal/mavis", tags=["internal"])
app.include_router(
    device_groups.router, prefix="/api/v1/device-groups", tags=["device-groups"]
)
app.include_router(
    privilege_profiles.router,
    prefix="/api/v1/privilege-profiles",
    tags=["privilege-profiles"],
)
app.include_router(devices.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(
    authorizations.router, prefix="/api/v1/authorizations", tags=["authorizations"]
)
app.include_router(effective_permissions.router, prefix="/api/v1", tags=["effective-permissions"])
