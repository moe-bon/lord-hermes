from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from apexquant_s3.client import ObjectStorageClient
from apexquant_s3.config import S3Settings
from apexquant_s3.registry import BucketRegistry


def cmd_bootstrap(args: argparse.Namespace) -> int:
    settings = S3Settings(
        endpoint_url=args.endpoint_url,
        access_key_id=args.access_key,
        secret_access_key=args.secret_key,
    )
    client = ObjectStorageClient(settings)
    registry = BucketRegistry(environment=args.environment)

    created = []
    for spec in registry.specs():
        client.ensure_bucket(spec)
        created.append(spec.name)

    if args.database_url:
        import psycopg
        from apexquant_s3.persistence import persist_buckets

        with psycopg.connect(args.database_url) as connection:
            persist_buckets(connection, registry.specs())

    print(json.dumps({"bootstrapped": created}, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    settings = S3Settings(
        endpoint_url=args.endpoint_url,
        access_key_id=args.access_key,
        secret_access_key=args.secret_key,
    )
    client = ObjectStorageClient(settings)
    registry = BucketRegistry(environment=args.environment)

    observed = set(client.list_buckets())
    expected = {spec.name for spec in registry.specs()}
    missing = sorted(expected - observed)

    ok = not missing

    if args.database_url:
        import psycopg
        from apexquant_s3.persistence import persist_verification_report

        with psycopg.connect(args.database_url) as connection:
            persist_verification_report(
                connection,
                environment=args.environment,
                endpoint=args.endpoint_url,
                ok=ok,
                missing_buckets=missing,
                observed_buckets=sorted(observed),
            )

    print(
        json.dumps(
            {
                "ok": ok,
                "missing": missing,
                "observed": sorted(observed),
            },
            indent=2,
        )
    )

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexquant-s3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--endpoint-url", default="http://localhost:9000")
    bootstrap.add_argument("--access-key", default="apex")
    bootstrap.add_argument("--secret-key", default="apexquant-minio")
    bootstrap.add_argument("--environment", default="local")
    bootstrap.add_argument("--database-url", default=None)
    bootstrap.set_defaults(func=cmd_bootstrap)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--endpoint-url", default="http://localhost:9000")
    verify.add_argument("--access-key", default="apex")
    verify.add_argument("--secret-key", default="apexquant-minio")
    verify.add_argument("--environment", default="local")
    verify.add_argument("--database-url", default=None)
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())