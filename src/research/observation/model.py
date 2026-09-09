"""The ProviderObservation value type and its identity key.

NULL != ZERO is represented explicitly: a value of ``None`` means "observed as
absent/unknown" and a dedicated ``MISSING`` sentinel means "no observation
exists at all". These are distinct from a genuine numeric 0, which is a real
observed value. Consumers must never coerce MISSING or None into 0.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


class Missing:
    """Sentinel type meaning 'no observation exists' (distinct from None/0).

    ``None`` = observed but absent/unknown value.
    ``MISSING`` = there is no observation record at all.
    ``0`` = a genuine observed zero.
    """

    _instance: Optional["Missing"] = None

    def __new__(cls) -> "Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING = Missing()


@dataclass(frozen=True)
class ObservationKey:
    """Identity of what is being observed (NOT when/by whom).

    Attributes:
        canonical_entity_id: The canonical entity the observation is about
            (e.g. a canonical fixture id). This is how observations from
            different providers about the SAME thing are grouped.
        concept: The observed concept/field name (e.g. "total_corners",
            "GOALS_TOTAL@2.5:OVER"). Provider-agnostic.
    """
    canonical_entity_id: str
    concept: str


@dataclass(frozen=True)
class ProviderObservation:
    """A single provider's observation of one concept, with provenance.

    Attributes:
        key: What is being observed (canonical entity + concept).
        source: Provider id ("footystats" / "thestatsapi").
        provider_entity_id: The provider's own id for the entity (kept as a
            string so it is never conflated across providers).
        value: The observed value. May be a number, a string, ``None``
            (observed-absent), or ``MISSING`` (no observation).
        event_time: When the underlying event happened (unix), if applicable.
        observed_at: When the value was actually observable/published (unix).
            This is the timestamp the as-of gate compares against.
        retrieved_at: When we fetched it (unix).
        payload_hash: Content hash of the source payload the value came from.
        support: Optional integer sample support behind the value (e.g. number
            of matches contributing). None when not applicable.
        normalization_version: Version tag of the normalization that produced
            the value.
        observed_at_is_estimated: True when observed_at is an estimate (e.g.
            event+2h) rather than a provider-confirmed publication time.
    """
    key: ObservationKey
    source: str
    provider_entity_id: str
    value: Any = MISSING
    event_time: Optional[int] = None
    observed_at: Optional[int] = None
    retrieved_at: Optional[int] = None
    payload_hash: str = ""
    support: Optional[int] = None
    normalization_version: str = "1.0.0"
    observed_at_is_estimated: bool = False

    @property
    def has_value(self) -> bool:
        """Whether an actual observation exists (value is not MISSING)."""
        return not isinstance(self.value, Missing)

    @property
    def is_null(self) -> bool:
        """Whether the observation exists but its value is None (observed-absent)."""
        return self.has_value and self.value is None

    def available_at(self, cutoff: Optional[float]) -> bool:
        """Whether this observation was available at/before ``cutoff``.

        An observation with no observed_at is treated as NOT available for any
        finite cutoff (we cannot prove it predates the cutoff) — failing safe.
        A cutoff of None means "no restriction" (all observations available).
        """
        if cutoff is None:
            return True
        if self.observed_at is None:
            return False
        return self.observed_at <= cutoff

    @property
    def observation_id(self) -> str:
        """Deterministic identity for this observation instance."""
        canonical = json.dumps(
            {
                "canonical_entity_id": self.key.canonical_entity_id,
                "concept": self.key.concept,
                "source": self.source,
                "provider_entity_id": self.provider_entity_id,
                "observed_at": self.observed_at,
                "payload_hash": self.payload_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "canonical_entity_id": self.key.canonical_entity_id,
            "concept": self.key.concept,
            "source": self.source,
            "provider_entity_id": self.provider_entity_id,
            "value": ("MISSING" if isinstance(self.value, Missing) else self.value),
            "has_value": self.has_value,
            "is_null": self.is_null,
            "event_time": self.event_time,
            "observed_at": self.observed_at,
            "retrieved_at": self.retrieved_at,
            "payload_hash": self.payload_hash,
            "support": self.support,
            "normalization_version": self.normalization_version,
            "observed_at_is_estimated": self.observed_at_is_estimated,
        }
