"""`tacacs-web` CLI entry point.

Subcommands:
- `bootstrap-admin` — create or replace the single local-admin row
  (ADR-0003). The UI does not expose a way to do this; the operator runs
  the CLI inside the backend container (`docker compose exec backend
  tacacs-web bootstrap-admin`).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import LOCAL_ADMIN_BOOTSTRAPPED, LOCAL_ADMIN_PASSWORD_RESET
from app.audit.logger import append as audit_append
from app.auth.password import hash_password
from app.db.models import LocalAdmin
from app.db.session import SessionLocal


async def _bootstrap_admin(
    username: str, password: str, *, reset_password: bool
) -> int:
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(LocalAdmin).where(LocalAdmin.id == 1))
        ).scalar_one_or_none()
        if existing is None:
            row = LocalAdmin(
                id=1,
                username=username,
                password_argon2_hash=hash_password(password),
            )
            session.add(row)
            await session.commit()
            await _audit(session, LOCAL_ADMIN_BOOTSTRAPPED, username, "initial setup")
            print(f"local admin {username!r} created")
            return 0

        if not reset_password:
            print(
                f"local admin {existing.username!r} already exists. "
                "Re-run with --reset-password to replace the password.",
                file=sys.stderr,
            )
            return 1

        existing.username = username
        existing.password_argon2_hash = hash_password(password)
        await session.commit()
        await _audit(
            session, LOCAL_ADMIN_PASSWORD_RESET, username, "password reset via CLI"
        )
        print(f"local admin {username!r} password reset")
        return 0


async def _audit(
    session: AsyncSession, action: str, username: str, summary: str
) -> None:
    await audit_append(
        session,
        actor_username_snapshot=username,
        actor_role="admin",
        auth_method="local",
        action=action,
        target_type="local_admin",
        target_id=1,
        summary=summary,
        ts=datetime.now(UTC),
        client_ip=None,
        user_agent="cli",
        actor_id=1,
    )
    await session.commit()


def _read_password(arg_value: str | None) -> str:
    if arg_value:
        print(
            "WARN: passing --password via argv leaks it into process listings + shell history",
            file=sys.stderr,
        )
        return arg_value
    pw = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm:      ")
    if pw != confirm:
        raise SystemExit("passwords do not match")
    return pw


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tacacs-web")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser(
        "bootstrap-admin",
        help="Create the single local-admin row, or rotate its password.",
    )
    boot.add_argument("--username", default="admin", help="default: admin")
    boot.add_argument(
        "--password",
        help="set the password from the command line (avoid in interactive use)",
    )
    boot.add_argument(
        "--reset-password",
        action="store_true",
        help="replace the password of the existing local admin",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> NoReturn:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "bootstrap-admin":
        password = _read_password(args.password)
        rc = asyncio.run(
            _bootstrap_admin(
                username=args.username,
                password=password,
                reset_password=args.reset_password,
            )
        )
        sys.exit(rc)
    sys.exit(1)


if __name__ == "__main__":
    main()
