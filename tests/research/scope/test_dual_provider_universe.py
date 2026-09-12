"""The dual-provider intersection rule, and the death of Pilot-C scope.

Proves boundary claims A, B and C:

A. A safely mapped FootyStats + TheStatsAPI league is eligible for full research
   processing, whether or not it was ever a Pilot-C league.
B. Pilot-C membership and the legacy ``PILOT_C_EXISTING_SCOPE`` label are
   irrelevant to eligibility.
C. An unsupported or unresolvable provider mapping fails closed, with a reason
   that distinguishes *which* failure occurred.
"""

from __future__ import annotations

import pytest

from src.research.prospective.crosswalk import CrosswalkEntry, IdentityStatus
from src.research.scope.dual_provider import (
    DEPRECATED_PILOT_C_MODEL_STATUS,
    IDENTITY_UNSAFE_REASONS,
    LEGACY_NON_BEHAVIORAL_MODEL_STATUSES,
    PROVIDER_UNSUPPORTED_REASONS,
    ScopeDecision,
    ScopeExclusionReason,
    assert_model_status_non_behavioral,
    build_dual_provider_universe,
    corpus_covered_competition_ids,
    evaluate_league,
)

from tests.research.scope.conftest import NON_PILOT_C, league_entry, write_registry


def _entry(**kwargs) -> CrosswalkEntry:
    """A VERIFIED crosswalk entry, overridable per test."""
    defaults = dict(
        canonical_competition_id="canon_x",
        canonical_name="Test League",
        country="Nowhere",
        footystats_id="12345",
        footystats_name="Test League",
        thestatsapi_competition_id="comp_test",
        thestatsapi_name="Test",
        identity_status=IdentityStatus.VERIFIED,
        verification_method="level_a_registry_matched_single_id",
        odds_available=True,
        xg_available=True,
        has_team_stats=True,
        has_player_stats=True,
        evidence={"mapping_status": "MATCHED", "thestatsapi_competition_ids": ["comp_test"]},
    )
    defaults.update(kwargs)
    return CrosswalkEntry(**defaults)


# ── A. dual-provider eligibility ─────────────────────────────────────────────
def test_safely_mapped_league_is_eligible():
    decision = evaluate_league(_entry())
    assert decision.decision is ScopeDecision.ELIGIBLE
    assert decision.exclusion_reason is ScopeExclusionReason.NONE
    assert decision.thestatsapi_competition_id == "comp_test"


def test_several_non_pilot_c_leagues_all_become_eligible(tmp_path):
    """Coverage: representative leagues well outside the original three/four."""
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name=name, comp_ids=[cid], country=country)
         for name, cid, country in NON_PILOT_C],
    )
    universe = build_dual_provider_universe(registry)

    assert len(universe.eligible) == len(NON_PILOT_C)
    for _name, cid, _country in NON_PILOT_C:
        assert universe.is_eligible(cid), f"{cid} should be in the engine universe"
    # None of these is a Pilot-C competition.
    assert not {cid for _n, cid, _c in NON_PILOT_C} & {
        "comp_3039", "comp_8321", "comp_9777", "comp_0976"
    }


# ── B. Pilot-C irrelevance ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "legacy_status",
    sorted(LEGACY_NON_BEHAVIORAL_MODEL_STATUSES) + [None, "SOME_FUTURE_LABEL"],
)
def test_legacy_model_status_never_changes_eligibility(legacy_status):
    """Changing/removing PILOT_C_EXISTING_SCOPE must not change eligibility."""
    baseline = evaluate_league(_entry(), legacy_model_status=None)
    got = evaluate_league(_entry(), legacy_model_status=legacy_status)
    assert got.decision is baseline.decision
    assert got.exclusion_reason is baseline.exclusion_reason


def test_model_status_non_behavioral_invariant_holds():
    assert_model_status_non_behavioral()


def test_two_identical_leagues_differing_only_in_pilot_c_label_are_equally_eligible(tmp_path):
    """The core Pilot-C deprecation proof."""
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(
                name="Legacy Pilot League", comp_ids=["comp_8321"],
                model_status=DEPRECATED_PILOT_C_MODEL_STATUS,
            ),
            league_entry(
                name="Never Pilot League", comp_ids=["comp_5840"],
                model_status="RESEARCH_ONLY_NOT_VALIDATED",
            ),
        ],
    )
    universe = build_dual_provider_universe(registry)

    assert universe.is_eligible("comp_8321")
    assert universe.is_eligible("comp_5840")
    decisions = {lg.canonical_name: lg.decision for lg in universe.leagues}
    assert decisions["Legacy Pilot League"] is decisions["Never Pilot League"]


