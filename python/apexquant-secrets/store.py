from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from apexquant_secrets.crypto import decrypt_bytes, encrypt_bytes
from apexquant_secrets.models import (
    SecretClassification,
    SecretEntry,
    SecretMetadata,
    SecretStorePayload,
    SecretVersion,
    SecretVersionStatus,
)

SECRET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,254}$")


class SecretStoreError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_secret_name(name: str) -> None:
    if not SECRET_NAME_PATTERN.match(name):
        raise SecretStoreError(
            "secret name must match ^[a-z0-9][a-z0-9._/-]{0,254}$"
        )


class LocalEncryptedSecretStore:
    def __init__(
        self,
        path: Path,
        master_secret: bytes,
        payload: SecretStorePayload,
    ) -> None:
        self._path = path
        self._master_secret = master_secret
        self._payload = payload

    @classmethod
    def create(
        cls,
        path: Path,
        master_secret: bytes,
    ) -> LocalEncryptedSecretStore:
        if path.exists():
            return cls.load(path, master_secret)

        path.parent.mkdir(parents=True, exist_ok=True)

        store = cls(
            path=path,
            master_secret=master_secret,
            payload=SecretStorePayload(),
        )

        store.save()
        return store

    @classmethod
    def load(
        cls,
        path: Path,
        master_secret: bytes,
    ) -> LocalEncryptedSecretStore:
        if not path.exists():
            raise SecretStoreError(f"secret store does not exist: {path}")

        raw = path.read_text(encoding="utf-8")

        try:
            store_document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecretStoreError("secret store is not valid JSON") from exc

        plaintext = decrypt_bytes(store_document, master_secret)
        payload = SecretStorePayload.model_validate_json(plaintext)

        return cls(
            path=path,
            master_secret=master_secret,
            payload=payload,
        )

    def save(self) -> None:
        plaintext = self._payload.model_dump_json().encode("utf-8")
        store_document = encrypt_bytes(plaintext, self._master_secret)

        self._path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(store_document, indent=2),
            encoding="utf-8",
        )

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, self._path)

    def set_secret(
        self,
        name: str,
        value: str,
        classification: SecretClassification,
        description: str = "",
    ) -> tuple[bool, int]:
        validate_secret_name(name)

        if not value:
            raise SecretStoreError("secret value must not be empty")

        entry = self._payload.secrets.get(name)
        created_new = entry is None

        if entry is None:
            entry = SecretEntry(
                classification=classification,
                description=description,
                current_version=0,
                versions=[],
            )

        for version in entry.versions:
            if version.status == SecretVersionStatus.ACTIVE:
                version.status = SecretVersionStatus.REVOKED

        next_version = entry.current_version + 1

        entry.versions.append(
            SecretVersion(
                version=next_version,
                value=value,
                status=SecretVersionStatus.ACTIVE,
                created_at=utc_now(),
            )
        )

        entry.current_version = next_version
        entry.classification = classification

        if description:
            entry.description = description

        self._payload.secrets[name] = entry
        self.save()

        return created_new, next_version

    def rotate_secret(self, name: str, value: str) -> int:
        validate_secret_name(name)

        entry = self._payload.secrets.get(name)

        if entry is None:
            raise SecretStoreError(f"secret does not exist: {name}")

        if not value:
            raise SecretStoreError("secret value must not be empty")

        for version in entry.versions:
            if version.status == SecretVersionStatus.ACTIVE:
                version.status = SecretVersionStatus.REVOKED

        next_version = entry.current_version + 1

        entry.versions.append(
            SecretVersion(
                version=next_version,
                value=value,
                status=SecretVersionStatus.ACTIVE,
                created_at=utc_now(),
            )
        )

        entry.current_version = next_version
        self._payload.secrets[name] = entry
        self.save()

        return next_version

    def get_secret(self, name: str) -> str:
        validate_secret_name(name)

        entry = self._payload.secrets.get(name)

        if entry is None:
            raise SecretStoreError(f"secret does not exist: {name}")

        for version in entry.versions:
            if (
                version.version == entry.current_version
                and version.status == SecretVersionStatus.ACTIVE
            ):
                return version.value

        raise SecretStoreError(f"secret has no active version: {name}")

    def get_metadata(self, name: str) -> SecretMetadata:
        validate_secret_name(name)

        entry = self._payload.secrets.get(name)

        if entry is None:
            raise SecretStoreError(f"secret does not exist: {name}")

        return SecretMetadata(
            name=name,
            classification=entry.classification,
            description=entry.description,
            current_version=entry.current_version,
        )

    def list_metadata(self) -> list[SecretMetadata]:
        metadata: list[SecretMetadata] = []

        for name in sorted(self._payload.secrets.keys()):
            entry = self._payload.secrets[name]

            metadata.append(
                SecretMetadata(
                    name=name,
                    classification=entry.classification,
                    description=entry.description,
                    current_version=entry.current_version,
                )
            )

        return metadata