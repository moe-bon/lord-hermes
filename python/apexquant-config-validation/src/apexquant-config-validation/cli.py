from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from apexquant_config_validation.validator import ConfigValidator


def load_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        return json.loads(text)

    return yaml.safe_load(text)


def cmd_validate(args: argparse.Namespace) -> int:
    validator = ConfigValidator()

    document = load_document(Path(args.file))

    report = validator.validate(args.schema, document)

    print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


def cmd_validate_all(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    validator = ConfigValidator()

    failed = False

    for path in sorted(root.rglob("*.yaml")):
        try:
            document = load_document(path)
        except Exception as exc:
            print(f"FAIL {path}: unable to parse: {exc}")
            failed = True
            continue

        if not isinstance(document, dict):
            print(f"FAIL {path}: document root must be a mapping")
            failed = True
            continue

        schema_key = document.get("schema_version")

        if schema_key is None:
            print(f"SKIP {path}: missing schema_version")
            continue

        report = validator.validate(schema_key, document)

        status = "PASS" if report.ok else "FAIL"

        print(f"{status} {path}")

        if not report.ok:
            failed = True

            for issue in report.errors:
                print(f"  ERROR {issue.path}: {issue.message}")

        for issue in report.warnings:
            print(f"  WARNING {issue.path}: {issue.message}")

    for path in sorted(root.rglob("*.json")):
        try:
            document = load_document(path)
        except Exception as exc:
            print(f"FAIL {path}: unable to parse: {exc}")
            failed = True
            continue

        if not isinstance(document, dict):
            print(f"FAIL {path}: document root must be a mapping")
            failed = True
            continue

        schema_key = document.get("schema_version")

        if schema_key is None:
            print(f"SKIP {path}: missing schema_version")
            continue

        report = validator.validate(schema_key, document)

        status = "PASS" if report.ok else "FAIL"

        print(f"{status} {path}")

        if not report.ok:
            failed = True

            for issue in report.errors:
                print(f"  ERROR {issue.path}: {issue.message}")

        for issue in report.warnings:
            print(f"  WARNING {issue.path}: {issue.message}")

    return 1 if failed else 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from apexquant_config_validation.app import (
        ConfigValidationSettings,
        create_config_validation_app,
    )

    settings = ConfigValidationSettings()

    host, port = settings.http_addr.split(":")

    uvicorn.run(
        create_config_validation_app(settings),
        host=host,
        port=int(port),
        log_level="info",
    )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-config")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--schema", required=True)
    validate_parser.add_argument("--file", required=True)
    validate_parser.set_defaults(func=cmd_validate)

    validate_all_parser = subparsers.add_parser("validate-all")
    validate_all_parser.add_argument("--root", default="config")
    validate_all_parser.set_defaults(func=cmd_validate_all)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())