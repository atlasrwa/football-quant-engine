"""Market-level isolation: one unsupported market must not suppress a league.

Proves boundary claim D — an unsupported market excludes only that market, and the
competition plus its other markets continue — and pins the READY / PARTIAL /
UNSUPPORTED / UNKNOWN semantics, including that zero never conceals UNKNOWN.
"""

from __future__ import annotations

import pytest

from src.research.prospective.coverage_matrix import CHAMPION_MARKETS, MarketEligibility
from src.research.scope.market_scope import (
    MODEL_MARKET_TO_ODDS_MARKET,
    MarketExclusionReason,
    build_research_scope,
    market_exclusion_reason_for,
)

from tests.research.scope.conftest import (
    ALL_READY,
    coverage_row,
    league_entry,
    write_coverage_matrix,
    write_registry,
)


def _scope(tmp_path, *, leagues, rows):
    registry = write_registry(tmp_path / "registry.json", leagues)
    matrix = write_coverage_matrix(tmp_path / "matrix.json", rows)
    return build_research_scope(registry_path=registry, coverage_matrix_path=matrix)


# ── D. market isolation ──────────────────────────────────────────────────────
def test_bundesliga_style_mixed_coverage_processes_supported_markets(tmp_path):
    """The requirement's own example: goals READY, corners READY, cards PARTIAL,
    shots UNKNOWN -> process the supported markets, keep the league."""
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="Germany Bundesliga", comp_ids=["comp_5840"])],
        rows=[
            coverage_row(
                comp_id="comp_5840",
                canonical_name="Germany Bundesliga",
                market_eligibility={
                    "total_goals": "READY",
                    "match_corners": "READY",
                    "total_cards": "PARTIAL",
                    "match_shots_on_target": "UNKNOWN",
                },
            )
        ],
    )

    assert scope.is_in_research_scope("comp_5840"), "league must not be discarded"
    assert scope.odds_markets_for("comp_5840") == (
        "match_corners", "total_cards", "total_goals",
    )
    # shots on target abstains, and says why.
    assert market_exclusion_reason_for(scope, "comp_5840", "match_shots_on_target") == (
        MarketExclusionReason.PROVIDER_MARKET_UNKNOWN.value
    )
    # Model-side markets are the three with an odds counterpart.
    assert scope.model_markets_for("comp_5840") == ("cards", "corners", "goals")


def test_one_unsupported_market_does_not_suppress_the_league(tmp_path):
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="Test League", comp_ids=["comp_1111"])],
        rows=[
            coverage_row(
                comp_id="comp_1111",
                canonical_name="Test League",
                market_eligibility={
                    "total_goals": "READY",
                    "match_corners": "READY",
                    "total_cards": "UNSUPPORTED",
                    "match_shots_on_target": "READY",
                },
            )
        ],
    )

    assert scope.is_in_research_scope("comp_1111")
    assert "total_cards" not in scope.odds_markets_for("comp_1111")
    assert "cards" not in scope.model_markets_for("comp_1111")
    assert set(scope.model_markets_for("comp_1111")) == {"goals", "corners"}
    assert market_exclusion_reason_for(scope, "comp_1111", "total_cards") == (
        MarketExclusionReason.PROVIDER_MARKET_UNSUPPORTED.value
    )


def test_all_markets_unsupported_leaves_league_visible_but_unprocessable(tmp_path):
    """Fail closed at the market stage; the league is still reported, not deleted."""
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="No Odds League", comp_ids=["comp_2222"])],
        rows=[
            coverage_row(
                comp_id="comp_2222",
                canonical_name="No Odds League",
                market_eligibility={m: "UNSUPPORTED" for m in CHAMPION_MARKETS},
            )
        ],
    )

    assert not scope.is_in_research_scope("comp_2222")
    assert not scope.is_forecastable("comp_2222")
    # Still present with a complete market map — visible, with reasons.
    comp = scope.scope_for("comp_2222")
    assert comp is not None
    assert set(comp.market_eligibility) == set(CHAMPION_MARKETS)
    assert all(
        r == MarketExclusionReason.PROVIDER_MARKET_UNSUPPORTED.value
        for r in comp.market_exclusions.values()
    )


# ── status vocabulary is preserved ───────────────────────────────────────────
@pytest.mark.parametrize(
    "status,processable",
    [("READY", True), ("PARTIAL", True), ("UNSUPPORTED", False), ("UNKNOWN", False)],
)
def test_four_status_semantics_preserved(tmp_path, status, processable):
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="L", comp_ids=["comp_3333"])],
        rows=[
            coverage_row(
                comp_id="comp_3333", canonical_name="L",
                market_eligibility={m: status for m in CHAMPION_MARKETS},
            )
        ],
    )
    assert scope.is_in_research_scope("comp_3333") is processable


