from __future__ import annotations

import argparse

import uvicorn

from apexquant_service_versioning.app import create_service_versioning_app
from apexquant_service_versioning.repository import apply_migrations
from apexquant_service_versioning.settings import ServiceVersioningSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-service-versioning")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", required=True)
    migrate_parser.add_argument(
        "--migrations-dir",
        default="migrations/postgres/service_versioning",
    )

    args = parser.parse_args(argv)

    if args.command == "migrate":
        apply_migrations(args.database_url, args.migrations_dir)
        print("service versioning migrations applied")
        return 0

    if args.command == "serve":
        settings = ServiceVersioningSettings()

        default_host, default_port = settings.http_addr.split(":")

        host = args.host or default_host
        port = args.port or int(default_port)

        app = create_service_versioning_app(settings)

        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())