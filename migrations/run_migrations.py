"""Simple migration runner for Phase 3.1.

Executes SQL migration files in order, tracking which have been applied
in a _migrations table. Safe to run repeatedly (idempotent).

Usage:
    python migrations/run_migrations.py
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

DATABASE_URL = "postgresql://fqe_app:fqe_dev_password@localhost:5432/football_quant_engine"
MIGRATIONS_DIR = Path(__file__).parent


async def run():
    conn = await asyncpg.connect(DATABASE_URL)

    # Create migrations tracking table
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Get already-applied migrations
    applied = set(
        row["filename"]
        for row in await conn.fetch("SELECT filename FROM _migrations ORDER BY id")
    )

    # Find and sort migration files
    migration_files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql")
        if f.name[0].isdigit()
    )

    applied_count = 0
    for mf in migration_files:
        if mf.name in applied:
            print(f"  SKIP  {mf.name} (already applied)")
            continue

        print(f"  APPLY {mf.name} ...", end=" ")
        sql = mf.read_text()
        try:
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migrations (filename) VALUES ($1)", mf.name
            )
            print("OK")
            applied_count += 1
        except Exception as e:
            print(f"FAILED: {e}")
            await conn.close()
            sys.exit(1)

    await conn.close()
    print(f"\nDone. {applied_count} migration(s) applied, {len(applied)} already up-to-date.")


if __name__ == "__main__":
    print("Running migrations...")
    asyncio.run(run())
