"""Canonical entity registry — stable cross-provider identity.

A ``CanonicalEntity`` groups the provider-specific references that all denote
the same real-world thing:

    canonical_team_id
        ↳ footystats: 251
        ↳ thestatsapi: tm_5290

Mapping is by provider id only. The registry enforces that a given
(provider, kind, provider_id) binds to at most ONE canonical entity; any
attempt to rebind it to a different canonical id raises ``IdentityConflictError``
so a wrong match fails loudly instead of silently corrupting joins.

Determinism: canonical ids are derived from the SORTED set of provider refs
(a content hash), so the same set of provider refs always yields the same
canonical id regardless of insertion order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


class EntityKind(Enum):
    """Kinds of entity that can be canonicalized."""
    COMPETITION = "COMPETITION"
    SEASON = "SEASON"
    TEAM = "TEAM"
    FIXTURE = "FIXTURE"


class IdentityConflictError(Exception):
    """Raised when a provider ref would bind to a conflicting canonical entity."""


class UnknownEntityError(KeyError):
    """Raised when a lookup finds no canonical entity for a provider ref."""


@dataclass(frozen=True)
class ProviderRef:
    """A provider-specific reference to an entity.

    Attributes:
        provider: Provider id, e.g. "footystats" or "thestatsapi".
        kind: Entity kind.
        provider_id: The provider's own id, kept as a STRING to avoid conflating
            FootyStats integers with TheStatsAPI prefixed ids (they only meet
            through an explicit canonical mapping, never by numeric coincidence).
        display_name: Human-readable name (metadata only, NEVER used for joins).
    """
    provider: str
    kind: EntityKind
    provider_id: str
    display_name: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        """Identity key: (provider, kind, provider_id). Name excluded."""
        return (self.provider, self.kind.value, self.provider_id)


def _canonical_id(kind: EntityKind, refs: Iterable[ProviderRef]) -> str:
    """Deterministic canonical id from the set of provider refs (name-free)."""
    keys = sorted({(r.provider, r.provider_id) for r in refs})
    canonical = json.dumps({"kind": kind.value, "refs": keys}, separators=(",", ":"))
    return f"{kind.value.lower()}_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


@dataclass
class CanonicalEntity:
    """A canonical entity aggregating provider references for one real thing."""
    kind: EntityKind
    refs: list[ProviderRef] = field(default_factory=list)
    canonical_id: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_id:
            if not self.refs:
                raise ValueError(
                    "CanonicalEntity requires either an explicit canonical_id or "
                    "at least one ProviderRef to derive one from (empty refs would "
                    "collide across entities)."
                )
            self.canonical_id = _canonical_id(self.kind, self.refs)

    def provider_id(self, provider: str) -> Optional[str]:
        """Return this entity's id for the given provider, if bound."""
        for r in self.refs:
            if r.provider == provider:
                return r.provider_id
        return None

    def to_dict(self) -> dict:
        return {
            "canonical_id": self.canonical_id,
            "kind": self.kind.value,
            "refs": [
                {
                    "provider": r.provider,
                    "provider_id": r.provider_id,
                    "display_name": r.display_name,
                }
                for r in sorted(self.refs, key=lambda x: (x.provider, x.provider_id))
            ],
        }


