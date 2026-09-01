"""EV_Layer — audit-grounded per-side expected value (Req 9.9-9.11, 15).

Responsibility:
    Compute per-side expected value ONLY for ``Per_Side_Priced_Markets`` (team
    corners, team total goals, team shots on target) and ONLY from
    ``Priced_Books`` grounded in the coverage audit (``docs/coverage_matrix.md``):

    * Championship fixtures -> per-side prices from **bet365 only** (Req 9.10, 15.2).
    * EPL fixtures         -> per-side prices from **both bet365 and betmgm-uk**,
                              presented **separately (unblended)** (Req 9.10, 15.3,
                              15.4).
    * **Team cards**        -> **no per-side price in any book**: no per-side EV is
                              ever computed; the caller states no per-side price is
                              available (Req 9.11, 15.5, 15.7).

    A book that does not price a requested market for a fixture is **omitted and
    recorded** (Req 15.6). Per-side EV is computed with the reused
    :class:`~src.research.ev_calculator.EVCalculator` machinery (Req 15) by
    turning the model's per-side count PMF into ``P(over line)`` and pricing it
    against the book's over/under odds.

Design decisions:
    * **Coverage is a hard gate.** :func:`per_side_ev_coverage` returns, for a
      fixture, exactly the (market, book) pairs the audit says are priced —
      nothing more (Property 24). Cards is structurally excluded from the
      Per_Side_Priced_Markets set, so it can never receive a per-side EV.
    * **Books are never blended.** Each (market, book) pair produces its own EV
      entry; EPL therefore yields two entries per market (bet365, betmgm-uk),
      presented side by side, never averaged.
    * **Reuse, don't reinvent, the EV math.** EV = ``P(model) * odds - 1`` and the
      de-vig / fair-probability handling come from
      :class:`src.research.ev_calculator.EVCalculator` /
      :class:`MarketProbabilityNormalizer`.

Isolation: imports only the isolated package + the general-purpose
``ev_calculator`` building block (no prior-effort modules, Req 13.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from src.research.ev_calculator import (
    EVCalculator,
    MarketProbabilityNormalizer,
    probability_to_fair_odds,
)

# ─────────────────────────────────────────────────────────────────────────────
# Audit-grounded constants (docs/coverage_matrix.md)
# ─────────────────────────────────────────────────────────────────────────────
#: The three per-side markets that real books price (Req 15, 9.9). Team cards is
#: deliberately absent: no per-side cards market exists in any book (Req 9.11).
PER_SIDE_PRICED_MARKETS: tuple[str, ...] = (
    "team_corners",
    "team_total_goals",
    "team_shots_on_target",
)

#: Team cards has no per-side price in any book (Req 9.11, 15.5, 15.7).
TEAM_CARDS_MARKET = "team_cards"

#: League -> ordered list of Priced_Books (Req 15.2-15.4).
#: Championship: bet365 only. EPL: bet365 + betmgm-uk (presented unblended).
LEAGUE_BOOKS: dict[str, tuple[str, ...]] = {
    "Championship": ("bet365",),
    "EPL": ("bet365", "betmgm-uk"),
}

#: Which (book, market) pairs each book actually prices, per the audit. bet365
#: prices all three per-side markets in both leagues; betmgm-uk prices the full
#: per-side set in EPL. A pair absent here is omitted-and-recorded (Req 15.6).
BOOK_MARKET_COVERAGE: dict[str, frozenset[str]] = {
    "bet365": frozenset(PER_SIDE_PRICED_MARKETS),
    "betmgm-uk": frozenset(PER_SIDE_PRICED_MARKETS),
    # paddy-power prices only team_corners in EPL (recorded for completeness).
    "paddy-power": frozenset({"team_corners"}),
}


def normalize_league_label(label: str) -> str:
    """Map a corpus league label to a canonical key in :data:`LEAGUE_BOOKS`.

    The Rich_Corpus labels the two priced leagues ``"Championship"`` and
    ``"EPL"``; anything else is returned unchanged (and will resolve to no books,
    i.e. no per-side EV, which is the honest default for unpriced leagues).
    """
    key = label.strip()
    lower = key.lower()
    if "championship" in lower:
        return "Championship"
    if lower in {"epl", "premier league", "english premier league"} or "premier" in lower:
        return "EPL"
    return key


def books_for_league(league_label: str) -> tuple[str, ...]:
    """Return the ordered Priced_Books for a league (Req 15.2-15.4)."""
    return LEAGUE_BOOKS.get(normalize_league_label(league_label), ())


# ─────────────────────────────────────────────────────────────────────────────
# Coverage decision (Property 24)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CoverageCell:
    """One (market, book) coverage decision for a fixture (Req 15.6).

    ``priced`` is True iff the book prices this per-side market for the league;
    when False the cell is recorded (omitted from EV) with a reason.
    """

    market: str
    book: str
    priced: bool
    reason: str = ""


def per_side_ev_coverage(league_label: str) -> list[CoverageCell]:
    """Enumerate the (market, book) coverage for a league (Property 24, Req 15).

    Produces one :class:`CoverageCell` per (Per_Side_Priced_Market x book-in-league)
    combination, with ``priced`` set per :data:`BOOK_MARKET_COVERAGE`. Team cards
    is never included, so it can never receive a per-side EV (Req 9.11). A league
    with no Priced_Books yields an empty list (no per-side EV).
    """
    books = books_for_league(league_label)
    cells: list[CoverageCell] = []
    for market in PER_SIDE_PRICED_MARKETS:
        for book in books:
            priced = market in BOOK_MARKET_COVERAGE.get(book, frozenset())
            cells.append(
                CoverageCell(
                    market=market,
                    book=book,
                    priced=priced,
                    reason=""
                    if priced
                    else f"{book} does not price {market} for {league_label}",
                )
            )
    return cells


def is_per_side_priced_market(market: str) -> bool:
    """True iff ``market`` is a Per_Side_Priced_Market (never true for cards)."""
    return market in PER_SIDE_PRICED_MARKETS


# ─────────────────────────────────────────────────────────────────────────────
# PMF -> P(over line)
# ─────────────────────────────────────────────────────────────────────────────
def prob_over_line(pmf: Sequence[float], line: float) -> float:
    """P(count > line) from a per-side count PMF.

    For a standard half-integer O/U ``line`` (e.g. 4.5), ``count > line`` means
    ``count >= ceil(line)``. Sums PMF mass strictly above the line. The result is
    clamped to [0, 1] for numerical safety.
    """
    total = 0.0
    for k, p in enumerate(pmf):
        if k > line:
            total += p
    return max(0.0, min(1.0, total))


# ─────────────────────────────────────────────────────────────────────────────
# Per-side EV entry
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PerSideEV:
    """A per-side EV entry for one (market, book, side, line) (Req 9.9, 15).

    Presented unblended per book. ``ev_over`` / ``ev_under`` are ``P(model) *
    odds - 1`` for each side of the O/U; ``fair_odds`` is ``1 / P(model over)``.
    """

    market: str
    book: str
    side: str            # "home" | "away"
    line: float
    p_over: float
    over_odds: float
    under_odds: float
    ev_over: float
    ev_under: float
    fair_odds_over: Optional[float]

    @property
    def best_side(self) -> str:
        """"over" or "under" — whichever has the higher EV (research only)."""
        return "over" if self.ev_over >= self.ev_under else "under"


class EVLayer:
    """Computes audit-grounded per-side EV for a fixture (Req 9.9-9.11, 15).

    Reuses :class:`EVCalculator` de-vig machinery via
    :class:`MarketProbabilityNormalizer` for fair probabilities; the EV itself is
    the standard ``P(model) * odds - 1``.
    """

    def __init__(self, normalizer: Optional[MarketProbabilityNormalizer] = None) -> None:
        self._normalizer = normalizer or MarketProbabilityNormalizer()

    def compute_entry(
        self,
        *,
        market: str,
        book: str,
        side: str,
        line: float,
        pmf: Sequence[float],
        over_odds: float,
        under_odds: float,
    ) -> Optional[PerSideEV]:
        """Compute a single per-side EV entry, or None if inputs are invalid.

        Guards the audit rule: team cards is refused outright (Req 9.11). Invalid
        odds (<= 1.0) yield None (missing/invalid price is not fabricated).
        """
        if not is_per_side_priced_market(market):
            # Never compute per-side EV for a non-priced market (esp. cards).
            return None
        if over_odds <= 1.0 or under_odds <= 1.0:
            return None

        p_over = prob_over_line(pmf, line)
        p_under = 1.0 - p_over
        ev_over = p_over * over_odds - 1.0
        ev_under = p_under * under_odds - 1.0
        return PerSideEV(
            market=market,
            book=book,
            side=side,
            line=line,
            p_over=p_over,
            over_odds=over_odds,
            under_odds=under_odds,
            ev_over=ev_over,
            ev_under=ev_under,
            fair_odds_over=probability_to_fair_odds(p_over),
        )
