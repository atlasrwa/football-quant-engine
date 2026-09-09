"""Canonical cross-provider identity.

Maps provider-specific identifiers (FootyStats integer ids, TheStatsAPI
prefixed ids) to stable *canonical* entity ids so the same real-world
competition / season / team / fixture can be recognized across providers
WITHOUT ever joining primarily by display name.

Design rules:
- Joins are by provider id via an explicit, persisted mapping.
- Ambiguous mappings (one provider id already bound to a different canonical
  entity, or two providers disagreeing) FAIL VISIBLY (raise) rather than
  silently matching the wrong entity.
- No fuzzy/name matching in the production prediction path. A name-similarity
  *suggestion* helper exists only as an offline review aid and is clearly
  separated; its output must be reviewed and persisted as an explicit mapping
  before it can be used.

Entities: competition/league, season, team, fixture.
"""

from __future__ import annotations

from src.research.identity.canonical import (
    CanonicalEntity,
    CanonicalRegistry,
    EntityKind,
    IdentityConflictError,
    ProviderRef,
    UnknownEntityError,
)

__all__ = [
    "CanonicalEntity",
    "CanonicalRegistry",
    "EntityKind",
    "IdentityConflictError",
    "ProviderRef",
    "UnknownEntityError",
]
