from __future__ import annotations

import base64

import pytest

from apexquant_secrets.crypto import (
    CryptoError,
    decrypt_bytes,
    encrypt_bytes,
    generate_master_key_b64,
    master_secret_from_env,
)


def test_generate_master_key_is_32_bytes() -> None:
    key_b64 = generate_master_key_b64()
    key = base64.b64decode(key_b64)

    assert len(key) == 32


def test_encrypt_decrypt_roundtrip() -> None:
    master_secret = b"test-master-secret"
    plaintext = b"secret payload"

    document = encrypt_bytes(plaintext, master_secret)
    decrypted = decrypt_bytes(document, master_secret)

    assert decrypted == plaintext


def test_decrypt_with_wrong_key_fails() -> None:
    document = encrypt_bytes(b"secret payload", b"correct-key")

    with pytest.raises(CryptoError):
        decrypt_bytes(document, b"wrong-key")


def test_master_secret_from_env_requires_key_or_passphrase() -> None:
    with pytest.raises(CryptoError):
        master_secret_from_env({})


def test_master_key_must_be_32_bytes() -> None:
    invalid = base64.b64encode(b"short").decode()

    with pytest.raises(CryptoError):
        master_secret_from_env({"APEX_MASTER_KEY": invalid})