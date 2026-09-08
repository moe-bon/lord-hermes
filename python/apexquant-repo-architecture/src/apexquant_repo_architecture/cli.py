from __future__ import annotations

import argparse
import os
from pathlib import Path

from apexquant_repo_architecture.persistence import persist_report
from apexquant_repo_architecture.scanner import scan_repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apexquant-repo-verify",
        description="Verify ApexQuant Ultra repository architecture",
    )

    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the repository root",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("APEX_REPO_DATABASE_URL"),
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

    repo_root = Path(args.repo_root).resolve()

    if not repo_root.exists():
        print(f"repository root does not exist: {repo_root}")
        return 2

    report = scan_repo(repo_root, strict_warnings=args.strict_warnings)

    if args.output_json:
        print(report.model_dump_json(indent=2))
    else:
        status = "PASSED" if report.ok else "FAILED"

        print(f"repository verification {status}")
        print(f"errors={report.errors_count} warnings={report.warnings_count}")

        for violation in report.violations:
            print(
                f"{violation.severity.value} "
                f"{violation.code} "
                f"{violation.path}: "
                f"{violation.message}"
            )

    if args.database_url:
        import psycopg

        with psycopg.connect(args.database_url) as connection:
            persist_report(connection, report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())