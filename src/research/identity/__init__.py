"""Provider-neutral canonical identity primitives.

Provider identifiers are linked to stable canonical competition, season, team
and fixture ids only through explicit mappings. Display names never authorize a
join and fuzzy matching is not part of the reboot code path.

Conflicting bindings fail visibly rather than silently merging entities.
"""

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
