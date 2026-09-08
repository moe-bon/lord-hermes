import time

import pytest

from apexquant_auth.models import TokenClaims
from apexquant_auth.security import (
    AuthSecurityError,
    decode_token_secret,
    generate_api_key,
    hash_api_key_secret,
    parse_api_key,
    sign_token,
    verify_api_key_secret,
    verify_token,
)


def test_token_secret_must_be_32_bytes() -> None:
    import base64

    invalid = base64.b64encode(b"short").decode()

    with pytest.raises(AuthSecurityError):
        decode_token_secret(invalid)


def test_api_key_generation_and_parsing() -> None:
    identifier, secret, full_key = generate_api_key()

    assert full_key == f"{identifier}.{secret}"

    parsed_identifier, parsed_secret = parse_api_key(full_key)

    assert parsed_identifier == identifier
    assert parsed_secret == secret


def test_api_key_hash_and_verify() -> None:
    _, secret, _ = generate_api_key()

    secret_hash = hash_api_key_secret(secret)

    assert verify_api_key_secret(secret_hash, secret) is True
    assert verify_api_key_secret(secret_hash, "wrong-secret") is False


def test_token_roundtrip() -> None:
    secret = b"0" * 32

    now = int(time.time())

    claims = TokenClaims(
        sub="bootstrap-admin",
        typ="ADMIN",
        iat=now,
        exp=now + 300,
        jti="test-jti",
        permissions=["*"],
    )

    token = sign_token(secret, claims)
    context = verify_token(secret, token, now + 1)

    assert context.subject == "bootstrap-admin"
    assert context.principal_type == "ADMIN"
    assert context.permissions == ["*"]


def test_expired_token_is_rejected() -> None:
    secret = b"0" * 32

    now = int(time.time())

    claims = TokenClaims(
        sub="bootstrap-admin",
        typ="ADMIN",
        iat=now - 600,
        exp=now - 300,
        jti="test-jti",
        permissions=["*"],
    )

    token = sign_token(secret, claims)

    with pytest.raises(AuthSecurityError):
        verify_token(secret, token, now)


def test_tampered_token_is_rejected() -> None:
    secret = b"0" * 32

    now = int(time.time())

    claims = TokenClaims(
        sub="bootstrap-admin",
        typ="ADMIN",
        iat=now,
        exp=now + 300,
        jti="test-jti",
        permissions=["*"],
    )

    token = sign_token(secret, claims)

    parts = token.split(".")
    tampered = f"{parts[0]}.{parts[1]}x.{parts[2]}"

    with pytest.raises(AuthSecurityError):
        verify_token(secret, tampered, now)