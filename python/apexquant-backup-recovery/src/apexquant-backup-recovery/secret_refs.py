from __future__ import annotations

import os

from apexquant_backup_recovery.errors import ConnectionReferenceError


def resolve_connection_ref(reference: str) -> str:
    if reference.startswith("env://"):
        env_name = reference.removeprefix("env://")

        value = os.environ.get(env_name)

        if not value:
            raise ConnectionReferenceError(
                f"environment variable referenced by {reference} is not set"
            )

        return value

    if reference.startswith("vault://"):
        raise ConnectionReferenceError(
            "vault:// connection references are not configured in this environment"
        )

    if reference.startswith("secret://"):
        raise ConnectionReferenceError(
            "secret:// connection references are not configured in this environment"
        )

    raise ConnectionReferenceError(
        "connection references must use env://, vault://, or secret://"
    )