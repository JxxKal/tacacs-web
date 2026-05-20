"""Vendor-config snippet hints (M7 follow-up).

Operators who just provisioned a new NAS need a paste-ready
`aaa` block for their vendor. The snippet itself lives in the
frontend (locale-friendly, copy-paste); this endpoint only hands
back the small bits of server-side state the snippet needs —
the canonical hostname the device should point at and the TACACS+
TCP port (49 by default; never re-mapped because every NAS
expects it there).

No secrets travel in this payload — the snippet has a
`<SHARED_SECRET>` placeholder that the operator fills in from the
device row.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SystemSetting
from app.db.session import get_session

router = APIRouter()

TACACS_PORT = 49
WEB_BASE_URL_KEY = "web.base_url"


class DeviceTemplateHints(BaseModel):
    server_host: str | None
    tacacs_port: int


@router.get("", response_model=DeviceTemplateHints)
async def get_hints(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeviceTemplateHints:
    row = (
        await session.execute(
            select(SystemSetting).where(SystemSetting.key == WEB_BASE_URL_KEY)
        )
    ).scalar_one_or_none()
    host: str | None = None
    if row is not None and row.value:
        host = urlparse(row.value).hostname
    return DeviceTemplateHints(server_host=host, tacacs_port=TACACS_PORT)