class CanonicalRegistry:
    """In-memory registry of canonical entities with conflict detection.

    The registry is the single source of truth for cross-provider joins. It is
    append-only in spirit: bindings can be added and are stable, but a provider
    ref can never be silently rebound to a different canonical entity.
    """

    def __init__(self) -> None:
        # (provider, kind, provider_id) -> canonical_id
        self._ref_index: dict[tuple[str, str, str], str] = {}
        # canonical_id -> CanonicalEntity
        self._entities: dict[str, CanonicalEntity] = {}

    def link(self, refs: list[ProviderRef]) -> CanonicalEntity:
        """Link a set of provider refs into one canonical entity.

        All refs must share the same kind. If some refs are already bound, they
        must all be bound to the SAME canonical entity; otherwise this raises
        ``IdentityConflictError`` (visible failure, no silent merge).

        Returns the resulting canonical entity.
        """
        if not refs:
            raise ValueError("link() requires at least one ProviderRef")
        kinds = {r.kind for r in refs}
        if len(kinds) != 1:
            raise ValueError(f"All refs must share one kind, got {kinds}")
        kind = next(iter(kinds))

        # Detect existing bindings.
        existing_canon: set[str] = set()
        for r in refs:
            cid = self._ref_index.get(r.key)
            if cid is not None:
                existing_canon.add(cid)

        if len(existing_canon) > 1:
            raise IdentityConflictError(
                f"Refs span multiple canonical entities {sorted(existing_canon)}; "
                "refusing to silently merge. Resolve mapping explicitly."
            )

        if existing_canon:
            canonical_id = next(iter(existing_canon))
            entity = self._entities[canonical_id]
            # Add any new refs; guard against a provider being bound twice to
            # two different provider_ids within the same entity.
            for r in refs:
                self._bind_ref(entity, r)
        else:
            # Derive a stable canonical id from the refs BEING linked (not from
            # an empty list), so distinct entities never collapse together.
            canonical_id = _canonical_id(kind, refs)
            entity = CanonicalEntity(kind=kind, refs=[], canonical_id=canonical_id)
            self._entities[canonical_id] = entity
            for r in refs:
                self._bind_ref(entity, r)

        return entity

    def _bind_ref(self, entity: CanonicalEntity, ref: ProviderRef) -> None:
        existing = self._ref_index.get(ref.key)
        if existing is not None and existing != entity.canonical_id:
            raise IdentityConflictError(
                f"Provider ref {ref.key} already bound to {existing}, "
                f"cannot rebind to {entity.canonical_id}"
            )
        # Guard: within an entity, one provider should map to a single id per
        # entity kind. A second, different provider_id for the same provider is
        # a conflict (e.g. two TheStatsAPI teams claimed as one canonical team).
        for r in entity.refs:
            if r.provider == ref.provider and r.provider_id != ref.provider_id:
                raise IdentityConflictError(
                    f"Entity {entity.canonical_id} already has {ref.provider} id "
                    f"{r.provider_id!r}; refusing to also bind {ref.provider_id!r}"
                )
        if ref.key not in self._ref_index:
            entity.refs.append(ref)
        self._ref_index[ref.key] = entity.canonical_id

    def resolve(self, provider: str, kind: EntityKind, provider_id: str) -> CanonicalEntity:
        """Resolve a provider ref to its canonical entity, or raise.

        No fuzzy matching: an unmapped ref raises ``UnknownEntityError``.
        """
        cid = self._ref_index.get((provider, kind.value, str(provider_id)))
        if cid is None:
            raise UnknownEntityError(
                f"No canonical {kind.value} for {provider}:{provider_id}"
            )
        return self._entities[cid]

    def try_resolve(self, provider: str, kind: EntityKind, provider_id: str) -> Optional[CanonicalEntity]:
        """Like ``resolve`` but returns None instead of raising."""
        cid = self._ref_index.get((provider, kind.value, str(provider_id)))
        return self._entities.get(cid) if cid else None

    def translate(
        self,
        *,
        from_provider: str,
        to_provider: str,
        kind: EntityKind,
        provider_id: str,
    ) -> Optional[str]:
        """Translate an id from one provider to another via the canonical map.

        Returns the target provider's id, or None if either the source ref is
        unmapped or the target provider is not bound on that entity.
        """
        entity = self.try_resolve(from_provider, kind, provider_id)
        if entity is None:
            return None
        return entity.provider_id(to_provider)

    def entities(self, kind: Optional[EntityKind] = None) -> list[CanonicalEntity]:
        vals = list(self._entities.values())
        if kind is not None:
            vals = [e for e in vals if e.kind == kind]
        return vals

    def __len__(self) -> int:
        return len(self._entities)
