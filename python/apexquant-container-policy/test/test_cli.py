from __future__ import annotations

from pathlib import Path

import yaml

from apexquant_container_policy.cli import main


def write_invalid_compose(tmp_path: Path) -> Path:
    compose_path = tmp_path / "docker-compose.yaml"

    document = {
        "services": {
            "bad-service": {
                "image": "apexquant/bad-service:latest",
                "labels": {
                    "apexquant.managed": "true",
                },
            }
        }
    }

    compose_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return compose_path


def test_cli_returns_two_for_missing_file(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--compose",
            str(tmp_path / "does-not-exist.yaml"),
            "--json",
        ]
    )

    assert exit_code == 2


def test_cli_returns_one_for_policy_failure(tmp_path: Path) -> None:
    compose_path = write_invalid_compose(tmp_path)

    exit_code = main(
        [
            "--compose",
            str(compose_path),
            "--json",
        ]
    )

    assert exit_code == 1