def test_thin_corpus_does_not_remove_a_league_from_the_universe(tmp_path):
    """Corpus depth is model readiness, not provider eligibility (requirement 3)."""
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(
                name="No Corpus League", comp_ids=["comp_7777"],
                complete_seasons=0, model_status="BLOCKED_NO_TWO_SEASON_CORPUS",
            ),
        ],
    )
    universe = build_dual_provider_universe(registry)

    assert universe.is_eligible("comp_7777"), (
        "a league both providers support must stay in the universe even with no "
        "two-season corpus; corpus depth gates the model stage, not the league"
    )
    league = universe.league_for("comp_7777")
    assert league.corpus_complete_seasons == 0
    # ...but it is correctly reported as outside the corpus-covered set, which is
    # what the freshness benchmark uses.
    assert "comp_7777" not in corpus_covered_competition_ids(universe)


def test_no_hardcoded_three_or_four_league_list_in_the_scope_rule():
    """The rule must contain no league allowlist in executable code.

    Checked against the AST rather than the raw text: the module docstrings
    legitimately *name* the Pilot-C competition ids to explain what was removed and
    why, and a plain substring scan would forbid documenting the deprecation. What
    must not exist is a Pilot-C id as a live string constant — which is what an
    allowlist would look like.
    """
    import ast
    import inspect

    from src.research.scope import dual_provider, market_scope

    banned = {"comp_3039", "comp_8321", "comp_9777", "comp_0976"}

    for module in (dual_provider, market_scope):
        tree = ast.parse(inspect.getsource(module))
        # Collect docstring nodes so they can be exempted.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstrings.add(id(body[0].value))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            assert node.value not in banned, (
                f"{module.__name__} line {node.lineno} contains Pilot-C competition "
                f"id {node.value!r} as a live string constant; the scope rule must be "
                "provider-derived with no league allowlist"
            )


# ── C. fail-closed exclusions, each distinguishable ──────────────────────────
def test_footystats_only_league_is_excluded(tmp_path):
    """FootyStats has it, TheStatsAPI does not -> excluded as provider-unsupported."""
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name="Poland 1. Liga", comp_ids=[], mapping_status="BLOCKED")],
    )
    universe = build_dual_provider_universe(registry)

    assert universe.eligible == ()
    (excluded,) = universe.excluded
    assert excluded.exclusion_reason is ScopeExclusionReason.THESTATSAPI_UNSUPPORTED
    assert excluded.exclusion_reason in PROVIDER_UNSUPPORTED_REASONS


def test_thestatsapi_only_competition_is_never_introduced(tmp_path):
    """A TheStatsAPI competition with no FootyStats row cannot enter the universe.

    The registry is built one row per *FootyStats* league, so a TheStatsAPI-only
    competition has no row at all. Proven by absence: the extra competition id
    exists in the inventory but never appears in the universe.
    """
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name="Germany Bundesliga", comp_ids=["comp_5840"])],
    )
    universe = build_dual_provider_universe(registry)

    assert universe.eligible_competition_ids == ("comp_5840",)
    assert not universe.is_eligible("comp_999999")
    assert universe.league_for("comp_999999") is None


def test_blocked_provider_mapping_fails_closed():
    entry = _entry(
        identity_status=IdentityStatus.API_UNSUPPORTED,
        thestatsapi_competition_id=None,
        evidence={"mapping_status": "BLOCKED", "thestatsapi_competition_ids": ["comp_ghost"]},
    )
    decision = evaluate_league(entry)
    assert decision.decision is ScopeDecision.EXCLUDED
    assert decision.exclusion_reason is ScopeExclusionReason.PROVIDER_MAPPING_BLOCKED


def test_unresolved_mapping_is_excluded():
    entry = _entry(
        identity_status=IdentityStatus.UNRESOLVED,
        thestatsapi_competition_id=None,
        evidence={"mapping_status": "WEIRD", "thestatsapi_competition_ids": ["comp_x"]},
    )
    decision = evaluate_league(entry)
    assert decision.decision is ScopeDecision.EXCLUDED
    assert decision.exclusion_reason is ScopeExclusionReason.IDENTITY_UNRESOLVED
    assert decision.exclusion_reason in IDENTITY_UNSAFE_REASONS