def test_unknown_is_never_coerced_to_unsupported(tmp_path):
    """UNKNOWN and UNSUPPORTED are different claims and stay different."""
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="L", comp_ids=["comp_4444"])],
        rows=[
            coverage_row(
                comp_id="comp_4444", canonical_name="L",
                market_eligibility={
                    "total_goals": "UNKNOWN",
                    "match_corners": "UNSUPPORTED",
                    "total_cards": "READY",
                    "match_shots_on_target": "PARTIAL",
                },
            )
        ],
    )
    comp = scope.scope_for("comp_4444")
    assert comp.market_eligibility["total_goals"] == MarketEligibility.UNKNOWN.value
    assert comp.market_eligibility["match_corners"] == MarketEligibility.UNSUPPORTED.value
    assert comp.market_exclusions["total_goals"] != comp.market_exclusions["match_corners"]


def test_market_status_counts_always_report_every_status_including_zero(tmp_path):
    """Zero must not conceal UNKNOWN: all four keys always present."""
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="L", comp_ids=["comp_5555"])],
        rows=[coverage_row(comp_id="comp_5555", canonical_name="L", market_eligibility=ALL_READY)],
    )
    counts = scope.market_status_counts()
    for market in CHAMPION_MARKETS:
        assert set(counts[market]) == {s.value for s in MarketEligibility}
        assert counts[market]["READY"] == 1
        assert counts[market]["UNKNOWN"] == 0  # explicit zero, not absent


def test_missing_coverage_matrix_fails_closed_but_keeps_leagues_visible(tmp_path):
    """A missing observability artifact must not look like a scope collapse."""
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name="Germany Bundesliga", comp_ids=["comp_5840"])],
    )
    scope = build_research_scope(
        registry_path=registry, coverage_matrix_path=tmp_path / "absent.json"
    )

    # Provider-eligible...
    assert len(scope.universe.eligible) == 1
    # ...but nothing processes, with an explicit "no evidence" reason.
    assert not scope.is_in_research_scope("comp_5840")
    comp = scope.scope_for("comp_5840")
    assert all(
        v == MarketEligibility.UNKNOWN.value for v in comp.market_eligibility.values()
    )
    assert all(
        r == MarketExclusionReason.NO_COVERAGE_EVIDENCE.value
        for r in comp.market_exclusions.values()
    )


def test_shots_on_target_has_no_model_counterpart_and_says_so(tmp_path):
    """A captured market with no model cannot be forecast — reported, not silent."""
    assert "match_shots_on_target" not in MODEL_MARKET_TO_ODDS_MARKET.values()
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="L", comp_ids=["comp_6666"])],
        rows=[
            coverage_row(
                comp_id="comp_6666", canonical_name="L",
                market_eligibility={
                    "total_goals": "UNSUPPORTED",
                    "match_corners": "UNSUPPORTED",
                    "total_cards": "UNSUPPORTED",
                    "match_shots_on_target": "READY",
                },
            )
        ],
    )
    # Capturable...
    assert scope.is_in_research_scope("comp_6666")
    assert scope.odds_markets_for("comp_6666") == ("match_shots_on_target",)
    # ...but not forecastable, because no model market maps onto it.
    assert not scope.is_forecastable("comp_6666")
    assert scope.model_markets_for("comp_6666") == ()
    comp = scope.scope_for("comp_6666")
    assert comp.market_exclusions["match_shots_on_target"] == (
        MarketExclusionReason.NO_ODDS_COUNTERPART.value
    )


def test_market_map_stays_in_lockstep_with_the_shadow_builder():
    """A model market with no shadow mapping could never become evidence."""
    from src.research.prospective.shadow_builder import MODEL_TO_ODDS_MARKET

    assert MODEL_MARKET_TO_ODDS_MARKET == MODEL_TO_ODDS_MARKET, (
        "market_scope and shadow_builder must agree on the model->odds market map, "
        "or a forecast could be committed for a market that can never be joined"
    )


def test_excluded_league_market_query_reports_the_league_reason(tmp_path):
    """Querying a market on an excluded league returns the league's reason."""
    registry = write_registry(
        tmp_path / "registry.json",
        [league_entry(name="Blocked", comp_ids=[], mapping_status="BLOCKED")],
    )
    matrix = write_coverage_matrix(tmp_path / "matrix.json", [])
    scope = build_research_scope(registry_path=registry, coverage_matrix_path=matrix)

    # No eligible competitions, so the lookup falls back to the league decision.
    assert scope.competitions == ()
    assert scope.summary()["excluded_leagues"] == 1
