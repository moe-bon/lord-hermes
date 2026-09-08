from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-tracing-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", required=True)
    migrate_parser.add_argument("--migrations-dir", required=True)

    args = parser.parse_args(argv)

    if args.command == "migrate":
        from apexquant_tracing.core.repository import apply_migrations

        apply_migrations(args.database_url, args.migrations_dir)
        return 0

    if args.command == "serve":
        from apexquant_tracing.core.app import (
            TracingCoreSettings,
            create_tracing_core_app,
        )

        settings = TracingCoreSettings()

        default_host, default_port = settings.http_addr.split(":")

        host = args.host or default_host
        port = args.port or int(default_port)

        app = create_tracing_core_app(settings)

        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())