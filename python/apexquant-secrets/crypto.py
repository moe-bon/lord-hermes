from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

STORE_VERSION = 1
ASSOCIATED_DATA = b"apexquant.ultra.secrets.v1"

DEFAULT_SCRYPT_N = 2**14
DEFAULT_SCRYPT_R = 8
DEFAULT_SCRYPT_P = 1


class CryptoError(Exception):
    pass


def generate_master_key_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def master_secret_from_env(env: dict[str, str]) -> bytes:
    master_key_b64 = env.get("APEX_MASTER_KEY")
    master_passphrase = env.get("APEX_MASTER_PASSPHRASE")

    if master_key_b64:
        try:
            key = base64.b64decode(master_key_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise CryptoError("APEX_MASTER_KEY is not valid base64") from exc

        if len(key) != 32:
            raise CryptoError("APEX_MASTER_KEY must decode to exactly 32 bytes")

        return key

    if master_passphrase:
        if not master_passphrase.strip():
            raise CryptoError("APEX_MASTER_PASSPHRASE must not be empty")

        return master_passphrase.encode("utf-8")

    raise CryptoError(
        "either APEX_MASTER_KEY or APEX_MASTER_PASSPHRASE must be provided"
    )


def derive_key(
    master_secret: bytes,
    salt: bytes,
    n: int = DEFAULT_SCRYPT_N,
    r: int = DEFAULT_SCRYPT_R,
    p: int = DEFAULT_SCRYPT_P,
) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=n,
        r=r,
        p=p,
    )

    return kdf.derive(master_secret)


def key_id_from_key(key: bytes) -> str:
    digest = hashlib.sha256(key).digest()
    return base64.b64encode(digest).decode("ascii")


def encrypt_bytes(
    plaintext: bytes,
    master_secret: bytes,
    salt: bytes | None = None,
    n: int = DEFAULT_SCRYPT_N,
    r: int = DEFAULT_SCRYPT_R,
    p: int = DEFAULT_SCRYPT_P,
) -> dict:
    if salt is None:
        salt = os.urandom(32)

    key = derive_key(master_secret, salt, n=n, r=r, p=p)
    nonce = os.urandom(12)
    cipher = AESGCM(key)
    ciphertext = cipher.encrypt(nonce, plaintext, ASSOCIATED_DATA)

    return {
        "version": STORE_VERSION,
        "kdf": {
            "name": "scrypt",
            "n": n,
            "r": r,
            "p": p,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "key_id": key_id_from_key(key),
        "cipher": {
            "name": "AES-256-GCM",
        },
        "payload": base64.b64encode(nonce + ciphertext).decode("ascii"),
    }


def decrypt_bytes(store_document: dict, master_secret: bytes) -> bytes:
    try:
        version = int(store_document["version"])
        kdf = store_document["kdf"]
        kdf_name = str(kdf["name"])
        n = int(kdf["n"])
        r = int(kdf["r"])
        p = int(kdf["p"])
        salt = base64.b64decode(str(kdf["salt"]), validate=True)
        payload = base64.b64decode(str(store_document["payload"]), validate=True)
    except Exception as exc:
        raise CryptoError("invalid secret store document") from exc

    if version != STORE_VERSION:
        raise CryptoError(f"unsupported secret store version {version}")

    if kdf_name != "scrypt":
        raise CryptoError(f"unsupported KDF {kdf_name}")

    if len(payload) <= 12:
        raise CryptoError("invalid encrypted payload")

    key = derive_key(master_secret, salt, n=n, r=r, p=p)
    nonce = payload[:12]
    ciphertext = payload[12:]

    cipher = AESGCM(key)

    try:
        return cipher.decrypt(nonce, ciphertext, ASSOCIATED_DATA)
    except InvalidTag as exc:
        raise CryptoError("decryption failed: invalid master key or corrupted store") from exc