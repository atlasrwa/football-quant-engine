"""Append-only observation store with as-of (point-in-time) queries.

The store never overwrites: appending a new observation for an existing key
retains all prior observations. This lets us reconstruct exactly what was known
at any past cutoff and detect when a later retrieval reported a different value.

Key guarantees:
- ``append`` is idempotent on identical observations (same observation_id) and
  additive otherwise; it NEVER mutates or deletes an existing record.
- ``as_of`` returns the latest observation for a key whose ``observed_at`` is
  <= the cutoff — i.e. the value that was genuinely available then. An
  observation retrieved later but observed-after-cutoff can never be returned
  for an earlier cutoff, so a later API retrieval cannot rewrite history.
- Observations with no ``observed_at`` are excluded from any finite-cutoff
  as_of result (fail-safe): we will not assert availability we cannot prove.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from src.research.observation.model import ObservationKey, ProviderObservation


class ObservationStore:
    """In-memory append-only store of provider observations."""

    def __init__(self) -> None:
        # (canonical_entity_id, concept) -> list[ProviderObservation]
        self._by_key: dict[tuple[str, str], list[ProviderObservation]] = defaultdict(list)
        self._seen_ids: set[str] = set()

    def append(self, obs: ProviderObservation) -> bool:
        """Append an observation. Returns True if newly stored.

        Idempotent: an observation whose observation_id is already present is
        ignored (returns False). Never overwrites existing records.
        """
        oid = obs.observation_id
        if oid in self._seen_ids:
            return False
        self._seen_ids.add(oid)
        self._by_key[(obs.key.canonical_entity_id, obs.key.concept)].append(obs)
        return True

    def extend(self, observations: Iterable[ProviderObservation]) -> int:
        return sum(1 for o in observations if self.append(o))

    def all_for(self, key: ObservationKey) -> list[ProviderObservation]:
        """All observations for a key, in insertion order (append-only history)."""
        return list(self._by_key.get((key.canonical_entity_id, key.concept), []))

    def history(self, key: ObservationKey) -> list[ProviderObservation]:
        """Observations for a key sorted by observed_at (None sorts last)."""
        obs = self.all_for(key)
        return sorted(obs, key=lambda o: (o.observed_at is None, o.observed_at or 0))

    def as_of(
        self,
        key: ObservationKey,
        cutoff: Optional[float],
        *,
        source: Optional[str] = None,
    ) -> Optional[ProviderObservation]:
        """Latest observation for ``key`` available at ``cutoff``.

        Args:
            key: Observation key.
            cutoff: As-of boundary (unix). None = no restriction.
            source: If given, restrict to a single provider.

        Returns:
            The most recently-observed eligible observation, or None if none
            were available by the cutoff.
        """
        candidates = [
            o for o in self.all_for(key)
            if o.available_at(cutoff) and (source is None or o.source == source)
        ]
        if not candidates:
            return None
        # Latest by observed_at; among equal observed_at prefer latest retrieval.
        return max(
            candidates,
            key=lambda o: (o.observed_at or 0, o.retrieved_at or 0),
        )

    def as_of_by_source(
        self,
        key: ObservationKey,
        cutoff: Optional[float],
    ) -> dict[str, ProviderObservation]:
        """As-of observation per source, keyed by source id.

        Useful for reconciliation: gives the latest eligible value from each
        provider at the cutoff so a policy can decide between them.
        """
        result: dict[str, ProviderObservation] = {}
        for o in self.all_for(key):
            if not o.available_at(cutoff):
                continue
            prev = result.get(o.source)
            if prev is None or (o.observed_at or 0, o.retrieved_at or 0) > (
                prev.observed_at or 0, prev.retrieved_at or 0
            ):
                result[o.source] = o
        return result

    def keys(self) -> list[ObservationKey]:
        return [ObservationKey(c, concept) for (c, concept) in self._by_key.keys()]

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_key.values())
