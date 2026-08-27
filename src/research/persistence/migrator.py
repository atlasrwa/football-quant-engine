"""Database migration runner.

Simple, deterministic, forward-only migrations.
Each migration is a versioned SQL file.
Applied migrations are tracked in research_migrations table.
Idempotent: running multiple times is safe.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import psycopg2

from src.research.persistence.connection import ConnectionManager

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Migrator:
    """Runs database migrations in order."""

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._conn = conn_manager

    def migrate(self) -> int:
        """Run all pending migrations. Returns number applied."""
        self._ensure_migrations_table()
        migrations = self._discover_migrations()
        applied = self._get_applied_versions()

        count = 0
        for version, path in sorted(migrations.items()):
            if version in applied:
                continue
            self._apply_migration(version, path)
            count += 1

        if count:
            logger.info("Applied %d migration(s)", count)
        else:
            logger.info("Database is up to date")
        return count

    def _discover_migrations(self) -> dict[int, Path]:
        """Find all SQL migration files."""
        migrations: dict[int, Path] = {}
        if not _MIGRATIONS_DIR.exists():
            return migrations
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            # Extract version from filename like 001_initial_schema.sql
            try:
                version = int(path.stem.split("_")[0])
                migrations[version] = path
            except (ValueError, IndexError):
                logger.warning("Skipping unversioned migration: %s", path.name)
        return migrations

    def _get_applied_versions(self) -> set[int]:
        """Get already-applied migration versions."""
        try:
            with self._conn.cursor() as cur:
                cur.execute("""
                    SELECT version FROM research_migrations
                """)
                return {row["version"] for row in cur.fetchall()}
        except psycopg2.errors.UndefinedTable:
            # Table doesn't exist yet — no migrations applied
            return set()
        except psycopg2.Error as e:
            logger.error("Failed to query applied migrations: %s", e)
            raise

    def _ensure_migrations_table(self) -> None:
        """Create the research_migrations tracking table if it doesn't exist."""
        with self._conn.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TIMESTAMP DEFAULT NOW()
                    )
                """)

    def _apply_migration(self, version: int, path: Path) -> None:
        """Apply a single migration file and record it."""
        sql = path.read_text()
        logger.info("Applying migration %d: %s", version, path.name)
        with self._conn.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO research_migrations (version, name) VALUES (%s, %s)",
                    (version, path.name),
                )
