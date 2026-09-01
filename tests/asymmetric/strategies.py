"""Custom Hypothesis strategies for the Asymmetric Matchup Engine tests.

These strategies drive the property-based tests (Req 5, 6, 11 verification and
the design's Testing Strategy). Each is documented against the properties it
feeds:

    * ``match_histories``      — chronologically ordered ``ResearchMatch`` lists
                                 with configurable field-presence, league mix,
                                 home/away roles, per-team counts
                                 (Properties 2, 3, 8, 11, 12).
    * ``count_pmfs``           — valid probability mass functions over small
                                 count supports (Properties 4, 6, 7).
    * ``fixture_contexts``     — attacker/defender profile pairs with controllable
                                 divergence and referee presence (Properties 1, 5).
    * ``estimates``            — ``(point, ci_low, ci_high)`` triples spanning and
                                 not spanning zero (Properties 15, 16, 17, 18).
    * ``fetch_cost_sequences`` — sequences of non-negative fetch costs against a
                                 cap (Property 22).

Added as part of task 12.1 (the ``hypothesis`` dev-dependency); imported by the
property tests via ``from tests.asymmetric.strategies import ...`` (``pythonpath
= ["."]`` makes the repo root importable).
"""

from __future__ import annotations

from typing import Optional

from hypothesis import strategies as st

from src.research.asymmetric.models import (
    AttackingProfile,
    DefensiveProfile,
    Estimate,
    ProfileDimension,
    TeamMatchProfiles,
)
from src.research.data_source import ResearchMatch

# ─────────────────────────────────────────────────────────────────────────────
# match_histories (Properties 2, 3, 8, 11, 12)
# ─────────────────────────────────────────────────────────────────────────────
_TEAMS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]


@st.composite
def match_histories(
    draw,
    *,
    min_matches: int = 3,
    max_matches: int = 12,
    teams: Optional[list[str]] = None,
    leagues: tuple[int, ...] = (1, 2),
    allow_missing_fields: bool = False,
) -> list[ResearchMatch]:
    """Generate a chronologically ordered list of completed ``ResearchMatch``.

    Teams are drawn from a small pool so the same team recurs (home and away)
    across the history — the aggregation-key semantics the profiler relies on.
    Leagues are mixed across the given ids. Dates are strictly increasing so the
    list is already chronological. When ``allow_missing_fields`` is True some
    per-match raw fields may be ``None`` (NULL != ZERO), exercising missing-field
    exclusion (Property 11).
    """
    pool = teams or _TEAMS
    n = draw(st.integers(min_value=min_matches, max_value=max_matches))

    counts = st.integers(min_value=0, max_value=9)
    floats = st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False)

    def maybe(strat):
        if not allow_missing_fields:
            return draw(strat)
        return draw(st.one_of(st.none(), strat))

    matches: list[ResearchMatch] = []
    date = 1_000
    for i in range(n):
        home = draw(st.sampled_from(pool))
        away = draw(st.sampled_from([t for t in pool if t != home]))
        league = draw(st.sampled_from(leagues))
        date += draw(st.integers(min_value=1, max_value=100))
        matches.append(
            ResearchMatch(
                match_id=i + 1,
                date_unix=date,
                league_id=league,
                season="s",
                home_team=home,
                away_team=away,
                home_goals=draw(counts),
                away_goals=draw(counts),
                corners_home=maybe(counts),
                corners_away=maybe(counts),
                shots_on_target_home=maybe(counts),
                shots_on_target_away=maybe(counts),
                fouls_home=maybe(counts),
                fouls_away=maybe(counts),
                yellow_cards_home=maybe(counts),
                yellow_cards_away=maybe(counts),
                red_cards_home=draw(st.integers(min_value=0, max_value=2)),
                red_cards_away=draw(st.integers(min_value=0, max_value=2)),
                attacks_home=maybe(st.integers(min_value=0, max_value=150)),
                attacks_away=maybe(st.integers(min_value=0, max_value=150)),
                dangerous_attacks_home=maybe(st.integers(min_value=0, max_value=80)),
                dangerous_attacks_away=maybe(st.integers(min_value=0, max_value=80)),
                home_xg=maybe(floats),
                away_xg=maybe(floats),
            )
        )
    return matches


