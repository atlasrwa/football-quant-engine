"""Integration test fixtures for Phase 3.1 database tests.

Provides a real PostgreSQL connection for integration testing.
Tests are wrapped in transactions that are rolled back after each test.
"""

import json
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

DATABASE_URL = "postgresql://fqe_app:fqe_dev_password@localhost:5432/football_quant_engine"


async def _setup_json_codec(conn: asyncpg.Connection) -> None:
    """Register JSON codec so JSONB columns are auto-decoded."""
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


@pytest_asyncio.fixture
async def db_conn():
    """Provide a database connection within a transaction that rolls back.

    This ensures tests do not persist data between runs.
    """
    conn = await asyncpg.connect(DATABASE_URL)
    await _setup_json_codec(conn)

    # Start a savepoint that we will ROLLBACK at teardown
    # (Using a savepoint within a transaction allows codec to work)
    await conn.execute("BEGIN")
    await conn.execute("SET LOCAL app.user_id = '00000000-0000-0000-0000-000000000001'")
    await conn.execute("SET LOCAL app.user_role = 'system'")

    yield conn

    await conn.execute("ROLLBACK")
    await conn.close()


@pytest.fixture
def system_user_id() -> UUID:
    """The deterministic system user UUID."""
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def random_user_id() -> UUID:
    """A random UUID for test user creation."""
    return uuid4()
