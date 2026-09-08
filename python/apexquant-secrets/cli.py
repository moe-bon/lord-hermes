from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apexquant_secrets.audit import AuditLogger
from apexquant_secrets.crypto import CryptoError, generate_master_key_b64, master_secret_from_env
from apexquant_secrets.models import (
    AuditEvent,
    PolicyEffect,
    SecretAction,
    SecretClassification,
    SecretPlane,
)
from apexquant_secrets.policy import evaluate_access
from apexquant_secrets.scanning import scan_env_file
from apexquant_secrets.store import LocalEncryptedSecretStore, SecretStoreError


def add_common_store_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store-path",
        default=os.environ.get(
            "APEX_SECRETS_STORE_PATH",
            "infra/security/secrets/local.apexsecrets",
        ),
    )
    parser.add_argument(
        "--audit-path",
        default=os.environ.get(
            "APEX_SECRETS_AUDIT_PATH",
            "infra/security/audit/secrets-audit.jsonl",
        ),
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("APEX_SECRETS_DATABASE_URL"),
    )


def add_subject_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject-service", required=True)
    parser.add_argument(
        "--subject-plane",
        required=True,
        choices=[plane.value for plane in SecretPlane],
    )


def read_value(args: argparse.Namespace) -> str:
    if getattr(args, "value_stdin", False):
        value = sys.stdin.read().strip()

        if not value:
            raise ValueError("secret value from stdin must not be empty")

        return value

    value_file = getattr(args, "value_file", None)

    if value_file:
        path = Path(value_file)

        if not path.exists():
            raise ValueError(f"value file does not exist: {path}")

        value = path.read_text(encoding="utf-8").strip()

        if not value:
            raise ValueError(f"value file must not be empty: {path}")

        return value

    raise ValueError("either --value-stdin or --value-file is required")


def build_audit_event(
    args: argparse.Namespace,
    secret_name: str,
    action: SecretAction,
    decision: PolicyEffect,
    reason: str,
) -> AuditEvent:
    return AuditEvent(
        occurred_at=datetime.now(timezone.utc),
        request_id=str(uuid.uuid4()),
        subject_service_name=args.subject_service,
        subject_plane=SecretPlane(args.subject_plane),
        secret_name=secret_name,
        action=action,
        decision=decision,
        reason=reason,
    )


def load_store(args: argparse.Namespace) -> LocalEncryptedSecretStore:
    try:
        master_secret = master_secret_from_env(dict(os.environ))
    except CryptoError as exc:
        raise SystemExit(f"master key error: {exc}")

    store_path = Path(args.store_path)

    try:
        return LocalEncryptedSecretStore.load(store_path, master_secret)
    except SecretStoreError as exc:
        raise SystemExit(f"secret store error: {exc}")
    except CryptoError as exc:
        raise SystemExit(f"secret store decryption error: {exc}")


def audit_or_exit(args: argparse.Namespace, event: AuditEvent) -> None:
    logger = AuditLogger(
        audit_path=Path(args.audit_path) if args.audit_path else None,
        database_url=args.database_url,
    )

    try:
        logger.log(event)
    except Exception as exc:
        raise SystemExit(f"secret audit failure: {exc}")


def cmd_generate_master_key(args: argparse.Namespace) -> int:
    print(generate_master_key_b64())
    return 0


def cmd_init_store(args: argparse.Namespace) -> int:
    try:
        master_secret = master_secret_from_env(dict(os.environ))
    except CryptoError as exc:
        raise SystemExit(f"master key error: {exc}")

    store_path = Path(args.store_path)

    try:
        LocalEncryptedSecretStore.create(store_path, master_secret)
    except SecretStoreError as exc:
        raise SystemExit(f"secret store error: {exc}")

    audit_or_exit(
        args,
        build_audit_event(
            args,
            secret_name="<store>",
            action=SecretAction.ADMIN,
            decision=PolicyEffect.ALLOW,
            reason="secret store initialized",
        ),
    )

    print(json.dumps({"initialized": True, "store_path": str(store_path)}))
    return 0


