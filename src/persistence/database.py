"""Database connection management using asyncpg.

Provides a connection pool and context manager for transactions
with automatic app.user_id/app.user_role session variable injection.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

# Default connection URL — override via FQE_DATABASE_URL env var
_DEFAULT_URL = "postgresql://fqe_app:fqe_dev_password@localhost:5432/football_quant_engine"

_pool: asyncpg.Pool | None = None


def get_database_url() -> str:
    """Get database URL from environment or default."""
    return os.environ.get("FQE_DATABASE_URL", _DEFAULT_URL)


async def init_pool(
    dsn: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Initialize the global connection pool.

    If already initialized, returns existing pool.
    Call close_pool() first if you need to reinitialize.

    Args:
        dsn: PostgreSQL connection string. Defaults to DATABASE_URL env var.
        min_size: Minimum pool connections.
        max_size: Maximum pool connections.

    Returns:
        The initialized pool.
    """
    global _pool
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        dsn=dsn or get_database_url(),
        min_size=min_size,
        max_size=max_size,
    )
    return _pool


async def close_pool() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Get the current connection pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


@asynccontextmanager
async def acquire_connection(
    user_id: str | None = None,
    user_role: str | None = None,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection with app context variables set.

    Sets LOCAL session variables for RLS:
        app.user_id = <user_id>
        app.user_role = <user_role>

    Args:
        user_id: UUID string of the authenticated user.
        user_role: Role string ('user', 'admin', 'system').

    Yields:
        asyncpg.Connection with session context configured.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        if user_id or user_role:
            # Use a transaction so SET LOCAL applies to the connection scope
            async with conn.transaction():
                if user_id:
                    await conn.execute(
                        f"SET LOCAL app.user_id = '{user_id}'"
                    )
                if user_role:
                    await conn.execute(
                        f"SET LOCAL app.user_role = '{user_role}'"
                    )
                yield conn
        else:
            yield conn


@asynccontextmanager
async def transaction(
    user_id: str | None = None,
    user_role: str | None = None,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection within an explicit transaction with RLS context.

    All operations within this context manager are atomic.
    On exception, the transaction is rolled back.

    Args:
        user_id: UUID string of the authenticated user.
        user_role: Role string.

    Yields:
        asyncpg.Connection within a transaction.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if user_id:
                await conn.execute(f"SET LOCAL app.user_id = '{user_id}'")
            if user_role:
                await conn.execute(f"SET LOCAL app.user_role = '{user_role}'")
            yield conn
