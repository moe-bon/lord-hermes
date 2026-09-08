from __future__ import annotations

import argparse
import json
from pathlib import Path

from apexquant_env_config.loader import load_manifest
from apexquant_env_config.persistence import (
    persist_validation_report,
    register_environment,
)
from apexquant_env_config.validator import validate_environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apexquant-env-config",
        description="Verify ApexQuant Ultra environment configuration",
    )

    parser.add_argument(
        "--environments-root",
        required=True,
        help="Root directory containing environment subdirectories",
    )
    parser.add_argument(
        "--environment",
        required=False,
        help="Environment directory name to validate",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="validate_all",
        help="Validate all environments under the environments root",
    )
    parser.add_argument(
        "--check-process-env",
        action="store_true",
        help="Verify required environment variables in the current process",
    )
    parser.add_argument(
        "--database-url",
        required=False,
        help="Optional PostgreSQL DSN used to persist environment metadata",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print validation reports as JSON",
    )

    args = parser.parse_args(argv)

    environments_root = Path(args.environments_root).resolve()

    if not environments_root.exists():
        print(f"environments root does not exist: {environments_root}")
        return 2

    if args.validate_all:
        environment_names = sorted(
            path.name
            for path in environments_root.iterdir()
            if path.is_dir() and (path / "environment.yaml").exists()
        )
    else:
        if not args.environment:
            print("either --environment or --all is required")
            return 2

        environment_names = [args.environment]

    if not environment_names:
        print(f"no environments found under {environments_root}")
        return 2

    reports = []

    for environment_name in environment_names:
        report = validate_environment(
            environments_root=environments_root,
            environment=environment_name,
            check_process_env=args.check_process_env,
        )

        reports.append(report)

        if args.database_url:
            import psycopg

            with psycopg.connect(args.database_url) as connection:
                persist_validation_report(connection, report)

                if report.ok:
                    manifest_path = Path(report.manifest_path)
                    manifest = load_manifest(manifest_path)
                    register_environment(connection, manifest)

    if args.output_json:
        payload = [json.loads(report.model_dump_json()) for report in reports]
        print(json.dumps(payload, indent=2))
    else:
        for report in reports:
            status = "PASSED" if report.ok else "FAILED"

            print(
                f"environment={report.environment} "
                f"status={status} "
                f"errors={report.errors_count} "
                f"warnings={report.warnings_count}"
            )

            for violation in report.violations:
                location = f" path={violation.path}" if violation.path else ""

                print(
                    f"  {violation.severity.value} "
                    f"{violation.code}{location}: "
                    f"{violation.message}"
                )

    return 0 if all(report.ok for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())