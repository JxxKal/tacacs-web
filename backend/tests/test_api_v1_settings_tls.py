"""Tests for the TLS settings endpoints."""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import (
    TLS_CERT_REGENERATED,
    TLS_CERT_UPLOADED,
    TLS_PFX_UPLOADED,
)
from app.auth.sessions import SessionContext, require_session
from app.db.models import AuditLog
from app.db.session import get_session
from app.main import app
from app.tls import generate_self_signed
from app.tls.certs import CERT_FILE, KEY_FILE, TLS_DIR


def _build_pfx(common_name: str, password: str | None) -> bytes:
    """Bundle a fresh self-signed cert + key into a PKCS#12 blob.

    Used to feed `/upload-pfx` in tests without an external fixture.
    """
    cert_pem, key_pem = generate_self_signed(common_name, days=30)
    cert = x509.load_pem_x509_certificate(cert_pem)
    key = serialization.load_pem_private_key(key_pem, password=None)
    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(password.encode("utf-8"))
        if password
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=encryption,
    )


def _make_session(role: str = "admin") -> SessionContext:
    return SessionContext(
        token="test-token",
        username=f"test-{role}",
        role=role,
        auth_method="local",
        actor_id=1,
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


@pytest.fixture(autouse=True)
def _clean_tls_dir() -> Iterator[None]:
    for p in (CERT_FILE, KEY_FILE):
        if p.exists():
            p.unlink()
    yield
    for p in (CERT_FILE, KEY_FILE):
        if p.exists():
            p.unlink()


@pytest.fixture
def admin_client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _make_session("admin")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(async_db_session: AsyncSession) -> Iterator[TestClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield async_db_session

    async def _override_require_session() -> SessionContext:
        return _make_session("viewer")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_session] = _override_require_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_tls_dir_points_to_test_tmpdir() -> None:
    # Sanity-check the conftest override is in effect before we touch files.
    assert os.environ.get("TACACS_WEB_TLS_DIR") is not None
    assert str(TLS_DIR) == os.environ["TACACS_WEB_TLS_DIR"]


def test_get_returns_no_cert_when_missing(admin_client: TestClient) -> None:
    r = admin_client.get("/api/v1/settings/tls")
    assert r.status_code == 200
    assert r.json() == {"has_cert": False, "info": None}


def test_get_parses_existing_cert_on_volume(admin_client: TestClient) -> None:
    cert_pem, key_pem = generate_self_signed("smoke.example", days=1)
    CERT_FILE.write_bytes(cert_pem)
    KEY_FILE.write_bytes(key_pem)
    r = admin_client.get("/api/v1/settings/tls")
    assert r.status_code == 200
    body = r.json()
    assert body["has_cert"] is True
    assert body["info"]["subject_cn"] == "smoke.example"
    assert body["info"]["is_self_signed"] is True
    assert body["info"]["source"] == "bootstrap"


async def test_upload_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    cert_pem, key_pem = generate_self_signed("uploaded.example", days=30)
    r = admin_client.post(
        "/api/v1/settings/tls/upload",
        json={"cert_pem": cert_pem.decode(), "key_pem": key_pem.decode()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_cert"] is True
    assert body["info"]["subject_cn"] == "uploaded.example"
    assert body["info"]["source"] == "uploaded"

    assert CERT_FILE.read_bytes() == cert_pem
    assert KEY_FILE.read_bytes() == key_pem

    audits = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == TLS_CERT_UPLOADED)
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].summary is not None
    assert audits[0].summary.startswith("uploaded.example")


def test_upload_rejects_mismatched_key(admin_client: TestClient) -> None:
    cert_pem, _ = generate_self_signed("a.example")
    _, other_key_pem = generate_self_signed("b.example")
    r = admin_client.post(
        "/api/v1/settings/tls/upload",
        json={"cert_pem": cert_pem.decode(), "key_pem": other_key_pem.decode()},
    )
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]
    assert not CERT_FILE.exists()


def test_upload_rejects_malformed_cert(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/v1/settings/tls/upload",
        json={"cert_pem": "not a cert", "key_pem": "not a key"},
    )
    assert r.status_code == 400


