from __future__ import annotations

import argparse
import json

from apexquant_backup_recovery.bootstrap import build_service
from apexquant_backup_recovery.models import BackupPolicy, TargetSystem
from apexquant_backup_recovery.repository import apply_migrations
from apexquant_backup_recovery.settings import BackupSettings


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from apexquant_backup_recovery.app import create_backup_app

    settings = BackupSettings()
    service = build_service(settings)
    app = create_backup_app(service, settings)

    host, port = settings.http_addr.split(":")

    uvicorn.run(app, host=host, port=int(port), log_level="info")

    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    settings = BackupSettings()

    database_url = args.database_url or settings.database_url

    if not database_url:
        print("database URL is required")
        return 1

    apply_migrations(database_url, settings.migrations_dir)

    print("backup recovery migrations applied")

    return 0


def cmd_create_policy(args: argparse.Namespace) -> int:
    settings = BackupSettings()
    service = build_service(settings)

    policy = BackupPolicy(
        name=args.name,
        target_system=TargetSystem(args.target_system),
        target_name=args.target_name,
        target_connection_ref=args.connection_ref,
        storage_bucket=args.bucket or settings.default_bucket,
        storage_prefix=args.prefix,
        interval_minutes=args.interval_minutes,
        retention_count=args.retention_count,
        retention_days=args.retention_days,
        delete_expired=args.delete_expired,
        enabled=True,
    )

    created = service.create_policy(policy)

    print(created.model_dump_json(indent=2))

    return 0


def cmd_run_policy(args: argparse.Namespace) -> int:
    settings = BackupSettings()
    service = build_service(settings)

    policy = service.get_policy_by_name(args.name)

    if policy is None:
        print(f"policy not found: {args.name}")
        return 1

    run = service.create_backup(policy.policy_id, trigger="manual")

    print(run.model_dump_json(indent=2))

    return 0


def cmd_run_due(args: argparse.Namespace) -> int:
    settings = BackupSettings()
    service = build_service(settings)

    runs = service.run_due()

    print(json.dumps([run.model_dump(mode="json") for run in runs], indent=2, default=str))

    return 0


def cmd_list_policies(args: argparse.Namespace) -> int:
    settings = BackupSettings()
    service = build_service(settings)

    policies = service.list_policies()

    print(json.dumps([policy.model_dump(mode="json") for policy in policies], indent=2, default=str))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-backup-recovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.set_defaults(func=cmd_serve)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", default=None)
    migrate_parser.set_defaults(func=cmd_migrate)

    create_policy_parser = subparsers.add_parser("create-policy")
    create_policy_parser.add_argument("--name", required=True)
    create_policy_parser.add_argument("--target-system", default="POSTGRES")
    create_policy_parser.add_argument("--target-name", required=True)
    create_policy_parser.add_argument("--connection-ref", required=True)
    create_policy_parser.add_argument("--bucket", default=None)
    create_policy_parser.add_argument("--prefix", default="backups/")
    create_policy_parser.add_argument("--interval-minutes", type=int, default=1440)
    create_policy_parser.add_argument("--retention-count", type=int, default=None)
    create_policy_parser.add_argument("--retention-days", type=int, default=None)
    create_policy_parser.add_argument("--delete-expired", action="store_true")
    create_policy_parser.set_defaults(func=cmd_create_policy)

    run_policy_parser = subparsers.add_parser("run-policy")
    run_policy_parser.add_argument("--name", required=True)
    run_policy_parser.set_defaults(func=cmd_run_policy)

    run_due_parser = subparsers.add_parser("run-due")
    run_due_parser.set_defaults(func=cmd_run_due)

    list_policies_parser = subparsers.add_parser("list-policies")
    list_policies_parser.set_defaults(func=cmd_list_policies)

    args = parser.parse_args(argv)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())