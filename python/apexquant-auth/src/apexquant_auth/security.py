from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from apexquant_auth.models import AuthContext, TokenClaims

TOKEN_VERSION = "v1"

_password_hasher = PasswordHasher()


class AuthSecurityError(Exception):
    pass


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def decode_token_secret(secret_b64: str) -> bytes:
    secret = base64.b64decode(secret_b64.strip())

    if len(secret) != 32:
        raise AuthSecurityError("token secret must be exactly 32 bytes")

    return secret


def generate_api_key() -> tuple[str, str, str]:
    identifier = b64url_encode(secrets.token_bytes(12))
    secret = b64url_encode(secrets.token_bytes(32))
    full_key = f"{identifier}.{secret}"

    return identifier, secret, full_key


def parse_api_key(api_key: str) -> tuple[str, str]:
    api_key = api_key.strip()

    if not api_key:
        raise AuthSecurityError("API key must not be empty")

    if "." in api_key:
        identifier, secret = api_key.split(".", 1)

        if not identifier or not secret:
            raise AuthSecurityError("invalid API key format")

        return identifier, secret

    return "bootstrap", api_key


def hash_api_key_secret(secret: str) -> str:
    return _password_hasher.hash(secret)


def verify_api_key_secret(secret_hash: str, secret: str) -> bool:
    try:
        return _password_hasher.verify(secret_hash, secret)
    except VerifyMismatchError:
        return False


def sign_token(secret: bytes, claims: TokenClaims) -> str:
    payload = claims.model_dump(mode="json")

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=False)
    payload_b64 = b64url_encode(payload_json.encode("utf-8"))

    signing_input = f"{TOKEN_VERSION}.{payload_b64}".encode("ascii")

    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    signature_b64 = b64url_encode(signature)

    return f"{TOKEN_VERSION}.{payload_b64}.{signature_b64}"


def verify_token(secret: bytes, token: str, now_unix: int) -> AuthContext:
    parts = token.strip().split(".")

    if len(parts) != 3:
        raise AuthSecurityError("invalid token format")

    version, payload_b64, signature_b64 = parts

    if version != TOKEN_VERSION:
        raise AuthSecurityError("unsupported token version")

    signing_input = f"{version}.{payload_b64}".encode("ascii")

    expected_signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    provided_signature = b64url_decode(signature_b64)

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise AuthSecurityError("invalid token signature")

    payload_bytes = b64url_decode(payload_b64)
    payload: dict[str, Any] = json.loads(payload_bytes.decode("utf-8"))

    claims = TokenClaims.model_validate(payload)

    if claims.exp <= now_unix:
        raise AuthSecurityError("token expired")

    return AuthContext(
        subject=claims.sub,
        principal_type=claims.typ,
        permissions=claims.permissions,
        expires_at=claims.exp,
        jti=claims.jti,
    )