def test_viewer_cannot_upload(viewer_client: TestClient) -> None:
    cert_pem, key_pem = generate_self_signed("a.example")
    r = viewer_client.post(
        "/api/v1/settings/tls/upload",
        json={"cert_pem": cert_pem.decode(), "key_pem": key_pem.decode()},
    )
    assert r.status_code == 403


async def test_regenerate_self_signed_writes_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    r = admin_client.post(
        "/api/v1/settings/tls/regenerate-self-signed",
        json={"common_name": "fresh.example", "days": 30},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["info"]["subject_cn"] == "fresh.example"
    assert body["info"]["source"] == "self_signed_via_ui"
    # SAN should include the CN we asked for.
    assert "fresh.example" in body["info"]["san_dns"]

    assert CERT_FILE.exists() and KEY_FILE.exists()

    audits = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == TLS_CERT_REGENERATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


def test_regenerate_validates_days_bounds(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/v1/settings/tls/regenerate-self-signed",
        json={"common_name": "x.example", "days": 0},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /upload-pfx
# ---------------------------------------------------------------------------


async def test_upload_pfx_with_password_persists_and_audits(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    pfx = _build_pfx("pfx.example", "letmein")
    r = admin_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={
            "pfx_base64": base64.b64encode(pfx).decode("ascii"),
            "password": "letmein",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_cert"] is True
    assert body["info"]["subject_cn"] == "pfx.example"
    assert body["info"]["source"] == "uploaded"

    # Files were written; cert + key extracted correctly.
    assert CERT_FILE.exists() and KEY_FILE.exists()
    assert b"BEGIN CERTIFICATE" in CERT_FILE.read_bytes()
    assert b"BEGIN PRIVATE KEY" in KEY_FILE.read_bytes()

    audits = (
        (
            await async_db_session.execute(
                select(AuditLog).where(AuditLog.action == TLS_PFX_UPLOADED)
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].summary is not None
    assert audits[0].summary.startswith("PFX: pfx.example")


def test_upload_pfx_without_password_works(admin_client: TestClient) -> None:
    pfx = _build_pfx("nopw.example", password=None)
    r = admin_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={
            "pfx_base64": base64.b64encode(pfx).decode("ascii"),
            "password": None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["info"]["subject_cn"] == "nopw.example"


def test_upload_pfx_rejects_wrong_password(admin_client: TestClient) -> None:
    pfx = _build_pfx("pw.example", "correct")
    r = admin_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={
            "pfx_base64": base64.b64encode(pfx).decode("ascii"),
            "password": "incorrect",
        },
    )
    assert r.status_code == 400
    assert "wrong password" in r.json()["detail"].lower()
    assert not CERT_FILE.exists()


def test_upload_pfx_rejects_garbage_base64(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={"pfx_base64": "not_base64!!!!", "password": None},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_base64"


def test_viewer_cannot_upload_pfx(viewer_client: TestClient) -> None:
    pfx = _build_pfx("x.example", password=None)
    r = viewer_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={"pfx_base64": base64.b64encode(pfx).decode("ascii"), "password": None},
    )
    assert r.status_code == 403


async def test_upload_pfx_with_chain_writes_full_chain(
    admin_client: TestClient, async_db_session: AsyncSession
) -> None:
    """Mimic an AD-CS export: leaf + intermediate CA in one PFX."""
    leaf_pem, leaf_key = generate_self_signed("leaf.example", days=30)
    ca_pem, _ca_key = generate_self_signed("intermediate.example", days=30)
    leaf_cert = x509.load_pem_x509_certificate(leaf_pem)
    leaf_priv = serialization.load_pem_private_key(leaf_key, password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_pem)
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=leaf_priv,
        cert=leaf_cert,
        cas=[ca_cert],
        encryption_algorithm=serialization.BestAvailableEncryption(b"x"),
    )
    r = admin_client.post(
        "/api/v1/settings/tls/upload-pfx",
        json={"pfx_base64": base64.b64encode(pfx).decode("ascii"), "password": "x"},
    )
    assert r.status_code == 200, r.text
    on_disk = CERT_FILE.read_bytes()
    # Two BEGIN-CERTIFICATE blocks: leaf + intermediate.
    assert on_disk.count(b"BEGIN CERTIFICATE") == 2


def _assert_volume_perms(_path: Path) -> None:
    # Just used so the file's existence is verified end-to-end; we don't
    # assert specific modes because the test runs as a non-root user
    # without the matching gid.
    pass
