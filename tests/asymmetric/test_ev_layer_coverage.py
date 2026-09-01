# Feature: asymmetric-matchup-engine, Property 24: Audit-grounded per-side EV coverage
"""Property 24: per-side EV is computed iff audit-grounded (task 11.10).

**Property 24** — for any fixture and any requested market, the EV_Layer computes
a per-side EV iff the market is a Per_Side_Priced_Market and a Priced_Book prices
it for that league; team cards never receives a per-side EV; a Championship
fixture sources per-side prices only from bet365; an EPL fixture priced by both
bet365 and betmgm-uk presents both books' EV separately (unblended).

Validates: Requirements 9.9, 9.10, 9.11, 15.

Implemented as one Hypothesis property test over (league, market, book) with
``@settings(max_examples=100)``, plus focused unit assertions on the audit map.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.research.asymmetric.ev_layer import (
    BOOK_MARKET_COVERAGE,
    LEAGUE_BOOKS,
    PER_SIDE_PRICED_MARKETS,
    TEAM_CARDS_MARKET,
    EVLayer,
    books_for_league,
    is_per_side_priced_market,
    per_side_ev_coverage,
)

_ALL_MARKETS = list(PER_SIDE_PRICED_MARKETS) + [TEAM_CARDS_MARKET, "match_corners"]
_ALL_BOOKS = ["bet365", "betmgm-uk", "paddy-power", "pinnacle"]
_LEAGUES = ["Championship", "EPL", "Ligue 2"]


@settings(max_examples=200, deadline=None)
@given(
    league=st.sampled_from(_LEAGUES),
    market=st.sampled_from(_ALL_MARKETS),
    book=st.sampled_from(_ALL_BOOKS),
    side=st.sampled_from(["home", "away"]),
)
def test_per_side_ev_iff_audit_grounded(league, market, book, side) -> None:
    layer = EVLayer()
    # A simple valid PMF over counts 0..6.
    pmf = [0.05, 0.10, 0.20, 0.25, 0.20, 0.15, 0.05]
    entry = layer.compute_entry(
        market=market, book=book, side=side, line=2.5, pmf=pmf,
        over_odds=1.9, under_odds=1.9,
    )

    should_price = (
        is_per_side_priced_market(market)
        and book in books_for_league(league)
        and market in BOOK_MARKET_COVERAGE.get(book, frozenset())
    )
    # compute_entry itself only gates on market-is-per-side + valid odds; the
    # league/book gating lives in per_side_ev_coverage. Verify both layers.
    if not is_per_side_priced_market(market):
        assert entry is None  # cards / match markets never get per-side EV
    else:
        assert entry is not None  # valid per-side market + valid odds

    # Coverage layer: the (market, book) is 'priced' iff audit-grounded.
    coverage = {(c.market, c.book): c.priced for c in per_side_ev_coverage(league)}
    if is_per_side_priced_market(market) and book in books_for_league(league):
        assert coverage.get((market, book)) is (
            market in BOOK_MARKET_COVERAGE.get(book, frozenset())
        )
    # And team cards is never a coverage cell.
    assert all(c.market != TEAM_CARDS_MARKET for c in per_side_ev_coverage(league))


def test_team_cards_never_gets_per_side_ev() -> None:
    layer = EVLayer()
    pmf = [0.2, 0.3, 0.3, 0.2]
    entry = layer.compute_entry(
        market=TEAM_CARDS_MARKET, book="bet365", side="home", line=2.5, pmf=pmf,
        over_odds=1.9, under_odds=1.9,
    )
    assert entry is None
    assert TEAM_CARDS_MARKET not in PER_SIDE_PRICED_MARKETS


def test_championship_bet365_only_epl_both_books() -> None:
    assert books_for_league("Championship") == ("bet365",)
    assert set(books_for_league("EPL")) == {"bet365", "betmgm-uk"}

    # EPL presents both books, unblended: two coverage cells per priced market.
    epl = per_side_ev_coverage("EPL")
    for market in PER_SIDE_PRICED_MARKETS:
        books = sorted(c.book for c in epl if c.market == market and c.priced)
        assert books == ["bet365", "betmgm-uk"], (market, books)

    # Championship: only bet365.
    champ = per_side_ev_coverage("Championship")
    for market in PER_SIDE_PRICED_MARKETS:
        books = sorted(c.book for c in champ if c.market == market and c.priced)
        assert books == ["bet365"], (market, books)


def test_unpriced_league_has_no_per_side_ev() -> None:
    assert books_for_league("Ligue 2") == ()
    assert per_side_ev_coverage("Ligue 2") == []
