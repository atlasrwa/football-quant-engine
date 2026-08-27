"""Repository interfaces for Phase 3.1.

Defines abstract protocols for data access. Concrete implementations
exist for in-memory (testing) and PostgreSQL (production).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable
from uuid import UUID


# ═══════════════════════════════════════════════════════════════════
# DATA TRANSFER OBJECTS (not domain objects — persistence-specific)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class UserRecord:
    """Database representation of a user."""
    id: UUID
    username: str
    email: Optional[str]
    display_name: str
    password_hash: Optional[str]
    role: str
    status: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    primary_wallet_address: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


@dataclass
class EventRecord:
    """Database representation of an audit event."""
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_type: str
    actor_id: Optional[UUID] = None
    payload: dict = field(default_factory=dict)
    correlation_id: Optional[UUID] = None
    causation_id: Optional[int] = None
    event_version: int = 1


# ═══════════════════════════════════════════════════════════════════
# REPOSITORY INTERFACES
# ═══════════════════════════════════════════════════════════════════

@runtime_checkable
class UserRepository(Protocol):
    """Interface for user persistence."""

    async def create(self, user: UserRecord) -> UserRecord:
        """Create a new user. Returns the created record with server-generated fields."""
        ...

    async def get_by_id(self, user_id: UUID) -> Optional[UserRecord]:
        """Find user by primary key."""
        ...

    async def get_by_username(self, username: str) -> Optional[UserRecord]:
        """Find user by username (case-insensitive)."""
        ...

    async def get_by_email(self, email: str) -> Optional[UserRecord]:
        """Find user by email (case-insensitive)."""
        ...

    async def update(self, user_id: UUID, **fields) -> Optional[UserRecord]:
        """Update specific fields on a user record."""
        ...

    async def update_last_login(self, user_id: UUID) -> None:
        """Set last_login_at to now."""
        ...


@runtime_checkable
class EventLogRepository(Protocol):
    """Interface for the append-only event log."""

    async def append(self, event: EventRecord) -> int:
        """Append an event. Returns the assigned event ID."""
        ...

    async def get_by_aggregate(
        self, aggregate_type: str, aggregate_id: str, limit: int = 50
    ) -> List[dict]:
        """Get events for a specific aggregate."""
        ...


@runtime_checkable
class IdempotencyRepository(Protocol):
    """Interface for idempotency key management."""

    async def get(self, user_id: UUID, key: str) -> Optional[dict]:
        """Look up an existing idempotency response. Returns None if not found or expired."""
        ...

    async def store(
        self,
        user_id: UUID,
        key: str,
        endpoint: str,
        http_method: str,
        request_hash: str,
        response_status: int,
        response_body: dict,
    ) -> None:
        """Store an idempotency response. Raises on conflict."""
        ...

    async def cleanup_expired(self) -> int:
        """Remove expired keys. Returns count removed."""
        ...



@runtime_checkable
class MatchRepository(Protocol):
    """Interface for match persistence.

    Adapter pattern: the engine uses Match(id=int) where id is the
    external provider ID. The database uses a surrogate BIGSERIAL match_id.
    Implementations handle the mapping transparently.
    """

    async def upsert(self, match: "Match", external_source: str = "footystats") -> int:
        """Insert or update a match. Returns the surrogate match_id."""
        ...

    async def get_by_external_id(
        self, external_id: int, external_source: str = "footystats"
    ) -> Optional["Match"]:
        """Retrieve a match by its external provider ID."""
        ...

    async def get_surrogate_id(
        self, external_id: int, external_source: str = "footystats"
    ) -> Optional[int]:
        """Look up the internal surrogate match_id for an external ID."""
        ...

    async def list_by_league_season(
        self, league_id: int, season: str, external_source: str = "footystats"
    ) -> List["Match"]:
        """List all matches for a league/season, chronologically ordered."""
        ...


@runtime_checkable
class StrategyRepository(Protocol):
    """Interface for strategy persistence (identity + ownership)."""

    async def create_strategy(self, record: "StrategyRecord") -> "StrategyRecord":
        """Create a new strategy."""
        ...

    async def get_strategy(self, strategy_id: UUID) -> Optional["StrategyRecord"]:
        """Get strategy by ID."""
        ...

    async def get_strategies_by_owner(self, owner_id: UUID) -> List["StrategyRecord"]:
        """Get all strategies owned by a user."""
        ...

    async def update_visibility(self, strategy_id: UUID, visibility: str) -> Optional["StrategyRecord"]:
        """Update strategy visibility."""
        ...


@runtime_checkable
class StrategyVersionRepository(Protocol):
    """Interface for immutable strategy version persistence."""

    async def create_version(
        self, strategy_id: UUID, definition: dict, created_by: UUID
    ) -> "StrategyVersionRecord":
        """Create a new version. Content hash computed server-side."""
        ...

    async def get_version(
        self, strategy_id: UUID, version: int
    ) -> Optional["StrategyVersionRecord"]:
        """Get a specific version."""
        ...

    async def get_latest_version(self, strategy_id: UUID) -> Optional["StrategyVersionRecord"]:
        """Get the latest version."""
        ...

    async def get_by_content_hash(self, content_hash: str) -> Optional["StrategyVersionRecord"]:
        """Find by content hash (deduplication)."""
        ...
