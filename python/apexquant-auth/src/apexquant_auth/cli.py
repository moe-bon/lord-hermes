from __future__ import annotations

import argparse
import os

import uvicorn

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-auth")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database-url", default=None)
    migrate_parser.add_argument("--migrations-dir", default=None)

    args = parser.parse_args(argv)

    if args.command == "migrate":
        from apexquant_auth.migrations import apply_migrations

        database_url = args.database_url or os.environ["APEX_AUTH_DATABASE_URL"]
        migrations_dir = (
            args.migrations_dir
            or os.environ.get("APEX_AUTH_MIGRATIONS_DIR", "/migrations/postgres/auth")
        )

        apply_migrations(database_url, migrations_dir)
        return 0

    if args.command == "serve":
        from apexquant_auth.app import create_auth_app

        http_addr = os.environ.get("APEX_HTTP_ADDR", "0.0.0.0:8086")
        default_host, default_port = http_addr.split(":")

        host = args.host or default_host
        port = args.port or int(default_port)

        app = create_auth_app(
            database_url=os.environ["APEX_AUTH_DATABASE_URL"],
            token_secret_b64=os.environ["APEX_AUTH_TOKEN_SECRET"],
            bootstrap_subject=os.environ.get("APEX_AUTH_BOOTSTRAP_CLIENT_ID", "bootstrap-admin"),
            bootstrap_api_key=os.environ["APEX_AUTH_BOOTSTRAP_API_KEY"],
            bootstrap_permissions=os.environ.get("APEX_AUTH_BOOTSTRAP_PERMISSIONS", "*").split(","),
            migrations_dir=os.environ.get(
                "APEX_AUTH_MIGRATIONS_DIR",
                "/migrations/postgres/auth",
            ),
            migrate_on_start=True,
        )

        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())