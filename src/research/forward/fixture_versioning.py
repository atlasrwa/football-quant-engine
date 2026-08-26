"""Fixture Versioning — handles rescheduled, postponed, and changed fixtures.

Fixtures can be postponed, rescheduled, or have kickoff times changed.
This module:
- Tracks fixture versions (immutable history)
- Invalidates stale snapshots when kickoff changes significantly
- Preserves historical event trail
- Never mutates historical research records

Key rules:
- If kickoff changes, stale snapshots MAY be invalidated
- Settlement against obsolete fixture metadata is prevented
- Historical snapshots are PRESERVED (never deleted)
- A new valid snapshot can be created for the rescheduled fixture
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.forward.future_fixture import FixtureStatus, FutureFixture


@dataclass(frozen=True)
class FixtureVersion:
    """Immutable version record for a fixture at a point in time."""
    fixture_id: str
    version_number: int
    kickoff_timestamp: int
    status: FixtureStatus
    recorded_at: float
    change_reason: str = ""  # "initial", "rescheduled", "postponed", "status_change"

    @property
    def version_id(self) -> str:
        canonical = json.dumps({
            "fixture_id": self.fixture_id,
            "version_number": self.version_number,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "fixture_id": self.fixture_id,
            "version_number": self.version_number,
            "kickoff_timestamp": self.kickoff_timestamp,
            "status": self.status.value,
            "recorded_at": self.recorded_at,
            "change_reason": self.change_reason,
        }


class FixtureVersionTracker:
    """Tracks fixture versions and detects meaningful changes.

    Usage:
        tracker = FixtureVersionTracker()
        tracker.record(fixture)  # Initial version
        # ... time passes, fixture is rescheduled ...
        changed = tracker.record(updated_fixture)  # Detects change
        if changed:
            # Invalidate stale snapshots
    """

    def __init__(self, kickoff_change_threshold: int = 3600) -> None:
        """Initialize version tracker.

        Args:
            kickoff_change_threshold: Minimum kickoff change (seconds) to trigger
                snapshot invalidation. Small changes (e.g., 5 min delay) are tolerated.
        """
        self._versions: dict[str, list[FixtureVersion]] = {}
        self._kickoff_threshold = kickoff_change_threshold

    def record(self, fixture: FutureFixture) -> bool:
        """Record a fixture observation. Returns True if meaningful change detected.

        Meaningful changes:
        - First time seeing this fixture
        - Status changed
        - Kickoff changed by more than threshold
        """
        fid = fixture.fixture_id
        existing_versions = self._versions.get(fid, [])

        if not existing_versions:
            # First observation
            version = FixtureVersion(
                fixture_id=fid,
                version_number=1,
                kickoff_timestamp=fixture.kickoff_timestamp,
                status=fixture.status,
                recorded_at=time.time(),
                change_reason="initial",
            )
            self._versions[fid] = [version]
            return True

        latest = existing_versions[-1]

        # Check for meaningful change
        status_changed = latest.status != fixture.status
        kickoff_changed = abs(fixture.kickoff_timestamp - latest.kickoff_timestamp) > self._kickoff_threshold

        if not status_changed and not kickoff_changed:
            return False  # No meaningful change

        # Record new version
        reason = "status_change" if status_changed else "rescheduled"
        if fixture.status == FixtureStatus.POSTPONED:
            reason = "postponed"

        version = FixtureVersion(
            fixture_id=fid,
            version_number=latest.version_number + 1,
            kickoff_timestamp=fixture.kickoff_timestamp,
            status=fixture.status,
            recorded_at=time.time(),
            change_reason=reason,
        )
        self._versions[fid].append(version)
        return True

    def get_versions(self, fixture_id: str) -> list[FixtureVersion]:
        """Get all recorded versions for a fixture."""
        return list(self._versions.get(fixture_id, []))

    def get_latest_version(self, fixture_id: str) -> Optional[FixtureVersion]:
        """Get the most recent version."""
        versions = self._versions.get(fixture_id, [])
        return versions[-1] if versions else None

    def is_kickoff_changed(self, fixture_id: str) -> bool:
        """Check if kickoff has been rescheduled from original."""
        versions = self._versions.get(fixture_id, [])
        if len(versions) < 2:
            return False
        return any(v.change_reason == "rescheduled" for v in versions[1:])

    def should_invalidate_snapshots(self, fixture_id: str) -> bool:
        """Whether existing snapshots should be considered stale.

        Snapshots are stale if:
        - Fixture was rescheduled (kickoff changed significantly)
        - Fixture was postponed then rescheduled
        """
        versions = self._versions.get(fixture_id, [])
        if len(versions) < 2:
            return False
        return any(
            v.change_reason in ("rescheduled", "postponed")
            for v in versions[1:]
        )
