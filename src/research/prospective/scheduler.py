"""Adaptive, restart-safe capture scheduler (state reconstructed from disk).

The scheduler decides WHICH captures are due for upcoming fixtures, purely from
persisted state plus the current wall-clock time. It holds no correctness-
critical in-memory state: on restart it replays the append-only capture store
to learn which vintages were already captured, whether a lineup was observed,
and what is next due. Old observations are never rewritten.

Adaptive density: odds are captured more frequently as kickoff approaches
(sparse near T-24h, frequent near/after the lineup window), subject to the
quota guard which always takes precedence.

A capture is "due" for a (fixture, vintage) when:
- the current time is within the vintage's due window (before kickoff), AND
- no capture already exists that is ON/NEAR target for that vintage.

Retrieval-event policy (documented): we RETAIN every retrieval event as its own
observation (keyed by observed_at), because two retrievals at different times
are research-meaningful even when the price did not change. Deduplication only
happens at the idempotency layer (identical observation id = same concept,
source, observed_at, payload hash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from src.research.prospective.storage import CaptureStore
from src.research.prospective.vintage_quality import (
    VintageQuality,
    best_capture_for_vintage,
    classify_capture,
)
from src.research.prospective.vintages import ProspectiveVintage


class CaptureKind(str, Enum):
    ODDS = "odds"
    LINEUP = "lineup"
    CONTEXT = "context"  # match detail / referee / injuries


@dataclass(frozen=True)
class UpcomingFixture:
    """A discovered upcoming fixture the scheduler plans captures for."""

    fixture_id: str
    kickoff_ts: float
    league: Optional[str] = None


@dataclass(frozen=True)
class DueCapture:
    """A capture the scheduler determines is due now."""

    fixture_id: str
    kickoff_ts: float
    vintage: ProspectiveVintage
    kind: CaptureKind
    seconds_to_kickoff: float

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "kickoff_ts": self.kickoff_ts,
            "vintage": self.vintage.value,
            "kind": self.kind.value,
            "seconds_to_kickoff": self.seconds_to_kickoff,
        }


#: Due windows (seconds-to-kickoff range) in which each vintage should be
#: attempted. A vintage is attemptable while STK is within [low, high]. These
#: are scheduling windows, not fabricated observation times.
_DUE_WINDOWS: dict[ProspectiveVintage, tuple[float, float]] = {
    ProspectiveVintage.EARLY: (16 * 3600, 32 * 3600),
    ProspectiveVintage.MID: (3 * 3600, 9 * 3600),
    ProspectiveVintage.LATE: (40 * 60, 90 * 60),
    ProspectiveVintage.FINAL: (5 * 60, 20 * 60),
}


@dataclass
class CaptureScheduler:
    """Determines due captures from persisted state + current time.

    ``store`` is the append-only capture store; the scheduler reads it (never
    writes) to reconstruct what has been captured. All decisions are a pure
    function of the store contents and ``now``.
    """

    store: CaptureStore

    def _observed_ats(self, fixture_id: str, *, concept_prefix: str) -> list[float]:
        """All observed_at times for a fixture whose concept matches a prefix."""
        out = []
        for rec in self.store.read_all():
            if rec.canonical_entity_id != fixture_id:
                continue
            if rec.concept.startswith(concept_prefix):
                out.append(float(rec.observed_at))
        return out

    def lineup_observed(self, fixture_id: str) -> Optional[float]:
        """First observed_at of a confirmed lineup for a fixture, or None."""
        times = self._observed_ats(fixture_id, concept_prefix="confirmed_lineup")
        return min(times) if times else None

    def vintage_captured(
        self,
        fixture_id: str,
        kickoff_ts: float,
        vintage: ProspectiveVintage,
        *,
        concept_prefix: str = "odds:",
    ) -> bool:
        """Whether an ON/NEAR-target odds capture already exists for a vintage."""
        times = self._observed_ats(fixture_id, concept_prefix=concept_prefix)
        if not times:
            return False
        q = best_capture_for_vintage(
            vintage=vintage, observed_ats=times, kickoff_ts=kickoff_ts
        )
        return q.quality in (VintageQuality.ON_TARGET, VintageQuality.NEAR_TARGET)

    def due_for_fixture(self, fixture: UpcomingFixture, *, now: float) -> list[DueCapture]:
        """Compute due captures for one fixture at time ``now``."""
        stk = fixture.kickoff_ts - now
        due: list[DueCapture] = []
        if stk <= 0:
            return due  # kickoff passed; nothing prospective is due

        for vintage, (low, high) in _DUE_WINDOWS.items():
            if not (low <= stk <= high):
                continue
            if self.vintage_captured(fixture.fixture_id, fixture.kickoff_ts, vintage):
                continue
            due.append(
                DueCapture(
                    fixture_id=fixture.fixture_id, kickoff_ts=fixture.kickoff_ts,
                    vintage=vintage, kind=CaptureKind.ODDS, seconds_to_kickoff=stk,
                )
            )

        # Lineup polling: from the LATE window onward, until first observed.
        late_low = _DUE_WINDOWS[ProspectiveVintage.LATE][1]
        if stk <= late_low and self.lineup_observed(fixture.fixture_id) is None:
            due.append(
                DueCapture(
                    fixture_id=fixture.fixture_id, kickoff_ts=fixture.kickoff_ts,
                    vintage=ProspectiveVintage.LATE, kind=CaptureKind.LINEUP,
                    seconds_to_kickoff=stk,
                )
            )
        return due

    def due_captures(
        self, fixtures: Iterable[UpcomingFixture], *, now: float
    ) -> list[DueCapture]:
        """All due captures across upcoming fixtures, nearest-kickoff first."""
        due: list[DueCapture] = []
        for fx in fixtures:
            due.extend(self.due_for_fixture(fx, now=now))
        due.sort(key=lambda d: d.seconds_to_kickoff)
        return due
