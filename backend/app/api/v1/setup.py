"""First-boot setup-wizard status (M7).

Inspects existing settings, secrets and CRUD-table population to decide
which of the wizard's checkboxes are already done. The wizard itself
lives in the frontend — this endpoint is only the data source and the
"Mark complete" toggle.

The wizard is a checklist, not a redirect. Operators can dismiss it
permanently via POST /complete (admin-only). Re-opening is done by
DELETing the completion flag.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.settings_tls import TLS_SOURCE_KEY
from app.audit import append as audit_append
from app.audit.actions import SETUP_WIZARD_COMPLETED, SETUP_WIZARD_REOPENED
from app.auth.sessions import SessionContext, require_session
from app.db.models import (
    Authorization,
    Device,
    DeviceGroup,
    LocalAdmin,
    PrivilegeProfile,
    SystemSecret,
    SystemSetting,
)
from app.db.session import get_session
from app.ldap_sync.worker import (
    SETTING_BASE_DNS,
    SETTING_BIND_DN,
)
from app.ldap_sync.worker import (
    SETTING_ENABLED as LDAP_SYNC_ENABLED_KEY,
)
from app.saml.config import (
    SECRET_SP_CERT,
    SECRET_SP_PRIVATE_KEY,
    SETTING_IDP_ENTITY_ID,
    SETTING_IDP_SSO_URL,
)
from app.syslog import SETTING_ENABLED as SYSLOG_ENABLED_KEY
from app.syslog import SETTING_HOST as SYSLOG_HOST_KEY
from app.tls.certs import CERT_FILE

router = APIRouter()

WEB_BASE_URL_KEY = "web.base_url"
LDAP_URL_KEY = "ldap.url"
WIZARD_COMPLETED_KEY = "setup.wizard_completed"


class SetupStep(BaseModel):
    key: str
    done: bool
    required: bool
    detail: str | None = None


class SetupStatus(BaseModel):
    completed: bool
    completed_by: str | None
    can_complete: bool
    steps: list[SetupStep]


SeverityT = Literal["required", "optional"]


async def _setting(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _secret(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _count(session: AsyncSession, model: type) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(model))).scalar_one()
    )


async def _build_status(session: AsyncSession) -> SetupStatus:
    steps: list[SetupStep] = []

    local_admin_count = await _count(session, LocalAdmin)
    steps.append(
        SetupStep(
            key="local_admin",
            done=local_admin_count > 0,
            required=True,
            detail=(
                "Break-glass admin set via `tacacs-web bootstrap-admin`"
                if local_admin_count > 0
                else "Run `tacacs-web bootstrap-admin` on the host"
            ),
        )
    )

    base_url = await _setting(session, WEB_BASE_URL_KEY)
    steps.append(
        SetupStep(
            key="web_base_url",
            done=bool(base_url),
            required=True,
            detail=base_url,
        )
    )

    tls_present = CERT_FILE.exists()
    tls_source = await _setting(session, TLS_SOURCE_KEY) if tls_present else None
    steps.append(
        SetupStep(
            key="tls",
            done=tls_present,
            required=True,
            detail=tls_source or ("bootstrap" if tls_present else None),
        )
    )

    ldap_url = await _setting(session, LDAP_URL_KEY)
    steps.append(
        SetupStep(
            key="ldap_url",
            done=bool(ldap_url),
            required=True,
            detail=ldap_url,
        )
    )

    ldap_bind = await _setting(session, SETTING_BIND_DN)
    ldap_base = await _setting(session, SETTING_BASE_DNS)
    ldap_sync_enabled_raw = await _setting(session, LDAP_SYNC_ENABLED_KEY)
    ldap_sync_on = (ldap_sync_enabled_raw or "false").lower() == "true"
    steps.append(
        SetupStep(
            key="ldap_sync",
            done=bool(ldap_bind and ldap_base),
            required=False,
            detail=(
                "AD-Sync scheduled" if ldap_sync_on else "Bind DN + Base DN stored"
            )
            if (ldap_bind and ldap_base)
            else None,
        )
    )

    sp_cert = await _secret(session, SECRET_SP_CERT)
    sp_key = await _secret(session, SECRET_SP_PRIVATE_KEY)
    idp_entity = await _setting(session, SETTING_IDP_ENTITY_ID)
    idp_sso = await _setting(session, SETTING_IDP_SSO_URL)
    saml_ready = bool(sp_cert and sp_key and idp_entity and idp_sso)
    steps.append(
        SetupStep(
            key="saml",
            done=saml_ready,
            required=False,
            detail=idp_entity if saml_ready else None,
        )
    )

    dg_count = await _count(session, DeviceGroup)
    steps.append(
        SetupStep(
            key="first_device_group",
            done=dg_count > 0,
            required=True,
            detail=f"{dg_count} configured",
        )
    )
    pp_count = await _count(session, PrivilegeProfile)
    steps.append(
        SetupStep(
            key="first_privilege_profile",
            done=pp_count > 0,
            required=True,
            detail=f"{pp_count} configured",
        )
    )
    dev_count = await _count(session, Device)
    steps.append(
        SetupStep(
            key="first_device",
            done=dev_count > 0,
            required=False,
            detail=f"{dev_count} configured",
        )
    )
    authz_count = await _count(session, Authorization)
    steps.append(
        SetupStep(
            key="first_authorization",
            done=authz_count > 0,
            required=False,
            detail=f"{authz_count} configured",
        )
    )

    syslog_host = await _setting(session, SYSLOG_HOST_KEY)
    syslog_enabled_raw = await _setting(session, SYSLOG_ENABLED_KEY)
    syslog_on = (syslog_enabled_raw or "false").lower() == "true"
    steps.append(
        SetupStep(
            key="syslog_forwarder",
            done=bool(syslog_host),
            required=False,
            detail=("forwarding enabled" if syslog_on else "host set, disabled")
            if syslog_host
            else None,
        )
    )

    completed_by = await _setting(session, WIZARD_COMPLETED_KEY)
    completed = bool(completed_by)
    can_complete = all(s.done for s in steps if s.required)

    return SetupStatus(
        completed=completed,
        completed_by=completed_by if completed_by and completed_by != "true" else None,
        can_complete=can_complete,
        steps=steps,
    )


@router.get("", response_model=SetupStatus)
async def get_setup_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatus:
    return await _build_status(session)


@router.post("/complete", response_model=SetupStatus)
async def complete_wizard(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatus:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    current = await _build_status(session)
    if not current.can_complete:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="required_steps_incomplete"
        )
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == WIZARD_COMPLETED_KEY)
        )
    ).scalar_one_or_none()
    marker = ctx.username or "admin"
    if row is None:
        session.add(SystemSetting(key=WIZARD_COMPLETED_KEY, value=marker))
    else:
        row.value = marker
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SETUP_WIZARD_COMPLETED,
        actor_id=ctx.actor_id,
        target_type="setup",
        summary=marker,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await _build_status(session)


@router.post("/reopen", response_model=SetupStatus)
async def reopen_wizard(
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SetupStatus:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == WIZARD_COMPLETED_KEY)
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await audit_append(
            session,
            actor_username_snapshot=ctx.username,
            actor_role=ctx.role,
            auth_method=ctx.auth_method,
            action=SETUP_WIZARD_REOPENED,
            actor_id=ctx.actor_id,
            target_type="setup",
            summary=ctx.username or "admin",
            client_ip=ctx.client_ip,
            user_agent=ctx.user_agent,
        )
        await session.commit()
    return await _build_status(session)
