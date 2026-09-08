from __future__ import annotations

from pathlib import Path

import psycopg


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise FileNotFoundError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise FileNotFoundError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            sql = migration.read_text(encoding="utf-8")
            conn.execute(sql)