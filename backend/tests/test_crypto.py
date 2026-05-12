"""Round-trip + edge-case tests for the AES-GCM column-encryption helpers."""

from __future__ import annotations

import secrets

import pytest
from cryptography.exceptions import InvalidTag

from app.core.crypto import KEY_LEN, decrypt, encrypt


def test_round_trip_preserves_unicode() -> None:
    key = secrets.token_bytes(KEY_LEN)
    payload = "Hällo, wörld! 🚀\n\twith newlines"
    assert decrypt(encrypt(payload, key), key) == payload


def test_each_encryption_uses_a_fresh_nonce() -> None:
    key = secrets.token_bytes(KEY_LEN)
    a = encrypt("same plaintext", key)
    b = encrypt("same plaintext", key)
    assert a != b


def test_decrypt_with_wrong_key_raises() -> None:
    key = secrets.token_bytes(KEY_LEN)
    wrong = secrets.token_bytes(KEY_LEN)
    token = encrypt("secret", key)
    with pytest.raises(InvalidTag):
        decrypt(token, wrong)


def test_invalid_key_length_rejected() -> None:
    with pytest.raises(ValueError):
        encrypt("x", b"\x00" * 16)
    with pytest.raises(ValueError):
        decrypt("xxx", b"\x00" * 16)


def test_truncated_ciphertext_rejected() -> None:
    key = secrets.token_bytes(KEY_LEN)
    with pytest.raises(ValueError):
        decrypt("dG9vc2hvcnQ=", key)  # base64("tooshort")
