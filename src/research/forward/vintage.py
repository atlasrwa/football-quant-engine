"""Forecast vintages — EARLY (~T-24h) and LATE (~T-60m).

A *vintage* fixes the forecast cutoff relative to kickoff. It lets us produce
two forecasts per fixture from the SAME infrastructure:

    EARLY : cutoff = kickoff - 24h   (no confirmed lineups yet)
    LATE  : cutoff = kickoff - 60m   (may include confirmed XI, referee, and
                                      the latest pre-cutoff bookmaker prices)

Core guarantees:
- The cutoff is derived from kickoff and the vintage offset; it is the as-of
  boundary every consumer must respect.
- Availability is NEVER fabricated. A lineup/referee/odds observation is
  available to a vintage ONLY if it was actually observed at or before that
  vintage's cutoff (checked against a ProviderObservation.observed_at via the
  ObservationStore). If it was not observed in time, it stays unavailable —
  including for LATE.
- EARLY explicitly does not depend on confirmed lineups: the EARLY policy marks
  lineup/referee concepts as not-consulted regardless of whether a (later)
  observation exists.

This module is INFRASTRUCTURE ONLY: it establishes vintages and the
availability gate. It does not implement lineup modeling or change the champion
model. It computes cutoffs and filters observations; downstream feature/model
code decides what to do with the available set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.research.observation.model import ObservationKey, ProviderObservation
from src.research.observation.store import ObservationStore


class ForecastVintage(Enum):
    """Named forecast vintages with their offset before kickoff (seconds)."""
    EARLY = "EARLY"   # ~24h before kickoff
    LATE = "LATE"     # ~60m before kickoff

    @property
    def offset_seconds(self) -> int:
        return {
            ForecastVintage.EARLY: 24 * 3600,
            ForecastVintage.LATE: 60 * 60,
        }[self]


# Concepts that represent late-breaking team-sheet information. EARLY forecasts
# must not consult these even if a (later) observation happens to exist.
LINEUP_CONCEPTS = frozenset({
    "confirmed_lineup",
    "confirmed_xi",
    "assigned_referee",
    "referee",
})


@dataclass(frozen=True)
class ForecastCutoff:
    """A concrete forecast cutoff for a fixture at a given vintage."""
    fixture_id: str
    vintage: ForecastVintage
    kickoff_timestamp: float
    cutoff_timestamp: float

    @property
    def consults_lineups(self) -> bool:
        """Whether this vintage may consult confirmed lineup/referee info."""
        return self.vintage == ForecastVintage.LATE


def compute_cutoff(
    fixture_id: str,
    kickoff_timestamp: float,
    vintage: ForecastVintage,
) -> ForecastCutoff:
    """Compute the forecast cutoff for a fixture at a vintage.

    cutoff = kickoff - vintage.offset. The cutoff is never after kickoff.
    """
    cutoff = float(kickoff_timestamp) - vintage.offset_seconds
    return ForecastCutoff(
        fixture_id=fixture_id,
        vintage=vintage,
        kickoff_timestamp=float(kickoff_timestamp),
        cutoff_timestamp=cutoff,
    )


class VintageAvailabilityGate:
    """Decides which observations are available to a forecast vintage.

    Backed by an ObservationStore. An observation is available to a cutoff iff
    it was observed at/before the cutoff (ObservationStore.as_of semantics).
    Lineup/referee concepts are additionally suppressed for EARLY.
    """

    def __init__(self, store: ObservationStore) -> None:
        self._store = store

    def is_concept_consultable(self, cutoff: ForecastCutoff, concept: str) -> bool:
        """Whether a concept may be consulted at all for this vintage.

        EARLY never consults lineup/referee concepts (independent of data).
        """
        if concept in LINEUP_CONCEPTS and not cutoff.consults_lineups:
            return False
        return True

    def available(
        self,
        cutoff: ForecastCutoff,
        concept: str,
        *,
        canonical_entity_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[ProviderObservation]:
        """Return the as-of observation for a concept at this vintage, or None.

        Returns None when:
        - the concept is not consultable for this vintage (e.g. lineups @ EARLY),
        - or no observation was available at/before the cutoff (fail-safe).
        """
        if not self.is_concept_consultable(cutoff, concept):
            return None
        entity_id = canonical_entity_id or cutoff.fixture_id
        key = ObservationKey(canonical_entity_id=entity_id, concept=concept)
        return self._store.as_of(key, cutoff.cutoff_timestamp, source=source)

    def available_by_source(
        self,
        cutoff: ForecastCutoff,
        concept: str,
        *,
        canonical_entity_id: Optional[str] = None,
    ) -> dict[str, ProviderObservation]:
        """Per-source as-of observations for a concept at this vintage.

        Empty dict when the concept is not consultable for the vintage.
        """
        if not self.is_concept_consultable(cutoff, concept):
            return {}
        entity_id = canonical_entity_id or cutoff.fixture_id
        key = ObservationKey(canonical_entity_id=entity_id, concept=concept)
        return self._store.as_of_by_source(key, cutoff.cutoff_timestamp)
