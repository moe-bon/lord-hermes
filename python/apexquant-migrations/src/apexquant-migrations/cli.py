from __future__ import annotations

import argparse
import os
from pathlib import Path

from apexquant_migrations.clickhouse import ClickHouseMigrator
from apexquant_migrations.discovery import create_migration
from apexquant_migrations.models import MigrationEngine
from apexquant_migrations.postgres import PostgresMigrator


def default_root(engine: MigrationEngine) -> str:
    return f"migrations/{engine.value}"


def get_postgres_url(args: argparse.Namespace) -> str:
    database_url = args.database_url or os.environ.get("APEX_POSTGRES_URL")

    if not database_url:
        raise SystemExit("PostgreSQL URL is required")

    return database_url


def get_clickhouse_url(args: argparse.Namespace) -> str:
    clickhouse_url = args.clickhouse_url or os.environ.get("APEX_CLICKHOUSE_URL")

    if not clickhouse_url:
        raise SystemExit("ClickHouse URL is required")

    return clickhouse_url


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", required=True, choices=["postgres", "clickhouse"])
    parser.add_argument("--root", default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--clickhouse-url", default=None)
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--domain", default=None)


def build_migrator(args: argparse.Namespace):
    engine = MigrationEngine(args.engine)

    root = Path(args.root or default_root(engine))

    if engine == MigrationEngine.POSTGRES:
        database_url = get_postgres_url(args)

        return PostgresMigrator(
            database_url=database_url,
            migrations_root=root,
        )

    clickhouse_url = get_clickhouse_url(args)

    return ClickHouseMigrator(
        clickhouse_url=clickhouse_url,
        migrations_root=root,
        postgres_url=args.postgres_url or os.environ.get("APEX_POSTGRES_URL"),
    )


def cmd_status(args: argparse.Namespace) -> int:
    migrator = build_migrator(args)

    plan = migrator.plan(args.domain)

    print(plan.model_dump_json(indent=2))

    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    migrator = build_migrator(args)

    plan = migrator.plan(args.domain)

    print(plan.model_dump_json(indent=2))

    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    migrator = build_migrator(args)

    if not args.dry_run and not args.yes:
        answer = input("Apply migrations? [y/N]: ").strip().lower()

        if answer != "y":
            print("migration apply cancelled")
            return 1

    report = migrator.apply(domain=args.domain, dry_run=args.dry_run)

    print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    migrator = build_migrator(args)

    report = migrator.verify(domain=args.domain)

    print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    migrator = build_migrator(args)

    if args.engine != "postgres":
        print("baseline is currently supported only for postgres")
        return 2

    report = migrator.baseline(domain=args.domain, confirm=args.confirm_baseline)

    print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


def cmd_create(args: argparse.Namespace) -> int:
    engine = MigrationEngine(args.engine)

    root = Path(args.root or default_root(engine))

    path = create_migration(
        root=root,
        engine=engine,
        domain=args.domain,
        slug=args.slug,
    )

    print(str(path))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-migrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    add_common_arguments(status_parser)
    status_parser.set_defaults(func=cmd_status)

    plan_parser = subparsers.add_parser("plan")
    add_common_arguments(plan_parser)
    plan_parser.set_defaults(func=cmd_plan)

    apply_parser = subparsers.add_parser("apply")
    add_common_arguments(apply_parser)
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.add_argument("--yes", action="store_true")
    apply_parser.set_defaults(func=cmd_apply)

    verify_parser = subparsers.add_parser("verify")
    add_common_arguments(verify_parser)
    verify_parser.set_defaults(func=cmd_verify)

    baseline_parser = subparsers.add_parser("baseline")
    add_common_arguments(baseline_parser)
    baseline_parser.add_argument("--confirm-baseline", action="store_true")
    baseline_parser.set_defaults(func=cmd_baseline)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--engine", required=True, choices=["postgres", "clickhouse"])
    create_parser.add_argument("--root", default=None)
    create_parser.add_argument("--domain", required=True)
    create_parser.add_argument("--slug", required=True)
    create_parser.set_defaults(func=cmd_create)

    args = parser.parse_args(argv)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())