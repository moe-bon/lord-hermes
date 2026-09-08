from __future__ import annotations

from pathlib import Path

import pytest

from apexquant_secrets.models import SecretClassification
from apexquant_secrets.store import LocalEncryptedSecretStore, SecretStoreError


def test_store_set_get_rotate(tmp_path: Path) -> None:
    store_path = tmp_path / "store.apexsecrets"
    master_secret = b"master-secret"

    store = LocalEncryptedSecretStore.create(store_path, master_secret)

    created, version = store.set_secret(
        name="broker/test",
        value="first-value",
        classification=SecretClassification.BROKER,
        description="test broker secret",
    )

    assert created is True
    assert version == 1
    assert store.get_secret("broker/test") == "first-value"

    rotated_version = store.rotate_secret("broker/test", "second-value")

    assert rotated_version == 2
    assert store.get_secret("broker/test") == "second-value"

    reloaded = LocalEncryptedSecretStore.load(store_path, master_secret)

    assert reloaded.get_secret("broker/test") == "second-value"


def test_store_rejects_invalid_name(tmp_path: Path) -> None:
    store_path = tmp_path / "store.apexsecrets"
    master_secret = b"master-secret"

    store = LocalEncryptedSecretStore.create(store_path, master_secret)

    with pytest.raises(SecretStoreError):
        store.set_secret(
            name="Invalid Name",
            value="value",
            classification=SecretClassification.API,
        )


def test_store_rejects_empty_value(tmp_path: Path) -> None:
    store_path = tmp_path / "store.apexsecrets"
    master_secret = b"master-secret"

    store = LocalEncryptedSecretStore.create(store_path, master_secret)

    with pytest.raises(SecretStoreError):
        store.set_secret(
            name="api/test",
            value="",
            classification=SecretClassification.API,
        )