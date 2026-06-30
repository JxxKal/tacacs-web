"""SAML 2.0 SP HTTP routes: /saml/login, /saml/acs, /saml/metadata.

Flow:
1. Browser hits /login (SPA), clicks "Sign in with SAML" -> GET /saml/login.
2. Backend builds an AuthnRequest, redirects to the IdP SSO URL.
3. IdP authenticates the user (out of our scope) and POSTs a SAML
   Response to /saml/acs.
4. /saml/acs validates the signature, extracts NameID + group claims,
   maps groups to role per the stored mapping, creates a session, and
   redirects to /.
5. /saml/metadata exports the SP metadata XML for the IdP admin to
   register us as a trusted SP.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append as audit_append
from app.audit.actions import AUTH_LOGIN_FAILED, AUTH_LOGIN_SUCCEEDED
from app.auth.sessions import (
    SESSION_COOKIE_NAME,
    SESSION_SLIDING_LIFETIME,
    create_session,
)
from app.core.config import settings
from app.db.models import User
from app.db.session import get_session
from app.saml import (
    SamlNotConfigured,
    build_auth_for_request,
    load_saml_config,
    sp_metadata_xml,
)
from app.saml.config import build_request_data

router = APIRouter()


def _request_data(
    request: Request,
    base_url: str,
    post_data: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build the request-data dict python3-saml expects.

    Host / port / scheme are derived from the configured `base_url`, NOT
    from the proxied request. nginx terminates TLS and forwards to
    uvicorn over plain HTTP on port 8000, so `request.url.scheme` is
    always "http" and the port doesn't match what the IdP actually saw.
    Reading from cfg.base_url keeps the Destination check in
    auth.process_response() aligned with the IdP-side ACS URL.
    """
    parsed = urlparse(base_url)
    https = parsed.scheme == "https"
    return build_request_data(
        http_host=parsed.hostname or "localhost",
        server_port=parsed.port or (443 if https else 80),
        https=https,
        request_uri=request.url.path,
        get_data=dict(request.query_params),
        post_data=post_data or {},
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _resolve_role(
    group_values: list[str], mappings: tuple[tuple[str, str], ...]
) -> str | None:
    """Find the highest-precedence role from `mappings` that matches.

    First entry wins (mapping order is operator-controlled in the UI).
    Mapping key is matched case-insensitively against either a CN, DN, or
    plain group name presented in the assertion.
    """
    lowered = {v.lower() for v in group_values}
    for ad_group, role in mappings:
        if ad_group.lower() in lowered:
            return role
        # Match by CN= prefix as a convenience.
        for value in lowered:
            if value.startswith(f"cn={ad_group.lower()},"):
                return role
    return None


async def _synced_group_dns(
    session: AsyncSession, sam_account_name: str
) -> list[str] | None:
    """Group DNs of the SAML user from the AD-synced tables, or None if unknown.

    FortiAuthenticator authenticates the user but does not reliably carry AD
    group memberships in the assertion, so we resolve the role from the same
    locally-synced `user`/`ad_group` data that drives MAVIS authorization
    rather than from a SAML attribute. Returns None when the user is absent
    from the sync (or disabled) — distinct from "synced but in no group".
    """
    user = (
        await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(func.lower(User.sam_account_name) == sam_account_name.lower())
        )
    ).scalar_one_or_none()
    if user is None or not user.enabled:
        return None
    return [g.distinguished_name for g in user.groups]


@router.get("/login")
async def saml_login(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RedirectResponse:
    try:
        cfg = await load_saml_config(session)
    except SamlNotConfigured as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"saml_not_configured: {exc}"
        ) from exc
    auth = build_auth_for_request(
        cfg, request_data=_request_data(request, cfg.base_url)
    )
    target = auth.login(return_to=f"{cfg.base_url}/")
    return RedirectResponse(target, status_code=302)


@router.get("/metadata")
async def saml_metadata(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    try:
        cfg = await load_saml_config(session)
    except SamlNotConfigured as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"saml_not_configured: {exc}"
        ) from exc
    xml = sp_metadata_xml(cfg)
    return Response(content=xml, media_type="application/samlmetadata+xml")


@router.post("/acs")
async def saml_acs(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RedirectResponse:
    form = await request.form()
    post_data = {k: str(v) for k, v in form.items()}
    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    try:
        cfg = await load_saml_config(session)
    except SamlNotConfigured as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"saml_not_configured: {exc}"
        ) from exc

    auth = build_auth_for_request(
        cfg, request_data=_request_data(request, cfg.base_url, post_data)
    )
    auth.process_response()
    errors = auth.get_errors()
    if errors or not auth.is_authenticated():
        await audit_append(
            session,
            actor_username_snapshot="<saml>",
            actor_role="unknown",
            auth_method="saml",
            action=AUTH_LOGIN_FAILED,
            summary=f"errors={errors!r}; reason={auth.get_last_error_reason()!r}",
            client_ip=client_ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="saml_validation_failed"
        )

    name_id = auth.get_nameid() or "<unknown>"

    # Group memberships come from the AD-synced DB (keyed by sAMAccountName =
    # the SAML NameID), not from a SAML attribute — the IdP authenticates the
    # user but does not reliably carry group claims in the assertion.
    group_values = await _synced_group_dns(session, name_id)
    role = (
        _resolve_role(group_values, cfg.role_mappings)
        if group_values is not None
        else None
    )
    if role is None:
        detail = "user_not_synced" if group_values is None else "no_role_mapping"
        await audit_append(
            session,
            actor_username_snapshot=name_id,
            actor_role="unknown",
            auth_method="saml",
            action=AUTH_LOGIN_FAILED,
            summary=f"{detail}; groups={group_values!r}",
            client_ip=client_ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=detail)

    ws = await create_session(
        session,
        username=name_id,
        role=role,
        auth_method="saml",
        actor_id=None,
        client_ip=client_ip,
    )
    await audit_append(
        session,
        actor_username_snapshot=name_id,
        actor_role=role,
        auth_method="saml",
        action=AUTH_LOGIN_SUCCEEDED,
        summary=f"groups={group_values!r}",
        client_ip=client_ip,
        user_agent=user_agent,
    )
    await session.commit()

    response = RedirectResponse(url=f"{cfg.base_url}/", status_code=302)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        ws.token,
        max_age=int(SESSION_SLIDING_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response
