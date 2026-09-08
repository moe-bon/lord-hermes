from __future__ import annotations

import argparse
import os

import uvicorn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", default=None)
    migrate_parser.add_argument("--migrations-dir", default=None)

    args = parser.parse_args(argv)

    if args.command == "migrate":
        from apexquant_audit.repository import apply_migrations

        database_url = args.database_url or os.environ["APEX_AUDIT_DATABASE_URL"]
        migrations_dir = (
            args.migrations_dir
            or os.environ.get("APEX_AUDIT_MIGRATIONS_DIR", "/migrations/postgres/audit")
        )

        apply_migrations(database_url, migrations_dir)
        return 0

    if args.command == "serve":
        from apexquant_audit.app import AuditSettings, create_audit_app

        settings = AuditSettings()

        default_host, default_port = settings.http_addr.split(":")

        host = args.host or default_host
        port = args.port or int(default_port)

        app = create_audit_app(settings)

        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())