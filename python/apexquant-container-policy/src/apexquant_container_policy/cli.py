from __future__ import annotations

import argparse
import os
from pathlib import Path

from apexquant_container_policy.compose import load_compose
from apexquant_container_policy.persistence import persist_report
from apexquant_container_policy.policy import verify_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apexquant-container-policy",
        description="Verify ApexQuant Ultra Docker containerization policy",
    )

    parser.add_argument(
        "--compose",
        required=True,
        help="Path to docker-compose.yaml",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("APEX_CONTAINER_POLICY_DATABASE_URL"),
        help="Optional PostgreSQL DSN used to persist verification reports",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Fail verification when warnings are present",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print the verification report as JSON",
    )

    args = parser.parse_args(argv)

    compose_path = Path(args.compose).resolve()

    if not compose_path.exists():
        print(f"compose file does not exist: {compose_path}")
        return 2

    try:
        document = load_compose(compose_path)
    except ValueError as exc:
        print(f"invalid compose file: {exc}")
        return 2

    report = verify_document(document, strict_warnings=args.strict_warnings)
    report.compose_path = str(compose_path)

    if args.output_json:
        print(report.model_dump_json(indent=2))
    else:
        status = "PASSED" if report.ok else "FAILED"

        print(f"container policy verification {status}")
        print(f"errors={report.errors_count} warnings={report.warnings_count}")

        for violation in report.violations:
            print(
                f"{violation.severity.value} "
                f"{violation.service_name} "
                f"{violation.code}: "
                f"{violation.message}"
            )

    if args.database_url:
        import psycopg

        with psycopg.connect(args.database_url) as connection:
            persist_report(connection, report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())