def test_ambiguous_identity_is_excluded():
    entry = _entry(
        identity_status=IdentityStatus.AMBIGUOUS,
        thestatsapi_competition_id=None,
        verification_method="level_a_link_mismatch",
        evidence={"mapping_status": "MATCHED", "thestatsapi_competition_ids": ["comp_test"]},
    )
    decision = evaluate_league(entry)
    assert decision.decision is ScopeDecision.EXCLUDED
    assert decision.exclusion_reason is ScopeExclusionReason.IDENTITY_AMBIGUOUS


def test_split_apertura_clausura_is_not_blindly_activated(tmp_path):
    """SPLIT_OR_PARTIAL stays excluded, with a reason naming the risk."""
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(
                name="Mexico Liga MX",
                comp_ids=["comp_298265", "comp_137103"],
                mapping_status="SPLIT_OR_PARTIAL",
                representation_note="TheStatsAPI separates Apertura and Clausura.",
            ),
        ],
    )
    universe = build_dual_provider_universe(registry)

    assert universe.eligible == ()
    (excluded,) = universe.excluded
    assert excluded.exclusion_reason is ScopeExclusionReason.SPLIT_OR_PARTIAL_NOT_DETERMINISTIC
    assert "pool fixtures" in excluded.detail
    # The candidate ids survive as diagnostic evidence, never as a join.
    assert excluded.candidate_competition_ids == ("comp_298265", "comp_137103")
    assert excluded.thestatsapi_competition_id is None


def test_partial_split_with_one_id_also_fails_closed(tmp_path):
    """Only the Apertura half mapped: still refused, for the right reason."""
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(
                name="Colombia Categoria Primera A",
                comp_ids=["comp_720692"],
                mapping_status="SPLIT_OR_PARTIAL",
                representation_note="Only the Apertura counterpart is present.",
            ),
        ],
    )
    universe = build_dual_provider_universe(registry)
    (excluded,) = universe.excluded
    assert excluded.exclusion_reason is ScopeExclusionReason.SPLIT_OR_PARTIAL_NOT_DETERMINISTIC
    assert "part of the FootyStats season" in excluded.detail


def test_verified_without_a_linked_id_fails_closed():
    """Defence in depth: VERIFIED but no id must never activate."""
    entry = _entry(thestatsapi_competition_id=None)
    decision = evaluate_league(entry)
    assert decision.decision is ScopeDecision.EXCLUDED
    assert decision.exclusion_reason is ScopeExclusionReason.IDENTITY_UNRESOLVED


def test_every_league_gets_a_row_nothing_vanishes(tmp_path):
    """An excluded league is present and labelled, never silently absent."""
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(name="Good League", comp_ids=["comp_5840"]),
            league_entry(name="Blocked League", comp_ids=[], mapping_status="BLOCKED"),
            league_entry(
                name="Split League", comp_ids=["comp_a", "comp_b"],
                mapping_status="SPLIT_OR_PARTIAL",
            ),
        ],
    )
    universe = build_dual_provider_universe(registry)

    assert len(universe.leagues) == 3
    assert len(universe.eligible) == 1
    assert len(universe.excluded) == 2
    assert universe.exclusion_summary() == {
        "SPLIT_OR_PARTIAL_NOT_DETERMINISTIC": 1,
        "THESTATSAPI_UNSUPPORTED": 1,
    }


def test_summary_declares_pilot_c_non_behavioral(tmp_path):
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name="Germany Bundesliga", comp_ids=["comp_5840"])],
    )
    summary = build_dual_provider_universe(registry).summary()
    assert summary["pilot_c_is_behavioral_input"] is False
    assert summary["legacy_model_status_is_behavioral"] is False


def test_eligible_competition_ids_are_deterministic(tmp_path):
    registry = write_registry(
        tmp_path / "registry.json",
        [
            league_entry(name="Z League", comp_ids=["comp_zzz"]),
            league_entry(name="A League", comp_ids=["comp_aaa"]),
        ],
    )
    first = build_dual_provider_universe(registry).eligible_competition_ids
    second = build_dual_provider_universe(registry).eligible_competition_ids
    assert first == second == ("comp_aaa", "comp_zzz")
