"""Tests for canonical cross-provider identity mapping."""

from __future__ import annotations

import pytest

from src.research.identity import (
    CanonicalRegistry,
    EntityKind,
    IdentityConflictError,
    ProviderRef,
    UnknownEntityError,
)


def _team(provider, pid, name=""):
    return ProviderRef(provider, EntityKind.TEAM, pid, name)


class TestLinkingAndTranslation:
    def test_link_and_translate(self):
        reg = CanonicalRegistry()
        reg.link([_team("provider_a", "251", "Fulham"),
                  _team("thestatsapi", "tm_5290", "Fulham")])
        assert reg.translate(
            from_provider="provider_a", to_provider="thestatsapi",
            kind=EntityKind.TEAM, provider_id="251",
        ) == "tm_5290"
        assert reg.translate(
            from_provider="thestatsapi", to_provider="provider_a",
            kind=EntityKind.TEAM, provider_id="tm_5290",
        ) == "251"

    def test_distinct_entities_do_not_collapse(self):
        reg = CanonicalRegistry()
        reg.link([_team("provider_a", "1"), _team("thestatsapi", "tm_1")])
        reg.link([_team("provider_a", "2"), _team("thestatsapi", "tm_2")])
        assert len(reg.entities(EntityKind.TEAM)) == 2

    def test_idempotent_relink_same_refs(self):
        reg = CanonicalRegistry()
        e1 = reg.link([_team("provider_a", "1"), _team("thestatsapi", "tm_1")])
        e2 = reg.link([_team("provider_a", "1"), _team("thestatsapi", "tm_1")])
        assert e1.canonical_id == e2.canonical_id
        assert len(reg.entities(EntityKind.TEAM)) == 1


class TestAmbiguityFailsVisibly:
    def test_same_name_collision_does_not_silently_match(self):
        # Two different TheStatsAPI teams must never bind to one provider A team.
        reg = CanonicalRegistry()
        reg.link([_team("provider_a", "251"), _team("thestatsapi", "tm_5290")])
        with pytest.raises(IdentityConflictError):
            reg.link([_team("provider_a", "251"), _team("thestatsapi", "tm_9999")])

    def test_rebinding_a_ref_raises(self):
        reg = CanonicalRegistry()
        reg.link([_team("provider_a", "1"), _team("thestatsapi", "tm_1")])
        reg.link([_team("provider_a", "2"), _team("thestatsapi", "tm_2")])
        # Trying to merge two already-distinct canonical entities must fail.
        with pytest.raises(IdentityConflictError):
            reg.link([_team("provider_a", "1"), _team("provider_a", "2")])

    def test_unknown_resolve_raises_no_fuzzy(self):
        reg = CanonicalRegistry()
        reg.link([_team("provider_a", "251", "Manchester United")])
        # A same-ish name is NOT fuzzy-matched; unmapped id raises.
        with pytest.raises(UnknownEntityError):
            reg.resolve("thestatsapi", EntityKind.TEAM, "tm_5290")

    def test_try_resolve_returns_none(self):
        reg = CanonicalRegistry()
        assert reg.try_resolve("provider_a", EntityKind.TEAM, "999") is None
