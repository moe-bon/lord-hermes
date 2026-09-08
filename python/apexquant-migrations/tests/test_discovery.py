from pathlib import Path

import pytest

from apexquant_migrations.discovery import (
    MigrationDiscoveryError,
    create_migration,
    discover_migrations,
    next_version,
)
from apexquant_migrations.models import MigrationEngine


def write_migration(root: Path, domain: str, filename: str, sql: str = "SELECT 1;") -> Path:
    domain_dir = root / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    path = domain_dir / filename
    path.write_text(sql, encoding="utf-8")

    return path


def test_discover_migrations_orders_by_domain_and_version(tmp_path: Path) -> None:
    write_migration(tmp_path, "auth", "0002_second.sql")
    write_migration(tmp_path, "auth", "0001_first.sql")
    write_migration(tmp_path, "audit", "0001_first.sql")

    files = discover_migrations(tmp_path, MigrationEngine.POSTGRES)

    assert [file.migration_id for file in files] == [
        "postgres/audit/0001_first.sql",
        "postgres/auth/0001_first.sql",
        "postgres/auth/0002_second.sql",
    ]


def test_discover_rejects_invalid_filename(tmp_path: Path) -> None:
    write_migration(tmp_path, "auth", "bad-name.sql")

    with pytest.raises(MigrationDiscoveryError):
        discover_migrations(tmp_path, MigrationEngine.POSTGRES)


def test_next_version_increments(tmp_path: Path) -> None:
    write_migration(tmp_path, "auth", "0001_first.sql")
    write_migration(tmp_path, "auth", "0002_second.sql")

    files = discover_migrations(tmp_path, MigrationEngine.POSTGRES, domain_filter="auth")

    assert next_version(files) == "0003"


def test_create_migration_writes_noop_file(tmp_path: Path) -> None:
    path = create_migration(
        root=tmp_path,
        engine=MigrationEngine.POSTGRES,
        domain="auth",
        slug="add_table",
    )

    assert path.exists()
    assert path.name == "0001_add_table.sql"

    content = path.read_text(encoding="utf-8")

    assert "BEGIN;" in content
    assert "COMMIT;" in content
    assert "SELECT 1;" in content