def cmd_set_secret(args: argparse.Namespace) -> int:
    store = load_store(args)

    try:
        value = read_value(args)
    except ValueError as exc:
        raise SystemExit(str(exc))

    classification = SecretClassification(args.classification)

    exists = args.name in store._payload.secrets
    action = SecretAction.ROTATE if exists else SecretAction.WRITE

    evaluation = evaluate_access(
        SecretPlane(args.subject_plane),
        classification,
        action,
    )

    audit_or_exit(
        args,
        build_audit_event(
            args,
            secret_name=args.name,
            action=action,
            decision=PolicyEffect.ALLOW if evaluation.allowed else PolicyEffect.DENY,
            reason=evaluation.reason,
        ),
    )

    if not evaluation.allowed:
        print(json.dumps({"allowed": False, "reason": evaluation.reason}))
        return 1

    try:
        created_new, version = store.set_secret(
            name=args.name,
            value=value,
            classification=classification,
            description=args.description,
        )
    except SecretStoreError as exc:
        raise SystemExit(f"secret store error: {exc}")

    if args.database_url:
        import psycopg
        from apexquant_secrets.persistence import (
            persist_secret_metadata,
            persist_secret_version,
        )

        with psycopg.connect(args.database_url) as connection:
            persist_secret_metadata(
                connection,
                args.name,
                classification,
                args.description,
                version,
            )
            persist_secret_version(connection, args.name, version)

    print(
        json.dumps(
            {
                "created": created_new,
                "name": args.name,
                "classification": classification.value,
                "version": version,
            }
        )
    )

    return 0


def cmd_rotate_secret(args: argparse.Namespace) -> int:
    store = load_store(args)

    try:
        value = read_value(args)
    except ValueError as exc:
        raise SystemExit(str(exc))

    try:
        metadata = store.get_metadata(args.name)
    except SecretStoreError as exc:
        raise SystemExit(str(exc))

    evaluation = evaluate_access(
        SecretPlane(args.subject_plane),
        metadata.classification,
        SecretAction.ROTATE,
    )

    audit_or_exit(
        args,
        build_audit_event(
            args,
            secret_name=args.name,
            action=SecretAction.ROTATE,
            decision=PolicyEffect.ALLOW if evaluation.allowed else PolicyEffect.DENY,
            reason=evaluation.reason,
        ),
    )

    if not evaluation.allowed:
        print(json.dumps({"allowed": False, "reason": evaluation.reason}))
        return 1

    try:
        version = store.rotate_secret(args.name, value)
    except SecretStoreError as exc:
        raise SystemExit(f"secret store error: {exc}")

    if args.database_url:
        import psycopg
        from apexquant_secrets.persistence import (
            persist_secret_metadata,
            persist_secret_version,
        )

        with psycopg.connect(args.database_url) as connection:
            persist_secret_metadata(
                connection,
                args.name,
                metadata.classification,
                metadata.description,
                version,
            )
            persist_secret_version(connection, args.name, version)

    print(
        json.dumps(
            {
                "name": args.name,
                "classification": metadata.classification.value,
                "version": version,
            }
        )
    )

    return 0


def cmd_get_secret(args: argparse.Namespace) -> int:
    store = load_store(args)

    try:
        metadata = store.get_metadata(args.name)
    except SecretStoreError as exc:
        raise SystemExit(str(exc))

    evaluation = evaluate_access(
        SecretPlane(args.subject_plane),
        metadata.classification,
        SecretAction.READ,
    )

    audit_or_exit(
        args,
        build_audit_event(
            args,
            secret_name=args.name,
            action=SecretAction.READ,
            decision=PolicyEffect.ALLOW if evaluation.allowed else PolicyEffect.DENY,
            reason=evaluation.reason,
        ),
    )

    if not evaluation.allowed:
        print(json.dumps({"allowed": False, "reason": evaluation.reason}))
        return 1

    if not args.reveal:
        print(
            json.dumps(
                {
                    "name": metadata.name,
                    "classification": metadata.classification.value,
                    "description": metadata.description,
                    "current_version": metadata.current_version,
                }
            )
        )
        return 0

    try:
        value = store.get_secret(args.name)
    except SecretStoreError as exc:
        raise SystemExit(str(exc))

    sys.stdout.write(value)
    return 0