# ─────────────────────────────────────────────────────────────────────────────
# count_pmfs (Properties 4, 6, 7)
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def count_pmfs(draw, *, min_support: int = 1, max_support: int = 10) -> tuple[float, ...]:
    """Generate a valid PMF over a small count support (entries >=0, sum to 1)."""
    size = draw(st.integers(min_value=min_support, max_value=max_support))
    weights = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=size,
            max_size=size,
        )
    )
    total = sum(weights)
    if total <= 0.0:
        # Degenerate all-zero draw -> put all mass at 0 (a valid PMF).
        pmf = [0.0] * size
        pmf[0] = 1.0
        return tuple(pmf)
    return tuple(w / total for w in weights)


# ─────────────────────────────────────────────────────────────────────────────
# fixture_contexts (Properties 1, 5)
# ─────────────────────────────────────────────────────────────────────────────
def _dim(name: str, value: float) -> ProfileDimension:
    return ProfileDimension(
        name=name, value=value, source_fields=(name,), n_matches_used=5
    )


_ATT_NAMES = ("width", "central_penetration", "volume_vs_quality",
              "set_piece_reliance", "directness")
_DEF_NAMES = ("block_orientation", "aerial_vs_ground", "shot_suppression",
              "gk_contribution", "discipline")


@st.composite
def _team_profiles(draw, team: str, *, n_history: int = 8) -> TeamMatchProfiles:
    vals = st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
    att = AttackingProfile(
        team=team,
        as_of_unix=1_000,
        **{name: _dim(name, draw(vals)) for name in _ATT_NAMES},
    )
    dfn = DefensiveProfile(
        team=team,
        as_of_unix=1_000,
        **{name: _dim(name, draw(vals)) for name in _DEF_NAMES},
    )
    return TeamMatchProfiles(
        team=team,
        n_history=n_history,
        insufficient=n_history < 5,
        attacking=att,
        defensive=dfn,
    )


@st.composite
def fixture_contexts(draw):
    """Generate a pair of (home, away) ``TeamMatchProfiles`` plus referee info.

    Returns ``(home_profiles, away_profiles, referee_present)``. The two profiles
    are drawn independently so they usually differ (Property 1 divergence);
    ``referee_present`` toggles the cards substitution path (Property 5).
    """
    home = draw(_team_profiles("HomeTeam"))
    away = draw(_team_profiles("AwayTeam"))
    referee_present = draw(st.booleans())
    return home, away, referee_present


# ─────────────────────────────────────────────────────────────────────────────
# estimates (Properties 15, 16, 17, 18)
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def estimates(draw) -> Estimate:
    """Generate an ``Estimate`` whose CI both spans and does not span zero.

    Draws a lower bound and a non-negative width so ``ci_low <= point <=
    ci_high`` always holds; the sign of ``ci_low`` and the width together produce
    CIs that span zero and CIs that do not, exercising the suppression rule
    (Property 15) and the verdict logic (16, 17, 18).
    """
    lo = draw(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    width = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    hi = lo + width
    point = draw(
        st.floats(min_value=lo, max_value=hi, allow_nan=False, allow_infinity=False)
    )
    return Estimate(point=point, ci_low=lo, ci_high=hi)


# ─────────────────────────────────────────────────────────────────────────────
# fetch_cost_sequences (Property 22)
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def fetch_cost_sequences(draw) -> tuple[list[float], float]:
    """Generate ``(costs, cap)``: a list of non-negative fetch costs and a cap.

    Costs are non-negative floats; the cap is a non-negative float that may be
    below, within, or above the cumulative cost so the refuse/admit boundary is
    exercised from both sides (Property 22).
    """
    costs = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=12,
        )
    )
    cap = draw(st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False))
    return costs, cap
