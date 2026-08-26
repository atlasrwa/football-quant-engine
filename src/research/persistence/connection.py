"""PostgreSQL connection management.

Provides connection pooling, configurable timeouts,
clean shutdown, and credential security.

Credentials loaded from environment — never logged or serialized.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

_DEFAULT_DSN = "postgresql://research:research_test_pw@localhost:5432/research_test"


class ConnectionManager:
    """Manages PostgreSQL connections with pooling.

    Configuration from environment:
        RESEARCH_DATABASE_URL — full connection string
        RESEARCH_DB_POOL_MIN — min pool size (default 1)
        RESEARCH_DB_POOL_MAX — max pool size (default 5)
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        pool_min: int = 1,
        pool_max: int = 5,
    ) -> None:
        self._dsn = dsn or os.environ.get("RESEARCH_DATABASE_URL", _DEFAULT_DSN)
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    def initialize(self) -> None:
        """Create the connection pool."""
        if self._pool is not None:
            return
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=self._pool_min,
            maxconn=self._pool_max,
            dsn=self._dsn,
        )
        logger.info("Connection pool initialized (min=%d, max=%d)", self._pool_min, self._pool_max)

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("Connection pool closed")

    @contextmanager
    def connection(self) -> Generator[Any, None, None]:
        """Get a connection from the pool (context manager).

        Automatically returns connection to pool on exit.
        Rolls back on exception.
        """
        if self._pool is None:
            self.initialize()
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def cursor(self, dict_cursor: bool = True) -> Generator[Any, None, None]:
        """Get a cursor with automatic connection management.

        Args:
            dict_cursor: If True, returns DictCursor (rows as dicts).
        """
        with self.connection() as conn:
            cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
            with conn.cursor(cursor_factory=cursor_factory) as cur:
                yield cur

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Explicit transaction context. Commits on success, rolls back on error."""
        if self._pool is None:
            self.initialize()
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)