def cmd_list_secrets(args: argparse.Namespace) -> int:
    store = load_store(args)

    evaluation = evaluate_access(
        SecretPlane(args.subject_plane),
        SecretClassification.INFRASTRUCTURE,
        SecretAction.READ,
    )

    audit_or_exit(
        args,
        build_audit_event(
            args,
            secret_name="<metadata>",
            action=SecretAction.READ,
            decision=PolicyEffect.ALLOW if evaluation.allowed else PolicyEffect.DENY,
            reason=evaluation.reason,
        ),
    )

    if not evaluation.allowed:
        print(json.dumps({"allowed": False, "reason": evaluation.reason}))
        return 1

    metadata = store.list_metadata()

    print(
        json.dumps(
            [
                {
                    "name": item.name,
                    "classification": item.classification.value,
                    "description": item.description,
                    "current_version": item.current_version,
                }
                for item in metadata
            ],
            indent=2,
        )
    )

    return 0


def cmd_evaluate_access(args: argparse.Namespace) -> int:
    evaluation = evaluate_access(
        SecretPlane(args.subject_plane),
        SecretClassification(args.classification),
        SecretAction(args.action),
    )

    print(
        json.dumps(
            {
                "allowed": evaluation.allowed,
                "reason": evaluation.reason,
            }
        )
    )

    return 0 if evaluation.allowed else 1


def cmd_scan_env(args: argparse.Namespace) -> int:
    path = Path(args.path)

    if not path.exists():
        print(f"file does not exist: {path}")
        return 2

    violations = scan_env_file(path, allow_examples=args.allow_examples)

    if violations:
        for violation in violations:
            print(str(violation))

        return 1

    print(json.dumps({"ok": True, "path": str(path)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apexquant-secrets",
        description="ApexQuant Ultra secrets and key management foundation",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate-master-key")
    generate_parser.set_defaults(func=cmd_generate_master_key)

    init_parser = subparsers.add_parser("init-store")
    add_common_store_arguments(init_parser)
    add_subject_arguments(init_parser)
    init_parser.set_defaults(func=cmd_init_store)

    set_parser = subparsers.add_parser("set-secret")
    add_common_store_arguments(set_parser)
    add_subject_arguments(set_parser)
    set_parser.add_argument("--name", required=True)
    set_parser.add_argument(
        "--classification",
        required=True,
        choices=[classification.value for classification in SecretClassification],
    )
    set_parser.add_argument("--description", default="")
    set_parser.add_argument("--value-stdin", action="store_true")
    set_parser.add_argument("--value-file")
    set_parser.set_defaults(func=cmd_set_secret)

    rotate_parser = subparsers.add_parser("rotate-secret")
    add_common_store_arguments(rotate_parser)
    add_subject_arguments(rotate_parser)
    rotate_parser.add_argument("--name", required=True)
    rotate_parser.add_argument("--value-stdin", action="store_true")
    rotate_parser.add_argument("--value-file")
    rotate_parser.set_defaults(func=cmd_rotate_secret)

    get_parser = subparsers.add_parser("get-secret")
    add_common_store_arguments(get_parser)
    add_subject_arguments(get_parser)
    get_parser.add_argument("--name", required=True)
    get_parser.add_argument("--reveal", action="store_true")
    get_parser.set_defaults(func=cmd_get_secret)

    list_parser = subparsers.add_parser("list-secrets")
    add_common_store_arguments(list_parser)
    add_subject_arguments(list_parser)
    list_parser.set_defaults(func=cmd_list_secrets)

    evaluate_parser = subparsers.add_parser("evaluate-access")
    evaluate_parser.add_argument("--subject-plane", required=True, choices=[plane.value for plane in SecretPlane])
    evaluate_parser.add_argument(
        "--classification",
        required=True,
        choices=[classification.value for classification in SecretClassification],
    )
    evaluate_parser.add_argument(
        "--action",
        required=True,
        choices=[action.value for action in SecretAction],
    )
    evaluate_parser.set_defaults(func=cmd_evaluate_access)

    scan_parser = subparsers.add_parser("scan-env")
    scan_parser.add_argument("--path", required=True)
    scan_parser.add_argument("--allow-examples", action="store_true")
    scan_parser.set_defaults(func=cmd_scan_env)

    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except SystemExit as exc:
        print(str(exc))
        return int(exc.code) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())