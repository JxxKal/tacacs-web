"""Liveness and readiness probes.

`/healthz/live` — process is alive and the FastAPI app responds.
`/healthz/ready` — operational dependencies (DB, master key) are usable.

Returns 503 with a structured `checks` payload when any check fails, so an
operator (or Compose healthcheck) can see exactly which dependency is broken.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter()


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    overall_ok = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc.__class__.__name__}"
        overall_ok = False

    if settings.master_key_file is None:
        checks["master_key"] = "not_configured"
        overall_ok = False
    else:
        try:
            settings.master_key()
            checks["master_key"] = "ok"
        except Exception as exc:
            checks["master_key"] = f"error: {exc.__class__.__name__}"
            overall_ok = False

    body = {"status": "ok" if overall_ok else "fail", "checks": checks}
    return JSONResponse(body, status_code=200 if overall_ok else 503)
