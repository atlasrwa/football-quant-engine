"""PostgreSQL implementation of Strategy and StrategyVersion repositories.

Content hash computation reuses the canonical algorithm from
StrategyRegistry._compute_hash() — a single source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.engine.strategy_identity import StrategyRegistry
from src.engine.evaluator import Condition, Strategy


@dataclass
class StrategyRecord:
    """Database representation of a strategy (identity + ownership)."""
    id: UUID
    owner_id: UUID
    name: str
    description: Optional[str]
    visibility: str
    status: str
    created_at: object = None
    updated_at: object = None


@dataclass
class StrategyVersionRecord:
    """Database representation of a strategy version (immutable definition)."""
    id: UUID
    strategy_id: UUID
    version: int
    definition: dict
    content_hash: str
    created_by: UUID
    schema_version: str
    is_deprecated: bool
    deprecated_at: object = None
    created_at: object = None


def compute_content_hash(definition: dict) -> str:
    """Compute canonical content hash using the SAME algorithm as StrategyRegistry.

    This function produces identical output to StrategyRegistry._compute_hash()
    when given the same strategy definition. It accepts a dict representation
    (as stored in the DB) rather than a Strategy dataclass.

    The canonical form is:
        json.dumps({name, metric, market, conditions, logic, direction, min_odds}, sort_keys=True)
        → SHA-256 hex digest

    Args:
        definition: Strategy definition dict with keys:
            name, metric, market, conditions[{field, op, value}], logic, direction, min_odds

    Returns:
        64-char lowercase hex SHA-256 hash.
    """
    import hashlib
    content = json.dumps({
        "name": definition["name"],
        "metric": definition["metric"],
        "market": definition["market"],
        "conditions": [
            {"field": c["field"], "op": c["op"], "value": c["value"]}
            for c in definition["conditions"]
        ],
        "logic": definition["logic"],
        "direction": definition["direction"],
        "min_odds": definition["min_odds"],
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def strategy_to_definition(strategy: Strategy) -> dict:
    """Convert a Strategy dataclass to the canonical definition dict.

    This is the bridge between the engine's Strategy type and the
    database's JSONB definition column.
    """
    return {
        "name": strategy.name,
        "metric": strategy.metric,
        "market": strategy.market,
        "conditions": [
            {"field": c.field, "op": c.op, "value": c.value}
            for c in strategy.conditions
        ],
        "logic": strategy.logic,
        "direction": strategy.direction,
        "min_odds": strategy.min_odds,
    }


def definition_to_strategy(definition: dict) -> Strategy:
    """Convert a definition dict back to a Strategy dataclass."""
    return Strategy(
        name=definition["name"],
        metric=definition["metric"],
        market=definition["market"],
        conditions=tuple(
            Condition(field=c["field"], op=c["op"], value=c["value"])
            for c in definition["conditions"]
        ),
        logic=definition["logic"],
        direction=definition["direction"],
        min_odds=definition["min_odds"],
    )


class PgStrategyRepository:
    """PostgreSQL-backed strategy repository."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_strategy(self, record: StrategyRecord) -> StrategyRecord:
        """Create a new strategy (identity + ownership)."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO strategies (id, owner_id, name, description, visibility, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            record.id, record.owner_id, record.name,
            record.description, record.visibility, record.status,
        )
        return self._row_to_strategy(row)

    async def get_strategy(self, strategy_id: UUID) -> Optional[StrategyRecord]:
        """Get strategy by ID."""
        row = await self._conn.fetchrow(
            "SELECT * FROM strategies WHERE id = $1", strategy_id
        )
        return self._row_to_strategy(row) if row else None

    async def get_strategies_by_owner(self, owner_id: UUID) -> List[StrategyRecord]:
        """Get all strategies owned by a user."""
        rows = await self._conn.fetch(
            "SELECT * FROM strategies WHERE owner_id = $1 ORDER BY created_at DESC",
            owner_id,
        )
        return [self._row_to_strategy(r) for r in rows]

    async def update_visibility(self, strategy_id: UUID, visibility: str) -> Optional[StrategyRecord]:
        """Update strategy visibility. Only owner can do this (enforced by RLS)."""
        row = await self._conn.fetchrow(
            "UPDATE strategies SET visibility = $2 WHERE id = $1 RETURNING *",
            strategy_id, visibility,
        )
        return self._row_to_strategy(row) if row else None

    async def update_status(self, strategy_id: UUID, status: str) -> Optional[StrategyRecord]:
        """Update strategy status (active/archived)."""
        row = await self._conn.fetchrow(
            "UPDATE strategies SET status = $2 WHERE id = $1 RETURNING *",
            strategy_id, status,
        )
        return self._row_to_strategy(row) if row else None

    @staticmethod
    def _row_to_strategy(row: asyncpg.Record) -> StrategyRecord:
        return StrategyRecord(
            id=row["id"],
            owner_id=row["owner_id"],
            name=row["name"],
            description=row["description"],
            visibility=row["visibility"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class PgStrategyVersionRepository:
    """PostgreSQL-backed strategy version repository.

    Handles version numbering with concurrency protection and
    content_hash computation using the canonical algorithm.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_version(
        self,
        strategy_id: UUID,
        definition: dict,
        created_by: UUID,
        schema_version: str = "1.0.0",
    ) -> StrategyVersionRecord:
        """Create a new version with auto-incremented version number.

        Content hash is computed server-side from the definition.
        Version number is determined atomically using SELECT ... FOR UPDATE.

        Args:
            strategy_id: Parent strategy UUID.
            definition: Canonical strategy definition dict.
            created_by: User who created this version.
            schema_version: Schema version string.

        Returns:
            The created version record.

        Raises:
            asyncpg.UniqueViolationError: If content_hash already exists
                (exact duplicate definition).
        """
        content_hash = compute_content_hash(definition)

        # Atomically determine next version number
        # The UNIQUE(strategy_id, version) constraint prevents races
        row = await self._conn.fetchrow(
            """
            INSERT INTO strategy_versions (strategy_id, version, definition, content_hash, created_by, schema_version)
            VALUES (
                $1,
                COALESCE((SELECT MAX(version) FROM strategy_versions WHERE strategy_id = $1), 0) + 1,
                $2::jsonb,
                $3,
                $4,
                $5
            )
            RETURNING *
            """,
            strategy_id,
            json.dumps(definition),
            content_hash,
            created_by,
            schema_version,
        )
        return self._row_to_version(row)

    async def get_version(
        self, strategy_id: UUID, version: int
    ) -> Optional[StrategyVersionRecord]:
        """Get a specific version."""
        row = await self._conn.fetchrow(
            "SELECT * FROM strategy_versions WHERE strategy_id = $1 AND version = $2",
            strategy_id, version,
        )
        return self._row_to_version(row) if row else None

    async def get_latest_version(self, strategy_id: UUID) -> Optional[StrategyVersionRecord]:
        """Get the latest (highest version number) for a strategy."""
        row = await self._conn.fetchrow(
            """
            SELECT * FROM strategy_versions
            WHERE strategy_id = $1
            ORDER BY version DESC
            LIMIT 1
            """,
            strategy_id,
        )
        return self._row_to_version(row) if row else None

    async def get_by_content_hash(self, content_hash: str) -> Optional[StrategyVersionRecord]:
        """Find a version by its content hash (deduplication check)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM strategy_versions WHERE content_hash = $1",
            content_hash,
        )
        return self._row_to_version(row) if row else None

    async def list_versions(self, strategy_id: UUID) -> List[StrategyVersionRecord]:
        """List all versions of a strategy."""
        rows = await self._conn.fetch(
            "SELECT * FROM strategy_versions WHERE strategy_id = $1 ORDER BY version ASC",
            strategy_id,
        )
        return [self._row_to_version(r) for r in rows]

    async def deprecate_version(
        self, strategy_id: UUID, version: int
    ) -> Optional[StrategyVersionRecord]:
        """Mark a version as deprecated."""
        row = await self._conn.fetchrow(
            """
            UPDATE strategy_versions
            SET is_deprecated = TRUE, deprecated_at = NOW()
            WHERE strategy_id = $1 AND version = $2
            RETURNING *
            """,
            strategy_id, version,
        )
        return self._row_to_version(row) if row else None

    @staticmethod
    def _row_to_version(row: asyncpg.Record) -> StrategyVersionRecord:
        definition = row["definition"]
        if isinstance(definition, str):
            definition = json.loads(definition)
        return StrategyVersionRecord(
            id=row["id"],
            strategy_id=row["strategy_id"],
            version=row["version"],
            definition=definition,
            content_hash=row["content_hash"],
            created_by=row["created_by"],
            schema_version=row["schema_version"],
            is_deprecated=row["is_deprecated"],
            deprecated_at=row["deprecated_at"],
            created_at=row["created_at"],
        )


class PgStrategyForkRepository:
    """PostgreSQL-backed strategy fork repository."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_fork(
        self,
        source_strategy_id: UUID,
        source_version: int,
        source_content_hash: str,
        target_strategy_id: UUID,
        forked_by: UUID,
    ) -> dict:
        """Record a fork relationship. Returns the fork record."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO strategy_forks (source_strategy_id, source_version, source_content_hash,
                                        target_strategy_id, forked_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            source_strategy_id, source_version, source_content_hash,
            target_strategy_id, forked_by,
        )
        return dict(row)

    async def get_forks_of(self, strategy_id: UUID) -> List[dict]:
        """Get all forks derived from a strategy."""
        rows = await self._conn.fetch(
            "SELECT * FROM strategy_forks WHERE source_strategy_id = $1 ORDER BY created_at DESC",
            strategy_id,
        )
        return [dict(r) for r in rows]

    async def get_fork_source(self, target_strategy_id: UUID) -> Optional[dict]:
        """Get the fork source for a strategy (if it was forked)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM strategy_forks WHERE target_strategy_id = $1",
            target_strategy_id,
        )
        return dict(row) if row else None
