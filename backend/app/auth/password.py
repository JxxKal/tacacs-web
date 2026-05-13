"""Argon2id wrapper for the local-admin password (ADR-0003).

`argon2-cffi` has sensible defaults (id, t=3, m=64 MiB, p=4) suitable for a
single-admin login path that gets hit a handful of times a year. We rely
on its built-in verify() to be constant-time and to handle hash-string
versioning, so this module stays a 10-line facade.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("password must not be empty")
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    if not plain or not stored_hash:
        return False
    try:
        _hasher.verify(stored_hash, plain)
    except VerifyMismatchError:
        return False
    return True
