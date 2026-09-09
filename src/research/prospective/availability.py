"""Injuries / suspensions snapshot normalization (capture-first, no inference).

The live docs expose team- and player-level injuries-suspensions endpoints with
explicit ``status`` / ``reason`` / ``active`` / ``start_date`` / ``expected_return``
fields. These records are provider CURRENT-STATE (not fixture-specific and not
carrying a provider observation timestamp), so:

- We store the snapshot AS OBSERVED with OUR retrieval time as provenance.
- We NEVER infer "not in XI => injured". Absence from a lineup is not an injury.
- Only fields actually present are used; missing endpoint data fails neutrally
  (returns an empty snapshot, never fabricated).

This is capture-first: we record what the provider states so that, later,
prior-only availability features can be built with proper point-in-time
discipline. This module does not build features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class UnavailabilityKind(str, Enum):
    INJURY = "INJURY"
    SUSPENSION = "SUSPENSION"


@dataclass(frozen=True)
class UnavailabilityRecord:
    """One explicit injury/suspension record as the provider stated it.

    Every field is optional because the provider may omit any of them; a
    missing field stays ``None`` (never coerced). ``reason`` is the provider's
    explicit cause code — the ONLY acceptable source of a reason. ``kind``
    distinguishes injury from suspension per the endpoint grouping.
    """

    player_id: str
    kind: UnavailabilityKind
    status: Optional[str] = None
    reason: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    expected_return: Optional[str] = None
    active: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "kind": self.kind.value,
            "status": self.status,
            "reason": self.reason,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "expected_return": self.expected_return,
            "active": self.active,
        }


@dataclass(frozen=True)
class AvailabilitySnapshot:
    """A team's injuries+suspensions as observed at OUR retrieval time.

    Attributes:
        team_id: The team the snapshot is for (None for a player-scoped snapshot).
        observed_at: OUR retrieval time (unix) — provenance even though the
            provider is current-state.
        injuries / suspensions: explicit records.
        available: whether the endpoint returned any data (False => neutral empty).
    """

    team_id: Optional[str]
    observed_at: float
    injuries: tuple[UnavailabilityRecord, ...]
    suspensions: tuple[UnavailabilityRecord, ...]

    @property
    def available(self) -> bool:
        return bool(self.injuries) or bool(self.suspensions)

    def player_status(self, player_id: str) -> Optional[UnavailabilityRecord]:
        """The explicit record for a player, or None (NOT inferred from absence)."""
        for rec in list(self.injuries) + list(self.suspensions):
            if rec.player_id == player_id:
                return rec
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "observed_at": self.observed_at,
            "injuries": [r.to_dict() for r in self.injuries],
            "suspensions": [r.to_dict() for r in self.suspensions],
            "available": self.available,
        }


def _record(raw: Mapping[str, Any], kind: UnavailabilityKind) -> Optional[UnavailabilityRecord]:
    pid = raw.get("player_id")
    if not pid:
        return None  # no stable id => cannot attach safely
    return UnavailabilityRecord(
        player_id=str(pid),
        kind=kind,
        status=raw.get("status"),
        reason=raw.get("reason"),
        start_date=raw.get("start_date"),
        end_date=raw.get("end_date"),
        expected_return=raw.get("expected_return"),
        active=raw.get("active"),
    )


def normalize_availability(
    payload: Optional[Mapping[str, Any]],
    *,
    team_id: Optional[str],
    observed_at: float,
) -> AvailabilitySnapshot:
    """Normalize a verified injuries-suspensions payload.

    Missing / empty payload fails neutrally to an empty snapshot (never a
    fabricated 'nobody injured' claim beyond what the provider returned).
    Records without a stable player id are dropped.
    """
    injuries: list[UnavailabilityRecord] = []
    suspensions: list[UnavailabilityRecord] = []
    if payload is not None:
        data = payload.get("data", payload)
        if isinstance(data, Mapping):
            for raw in data.get("injuries", []) or []:
                if isinstance(raw, Mapping):
                    rec = _record(raw, UnavailabilityKind.INJURY)
                    if rec is not None:
                        injuries.append(rec)
            for raw in data.get("suspensions", []) or []:
                if isinstance(raw, Mapping):
                    rec = _record(raw, UnavailabilityKind.SUSPENSION)
                    if rec is not None:
                        suspensions.append(rec)
    return AvailabilitySnapshot(
        team_id=team_id,
        observed_at=float(observed_at),
        injuries=tuple(injuries),
        suspensions=tuple(suspensions),
    )
