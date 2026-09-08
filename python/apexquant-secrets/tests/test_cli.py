from __future__ import annotations

import base64
from pathlib import Path

import pytest

from apexquant_secrets.cli import main


@pytest.fixture()
def master_key_env(monkeypatch: pytest.MonkeyPatch) -> str:
    key = base64.b64encode(b"0" * 32).decode()
    monkeypatch.setenv("APEX_MASTER_KEY", key)
    return key


def test_generate_master_key(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["generate-master-key"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert len(base64.b64decode(captured.out.strip())) == 32


def test_secret_lifecycle(
    tmp_path: Path,
    master_key_env: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "store.apexsecrets"
    audit_path = tmp_path / "audit.jsonl"
    value_file = tmp_path / "value.txt"
    value_file.write_text("first-value", encoding="utf-8")

    init_code = main(
        [
            "init-store",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "bootstrap",
            "--subject-plane",
            "CONTROL",
        ]
    )

    assert init_code == 0

    set_code = main(
        [
            "set-secret",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "bootstrap",
            "--subject-plane",
            "CONTROL",
            "--name",
            "broker/test",
            "--classification",
            "BROKER",
            "--value-file",
            str(value_file),
        ]
    )

    assert set_code == 0

    get_code = main(
        [
            "get-secret",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "bootstrap",
            "--subject-plane",
            "CONTROL",
            "--name",
            "broker/test",
            "--reveal",
        ]
    )

    captured = capsys.readouterr()

    assert get_code == 0
    assert captured.out == "first-value"


def test_ai_is_denied_broker_secret(
    tmp_path: Path,
    master_key_env: str,
) -> None:
    store_path = tmp_path / "store.apexsecrets"
    audit_path = tmp_path / "audit.jsonl"
    value_file = tmp_path / "value.txt"
    value_file.write_text("broker-value", encoding="utf-8")

    main(
        [
            "init-store",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "bootstrap",
            "--subject-plane",
            "CONTROL",
        ]
    )

    main(
        [
            "set-secret",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "bootstrap",
            "--subject-plane",
            "CONTROL",
            "--name",
            "broker/test",
            "--classification",
            "BROKER",
            "--value-file",
            str(value_file),
        ]
    )

    denied_code = main(
        [
            "get-secret",
            "--store-path",
            str(store_path),
            "--audit-path",
            str(audit_path),
            "--subject-service",
            "model-serving",
            "--subject-plane",
            "AI",
            "--name",
            "broker/test",
            "--reveal",
        ]
    )

    assert denied_code == 1


def test_scan_env_detects_literal_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BROKER_API_SECRET=hunter2\n", encoding="utf-8")

    exit_code = main(
        [
            "scan-env",
            "--path",
            str(env_file),
        ]
    )

    assert exit_code == 1