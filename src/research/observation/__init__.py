"""Provider-agnostic observation model with point-in-time provenance.

An *observation* is a single (field or record) value as reported by ONE
provider, together with enough provenance to answer:

    "What information was actually available when a forecast was generated?"

This module intentionally sits ABOVE the per-provider provenance records
(footystats.DataProvenance, thestatsapi.TheStatsAPIProvenance): those describe
how a match was fetched/normalized; a ``ProviderObservation`` describes a
single observed value with the timestamps needed for as-of reconstruction and
reconciliation.

Core distinctions preserved:
- event_time      : when the underlying event happened (kickoff).
- observed_at     : when the value was actually observable/published.
- retrieved_at    : when we fetched it.
- forecast_cutoff : the as-of boundary a consumer must respect. An observation
                    is eligible for a forecast only if observed_at <= cutoff.

Storage is append-only: a later observation for the same key NEVER overwrites
an earlier one; both are retained so historical point-in-time state can be
reconstructed. ``as_of`` queries select the latest observation whose
observed_at <= cutoff.
"""

from __future__ import annotations

from src.research.observation.model import (
    Missing,
    MISSING,
    ObservationKey,
    ProviderObservation,
)
from src.research.observation.store import ObservationStore

__all__ = [
    "Missing",
    "MISSING",
    "ObservationKey",
    "ProviderObservation",
    "ObservationStore",
]
