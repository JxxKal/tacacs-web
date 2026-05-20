"""FastAPI app entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.accounting import ingestor as acct_ingestor
from app.api import auth_local, health, internal_mavis, saml_routes
from app.api.v1 import (
    accounting,
    admin,
    audit_log,
    authorizations,
    device_groups,
    devices,
    effective_permissions,
    principals,
    privilege_profiles,
    settings_ldap_sync,
    settings_saml,
    settings_tls,
)
from app.api.v1 import (
    settings as v1_settings,
)
from app.auth.sessions import require_session
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.ldap_sync import scheduler as ldap_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    ldap_scheduler.start_scheduler()
    acct_ingestor.start_ingestor()
    try:
        yield
    finally:
        await acct_ingestor.stop_ingestor()
        ldap_scheduler.stop_scheduler()
        await engine.dispose()


app = FastAPI(
    title="tacacs-web",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/healthz", tags=["health"])
app.include_router(auth_local.router, tags=["auth"])
app.include_router(saml_routes.router, prefix="/saml", tags=["auth"])
app.include_router(internal_mavis.router, prefix="/internal/mavis", tags=["internal"])

# /api/v1/* sits behind the session dependency. Everything below uses the
# `require_session` dep at router-mount time; routes can additionally gate
# on `require_admin` for write paths if/when we split viewer vs admin.
_API_V1_DEPS = [Depends(require_session)]

app.include_router(
    device_groups.router,
    prefix="/api/v1/device-groups",
    tags=["device-groups"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    privilege_profiles.router,
    prefix="/api/v1/privilege-profiles",
    tags=["privilege-profiles"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    devices.router,
    prefix="/api/v1/devices",
    tags=["devices"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    authorizations.router,
    prefix="/api/v1/authorizations",
    tags=["authorizations"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    effective_permissions.router,
    prefix="/api/v1",
    tags=["effective-permissions"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    principals.users_router,
    prefix="/api/v1/users",
    tags=["principals"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    principals.ad_groups_router,
    prefix="/api/v1/ad-groups",
    tags=["principals"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    v1_settings.router,
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    settings_tls.router,
    prefix="/api/v1/settings/tls",
    tags=["settings"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    settings_saml.router,
    prefix="/api/v1/settings/saml",
    tags=["settings"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    settings_ldap_sync.router,
    prefix="/api/v1/settings/ldap-sync",
    tags=["settings"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    admin.router,
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    audit_log.router,
    prefix="/api/v1/audit-log",
    tags=["audit-log"],
    dependencies=_API_V1_DEPS,
)
app.include_router(
    accounting.router,
    prefix="/api/v1/accounting",
    tags=["accounting"],
    dependencies=_API_V1_DEPS,
)
