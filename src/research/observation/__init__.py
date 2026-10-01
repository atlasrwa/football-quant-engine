"""Provider-agnostic point-in-time observation primitives.

An observation preserves the value reported by one provider plus the timestamps
needed to answer what was actually knowable at the forecast cutoff.

Core distinctions:
- event_time: when the underlying event occurred;
- observed_at: when the value was actually observable;
- retrieved_at: when QFE fetched it.

Storage is append-only. As-of reads may use only observations whose
observed_at is at or before the cutoff; later observations never overwrite
earlier history.
"""

from src.research.observation.model import (
    MISSING,
    Missing,
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
