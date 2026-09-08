from __future__ import annotations

import argparse
import json

from apexquant_disaster_recovery.bootstrap import build_service
from apexquant_disaster_recovery.repository import apply_migrations
from apexquant_disaster_recovery.settings import DisasterRecoverySettings


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from apexquant_disaster_recovery.app import create_dr_app

    settings = DisasterRecoverySettings()
    service = build_service(settings)
    app = create_dr_app(service)

    host, port = settings.http_addr.split(":")

    uvicorn.run(app, host=host, port=int(port), log_level="info")

    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    settings = DisasterRecoverySettings()

    database_url = args.database_url or settings.database_url

    if not database_url:
        print("database URL is required")
        return 1

    apply_migrations(database_url, settings.migrations_dir)

    print("disaster recovery migrations applied")

    return 0


def cmd_bootstrap_default_plan(args: argparse.Namespace) -> int:
    settings = DisasterRecoverySettings()
    service = build_service(settings)

    plan = service.bootstrap_default_plan(
        environment=settings.environment,
        backup_policy_name=args.backup_policy or settings.default_backup_policy_name,
        actor=args.actor,
    )

    print(plan.model_dump_json(indent=2))

    return 0


def cmd_readiness(args: argparse.Namespace) -> int:
    settings = DisasterRecoverySettings()
    service = build_service(settings)

    plan = service._repository.get_plan_by_name(args.plan_name)

    if plan is None:
        print(f"plan not found: {args.plan_name}")
        return 1

    report = service.readiness(plan.plan_id)

    print(report.model_dump_json(indent=2))

    return 0 if report.state == "READY" else 1


def cmd_run_drill(args: argparse.Namespace) -> int:
    settings = DisasterRecoverySettings()
    service = build_service(settings)

    plan = service._repository.get_plan_by_name(args.plan_name)

    if plan is None:
        print(f"plan not found: {args.plan_name}")
        return 1

    drill = service.run_drill(
        plan.plan_id,
        actor=args.actor,
        trigger=args.trigger,
    )

    print(drill.model_dump_json(indent=2))

    return 0 if drill.status.value == "SUCCEEDED" else 1


def cmd_status(args: argparse.Namespace) -> int:
    settings = DisasterRecoverySettings()
    service = build_service(settings)

    print(json.dumps(service.status(), indent=2, default=str))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-disaster-recovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.set_defaults(func=cmd_serve)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", default=None)
    migrate_parser.set_defaults(func=cmd_migrate)

    bootstrap_parser = subparsers.add_parser("bootstrap-default-plan")
    bootstrap_parser.add_argument("--backup-policy", default=None)
    bootstrap_parser.add_argument("--actor", default="cli")
    bootstrap_parser.set_defaults(func=cmd_bootstrap_default_plan)

    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument("--plan-name", default="platform-disaster-recovery-plan")
    readiness_parser.set_defaults(func=cmd_readiness)

    drill_parser = subparsers.add_parser("run-drill")
    drill_parser.add_argument("--plan-name", default="platform-disaster-recovery-plan")
    drill_parser.add_argument("--actor", default="cli")
    drill_parser.add_argument("--trigger", default="manual")
    drill_parser.set_defaults(func=cmd_run_drill)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())