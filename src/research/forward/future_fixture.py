"""Future Fixture Model — represents upcoming matches for forward research.

Identity:
    Fixture identity is deterministic based on (source, source_fixture_id).
    Team names are metadata, NOT identity.
    Retrieval timestamp does NOT affect identity.
    Same fixture retrieved multiple times → same fixture.

Lifecycle:
    SCHEDULED → STARTED → COMPLETED
    SCHEDULED → POSTPONED
    SCHEDULED → CANCELLED

Immutability:
    FutureFixture is a frozen dataclass. Status transitions
    produce NEW instances via replace().
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional


class FixtureStatus(Enum):
    """Fixture lifecycle states."""
    SCHEDULED = "SCHEDULED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"


# Valid fixture state transitions
_FIXTURE_TRANSITIONS: dict[FixtureStatus, set[FixtureStatus]] = {
    FixtureStatus.SCHEDULED: {FixtureStatus.STARTED, FixtureStatus.POSTPONED, FixtureStatus.CANCELLED},
    FixtureStatus.POSTPONED: {FixtureStatus.SCHEDULED, FixtureStatus.CANCELLED},
    FixtureStatus.CANCELLED: set(),  # Terminal
    FixtureStatus.STARTED: {FixtureStatus.COMPLETED},
    FixtureStatus.COMPLETED: set(),  # Terminal
}


@dataclass(frozen=True)
class FutureFixture:
    """Immutable representation of a future/upcoming match.

    Identity is based on (source, source_fixture_id) — NOT team names,
    NOT retrieval time, NOT kickoff time (which may shift for postponed fixtures).

    Attributes:
        fixture_id: Deterministic content hash identity.
        source_fixture_id: Provider-specific fixture identifier (e.g., FootyStats match ID).
        home_team_id: Stable team identifier (provider-specific numeric ID preferred).
        away_team_id: Stable team identifier.
        home_team_name: Human-readable team name (metadata, not identity).
        away_team_name: Human-readable team name (metadata, not identity).
        competition_id: League/competition identifier.
        season_id: Season identifier.
        kickoff_timestamp: Scheduled kickoff as Unix timestamp.
        source: Data source identifier (e.g., "footystats", "test").
        retrieved_at: When this fixture data was retrieved (not used for identity).
        status: Current fixture lifecycle status.
    """
    source_fixture_id: int
    home_team_id: int
    away_team_id: int
    home_team_name: str = ""
    away_team_name: str = ""
    competition_id: int = 0
    season_id: int = 0
    kickoff_timestamp: int = 0
    source: str = ""
    retrieved_at: float = 0.0
    status: FixtureStatus = FixtureStatus.SCHEDULED

    @property
    def fixture_id(self) -> str:
        """Deterministic identity based on source and source_fixture_id.

        Does NOT depend on retrieval time, team names, or kickoff time.
        Same fixture from same source always produces same ID.
        """
        canonical = json.dumps({
            "source": self.source,
            "source_fixture_id": self.source_fixture_id,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Full content hash including all fields (for change detection)."""
        canonical = json.dumps({
            "source": self.source,
            "source_fixture_id": self.source_fixture_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "kickoff_timestamp": self.kickoff_timestamp,
            "status": self.status.value,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def is_terminal(self) -> bool:
        """Whether this fixture is in a terminal state."""
        return self.status in (FixtureStatus.COMPLETED, FixtureStatus.CANCELLED)

    @property
    def is_paper_eligible(self) -> bool:
        """Whether this fixture can receive paper trades (must be SCHEDULED)."""
        return self.status == FixtureStatus.SCHEDULED

    def transition(self, new_status: FixtureStatus) -> "FutureFixture":
        """Create a new fixture with updated status.

        Args:
            new_status: Target status.

        Returns:
            New FutureFixture with updated status.

        Raises:
            ValueError: If transition is invalid.
        """
        valid = _FIXTURE_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Invalid fixture transition: {self.status.value} → {new_status.value}. "
                f"Valid: {[s.value for s in valid]}"
            )
        return replace(self, status=new_status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "source_fixture_id": self.source_fixture_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "kickoff_timestamp": self.kickoff_timestamp,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "status": self.status.value,
            "content_hash": self.content_hash,
        }
