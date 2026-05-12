"""AES-GCM column encryption.

Format on disk is base64 of `<12-byte nonce> || <ciphertext+tag>`. The master
key is provided by `app.core.config.settings.master_key()`. See ADR-0004 for
the secrets model.
"""

from __future__ import annotations

import base64
import secrets
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN: Final = 12
KEY_LEN: Final = 32


def encrypt(plaintext: str, key: bytes) -> str:
    if len(key) != KEY_LEN:
        raise ValueError(f"master key must be exactly {KEY_LEN} bytes")
    nonce = secrets.token_bytes(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str, key: bytes) -> str:
    if len(key) != KEY_LEN:
        raise ValueError(f"master key must be exactly {KEY_LEN} bytes")
    raw = base64.b64decode(token)
    if len(raw) < NONCE_LEN + 16:
        raise ValueError("ciphertext too short")
    nonce, ct = raw[:NONCE_LEN], raw[NONCE_LEN:]
    pt = AESGCM(key).decrypt(nonce, ct, associated_data=None)
    return pt.decode("utf-8")
