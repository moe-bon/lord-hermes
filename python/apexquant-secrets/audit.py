from __future__ import annotations

import json
from pathlib import Path

from apexquant_secrets.models import AuditEvent


class AuditError(Exception):
    pass


class AuditLogger:
    def __init__(
        self,
        audit_path: Path | None,
        database_url: str | None,
    ) -> None:
        self._audit_path = audit_path
        self._database_url = database_url

    def log(self, event: AuditEvent) -> None:
        persisted = False

        if self._database_url:
            from apexquant_secrets.persistence import persist_audit_event
            import psycopg

            try:
                with psycopg.connect(self._database_url) as connection:
                    persist_audit_event(connection, event)
                    connection.commit()

                persisted = True
            except Exception as exc:
                raise AuditError(
                    "failed writing secret audit event to database"
                ) from exc

        if self._audit_path:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)

            payload = event.model_dump(mode="json")

            try:
                with self._audit_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload) + "\n")

                persisted = True
            except Exception as exc:
                raise AuditError("failed writing secret audit event to file") from exc

        if not persisted:
            raise AuditError(
                "secret access cannot proceed because no audit sink is configured"
            )