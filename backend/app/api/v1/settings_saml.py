"""SAML SP configuration endpoints.

GET /api/v1/settings/saml             -> current state (SP info + IdP info)
PUT /api/v1/settings/saml/idp-metadata-> import IdP metadata (xml in body)
PUT /api/v1/settings/saml/mapping     -> set group attribute + role mappings
POST /api/v1/settings/saml/sp-keypair -> regenerate the SP signing keypair

Persists into `system_setting` and `system_secret`. SP-side cert/key live
in `system_secret` so the AES-GCM master key seals them at rest.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append as audit_append
from app.audit.actions import (
    SAML_IDP_METADATA_IMPORTED,
    SAML_MAPPING_UPDATED,
    SAML_SP_KEYPAIR_REGENERATED,
)
from app.auth.sessions import SessionContext, require_session
from app.core.config import settings
from app.db.models import SystemSecret, SystemSetting
from app.db.session import get_session
from app.saml import (
    SamlConfig,
    SamlNotConfigured,
    generate_sp_keypair,
    load_saml_config,
    parse_idp_metadata,
    sp_acs_url,
    sp_entity_id,
)
from app.saml.config import (
    SAML_GROUP_ATTR_DEFAULT,
    SECRET_SP_CERT,
    SECRET_SP_PRIVATE_KEY,
    SETTING_GROUP_ATTRIBUTE,
    SETTING_IDP_ENTITY_ID,
    SETTING_IDP_METADATA_XML,
    SETTING_IDP_SSO_BINDING,
    SETTING_IDP_SSO_URL,
    SETTING_IDP_X509_CERT,
    SETTING_ROLE_MAPPINGS,
    SETTING_WEB_BASE_URL,
)
from app.saml.keypair import InvalidIdpMetadata

router = APIRouter()


class RoleMapping(BaseModel):
    ad_group: str = Field(..., min_length=1, max_length=512)
    role: Literal["admin", "operator", "viewer"]


class SamlStatusRead(BaseModel):
    configured: bool
    sp_entity_id: str | None
    sp_acs_url: str | None
    sp_has_keypair: bool
    idp_entity_id: str | None
    idp_sso_url: str | None
    idp_cert_present: bool
    group_attribute: str
    role_mappings: list[RoleMapping]


class IdpMetadataImport(BaseModel):
    xml: str = Field(..., min_length=1)


class MappingUpdate(BaseModel):
    group_attribute: str = Field(default=SAML_GROUP_ATTR_DEFAULT, max_length=256)
    role_mappings: list[RoleMapping] = Field(default_factory=list)

    @field_validator("group_attribute")
    @classmethod
    def _check_attr(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("group_attribute must not be empty")
        return v


class SpKeypairRegenerate(BaseModel):
    common_name: str | None = Field(default=None, max_length=253)


async def _read_setting(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _read_secret(session: AsyncSession, key: str) -> str | None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    return row.value if row is not None else None


async def _write_setting(session: AsyncSession, key: str, value: str) -> None:
    row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


async def _write_secret(session: AsyncSession, key: str, value: str) -> None:
    row = (
        await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemSecret(key=key, value=value))
    else:
        row.value = value


def _resolve_base_url(stored: str | None) -> str | None:
    return (stored or settings.base_url or "").rstrip("/") or None


@router.get("", response_model=SamlStatusRead)
async def get_saml_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SamlStatusRead:
    base_url = _resolve_base_url(await _read_setting(session, SETTING_WEB_BASE_URL))
    sp_cert = await _read_secret(session, SECRET_SP_CERT)
    sp_key = await _read_secret(session, SECRET_SP_PRIVATE_KEY)
    idp_entity = await _read_setting(session, SETTING_IDP_ENTITY_ID)
    idp_sso = await _read_setting(session, SETTING_IDP_SSO_URL)
    idp_cert = await _read_setting(session, SETTING_IDP_X509_CERT)
    group_attr = await _read_setting(session, SETTING_GROUP_ATTRIBUTE) or SAML_GROUP_ATTR_DEFAULT
    raw_mappings = await _read_setting(session, SETTING_ROLE_MAPPINGS) or "[]"
    try:
        mappings_data = json.loads(raw_mappings)
    except json.JSONDecodeError:
        mappings_data = []
    mappings = [
        RoleMapping.model_validate(m)
        for m in mappings_data
        if isinstance(m, dict) and m.get("role") in {"admin", "operator", "viewer"}
    ]

    configured = bool(base_url and sp_cert and sp_key and idp_entity and idp_sso and idp_cert)

    return SamlStatusRead(
        configured=configured,
        sp_entity_id=sp_entity_id(base_url) if base_url else None,
        sp_acs_url=sp_acs_url(base_url) if base_url else None,
        sp_has_keypair=bool(sp_cert and sp_key),
        idp_entity_id=idp_entity,
        idp_sso_url=idp_sso,
        idp_cert_present=bool(idp_cert),
        group_attribute=group_attr,
        role_mappings=mappings,
    )


@router.put("/idp-metadata", response_model=SamlStatusRead)
async def import_idp_metadata(
    payload: IdpMetadataImport,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SamlStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    try:
        idp = parse_idp_metadata(payload.xml)
    except InvalidIdpMetadata as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _write_setting(session, SETTING_IDP_ENTITY_ID, idp.entity_id)
    await _write_setting(session, SETTING_IDP_SSO_URL, idp.sso_url)
    await _write_setting(session, SETTING_IDP_SSO_BINDING, idp.sso_binding)
    await _write_setting(session, SETTING_IDP_X509_CERT, idp.x509_cert)
    await _write_setting(session, SETTING_IDP_METADATA_XML, payload.xml)
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SAML_IDP_METADATA_IMPORTED,
        actor_id=ctx.actor_id,
        target_type="saml.idp",
        summary=idp.entity_id,
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await get_saml_status(session)


@router.put("/mapping", response_model=SamlStatusRead)
async def update_mapping(
    payload: MappingUpdate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SamlStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")
    await _write_setting(session, SETTING_GROUP_ATTRIBUTE, payload.group_attribute)
    await _write_setting(
        session,
        SETTING_ROLE_MAPPINGS,
        json.dumps([m.model_dump() for m in payload.role_mappings]),
    )
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SAML_MAPPING_UPDATED,
        actor_id=ctx.actor_id,
        target_type="saml.mapping",
        summary=f"{len(payload.role_mappings)} mappings, attr={payload.group_attribute}",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await get_saml_status(session)


@router.post("/sp-keypair", response_model=SamlStatusRead)
async def regenerate_sp_keypair(
    payload: SpKeypairRegenerate,
    ctx: Annotated[SessionContext, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SamlStatusRead:
    if ctx.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin_required")

    cn = payload.common_name
    if not cn:
        base = _resolve_base_url(await _read_setting(session, SETTING_WEB_BASE_URL))
        if not base:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="common_name required (no base_url)"
            )
        cn = urlparse(base).hostname or "tacacs-web"

    cert_pem, key_pem = generate_sp_keypair(cn)
    await _write_secret(session, SECRET_SP_CERT, cert_pem.decode())
    await _write_secret(session, SECRET_SP_PRIVATE_KEY, key_pem.decode())
    await audit_append(
        session,
        actor_username_snapshot=ctx.username,
        actor_role=ctx.role,
        auth_method=ctx.auth_method,
        action=SAML_SP_KEYPAIR_REGENERATED,
        actor_id=ctx.actor_id,
        target_type="saml.sp",
        summary=f"CN={cn}",
        client_ip=ctx.client_ip,
        user_agent=ctx.user_agent,
    )
    await session.commit()
    return await get_saml_status(session)


@router.get("/sp-metadata")
async def get_sp_metadata(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Return the SP metadata XML so operators can register us with the IdP."""
    from app.saml import sp_metadata_xml

    try:
        cfg: SamlConfig = await load_saml_config(session)
    except SamlNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"saml_not_configured: {exc}") from exc
    xml = sp_metadata_xml(cfg)
    return Response(content=xml, media_type="application/samlmetadata+xml")
