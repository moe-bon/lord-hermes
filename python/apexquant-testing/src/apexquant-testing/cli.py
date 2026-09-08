from __future__ import annotations

import argparse
import json
from pathlib import Path

from apexquant_testing.failure_modes import FAILURE_MODES
from apexquant_testing.repository import TestingRepository, apply_migrations
from apexquant_testing.runner import discover_python_packages, git_sha, run_all


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    packages = [Path(package).resolve() for package in args.package]

    if not packages:
        packages = discover_python_packages(root)

    if not packages and not args.rust:
        print("no test packages discovered")
        return 2

    report = run_all(
        python_packages=packages,
        rust_enabled=args.rust,
        rust_crate=args.rust_crate,
        output_dir=args.output_dir,
        environment=args.environment,
        trigger=args.trigger,
        coverage=args.coverage,
    )

    if args.database_url:
        repository = TestingRepository(args.database_url)
        run_id = repository.persist_report(report)

        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "ok": report.ok,
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "skipped": report.skipped,
                    "errors": report.errors,
                    "git_sha": report.git_sha,
                },
                indent=2,
            )
        )
    else:
        print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


def cmd_migrate(args: argparse.Namespace) -> int:
    apply_migrations(args.database_url, args.migrations_dir)
    print("testing migrations applied")
    return 0


def cmd_list_failure_modes(args: argparse.Namespace) -> int:
    print(json.dumps(FAILURE_MODES, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-test-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--root", default=".")
    run_parser.add_argument("--package", action="append", default=[])
    run_parser.add_argument("--rust", action="store_true")
    run_parser.add_argument("--rust-crate", default=None)
    run_parser.add_argument("--output-dir", default="test-results")
    run_parser.add_argument("--environment", default="local")
    run_parser.add_argument("--trigger", default="manual")
    run_parser.add_argument("--coverage", action="store_true")
    run_parser.add_argument("--database-url", default=None)
    run_parser.set_defaults(func=cmd_run)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", required=True)
    migrate_parser.add_argument(
        "--migrations-dir",
        default="migrations/postgres/testing",
    )
    migrate_parser.set_defaults(func=cmd_migrate)

    list_parser = subparsers.add_parser("list-failure-modes")
    list_parser.set_defaults(func=cmd_list_failure_modes)

    args = parser.parse_args(argv)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())