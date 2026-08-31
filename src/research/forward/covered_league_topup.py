"""Covered-league bias for the weekly forward top-up.

The binding constraint on growing a *settleable* forward sample is team-history
coverage: a fixture can only be predicted (and later settled) if BOTH teams have
history in the corpus. Broadening the corpus to brand-new leagues costs API
requests and delays the readout, so the top-up policy is:

    Prioritise UPCOMING fixtures in leagues (competitions) that ALREADY have
    corpus coverage. Do not add new leagues.

This module is pure/deterministic given its inputs so it can be unit-tested
without the network. The fetch driver (``pilotC_multibook_fetch``) consumes the
ordered ``match_ids`` it produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


def team_coverage(meta_row: dict, corpus_teams: set[str]) -> int:
    """0, 1, or 2 — how many of the fixture's teams have corpus history."""
    return int(meta_row.get("home") in corpus_teams) + int(
        meta_row.get("away") in corpus_teams
    )


def covered_competitions(meta: dict, corpus_teams: set[str],
                         min_covered_fixtures: int = 1) -> set[str]:
    """Competitions that already have corpus coverage.

    A competition is "covered" if it has at least ``min_covered_fixtures``
    fixtures with BOTH teams in the corpus. These are the leagues we bias
    toward — we do NOT introduce new competitions.
    """
    counts: dict[str, int] = {}
    for row in meta.values():
        if team_coverage(row, corpus_teams) == 2:
            counts[row.get("comp")] = counts.get(row.get("comp"), 0) + 1
    return {c for c, n in counts.items() if n >= min_covered_fixtures and c is not None}


@dataclass
class TopupPlan:
    ordered_match_ids: list[str]
    covered_comps: set[str]
    # counts for reporting
    n_total: int = 0
    n_upcoming_both_covered: int = 0
    n_upcoming_one_covered: int = 0
    n_settle_finished_covered: int = 0
    n_excluded_new_league: int = 0
    n_excluded_past_uncovered: int = 0
    detail: dict = field(default_factory=dict)


def build_topup_plan(
    meta: dict,
    match_ids: list[str],
    corpus_teams: set[str],
    now_ts: float,
    include_partial_cover: bool = True,
) -> TopupPlan:
    """Order fixtures for fetching, biased toward covered-league upcoming games.

    Priority (lowest number fetched first):
      0. UPCOMING, both teams covered, in a covered competition  (settleable soon)
      1. UPCOMING, one team covered, in a covered competition    (partial; optional)
      2. FINISHED/past, both teams covered                       (settle backlog)
    Everything else (uncovered teams, or fixtures in competitions with no corpus
    coverage) is EXCLUDED from the top-up — fetching odds for them would spend
    budget without producing a settleable, predictable sample, and pulling brand
    new leagues is explicitly out of scope.
    """
    covered = covered_competitions(meta, corpus_teams)

    tier0, tier1, tier2 = [], [], []
    n_excluded_new_league = 0
    n_excluded_past_uncovered = 0

    for mid in match_ids:
        row = meta.get(mid, {})
        cov = team_coverage(row, corpus_teams)
        comp = row.get("comp")
        upcoming = row.get("ts", 0) > now_ts
        in_covered_comp = comp in covered

        if not in_covered_comp:
            # Competition has no corpus coverage at all — do not add new leagues.
            n_excluded_new_league += 1
            continue

        if upcoming and cov == 2:
            tier0.append(mid)
        elif upcoming and cov == 1 and include_partial_cover:
            tier1.append(mid)
        elif (not upcoming) and cov == 2:
            tier2.append(mid)  # settle backlog for already-covered finished games
        else:
            n_excluded_past_uncovered += 1

    # Within each tier, upcoming games sorted by soonest kickoff (settle fastest).
    tier0.sort(key=lambda m: meta[m].get("ts", 0))
    tier1.sort(key=lambda m: meta[m].get("ts", 0))
    tier2.sort(key=lambda m: meta[m].get("ts", 0))

    ordered = tier0 + tier1 + tier2
    return TopupPlan(
        ordered_match_ids=ordered,
        covered_comps=covered,
        n_total=len(match_ids),
        n_upcoming_both_covered=len(tier0),
        n_upcoming_one_covered=len(tier1),
        n_settle_finished_covered=len(tier2),
        n_excluded_new_league=n_excluded_new_league,
        n_excluded_past_uncovered=n_excluded_past_uncovered,
        detail={
            "n_covered_competitions": len(covered),
            "tier0_upcoming_both_covered": len(tier0),
            "tier1_upcoming_one_covered": len(tier1),
            "tier2_finished_both_covered": len(tier2),
        },
    )


def project_settleable_sample(
    plan: TopupPlan,
    markets_per_fixture: int,
    weekly_covered_upcoming: Optional[float] = None,
    target_n: int = 385,
) -> dict:
    """Project settleable sample growth under the covered-league bias.

    - ``markets_per_fixture``: predictions produced per fixture (e.g. goals 1.5/2.5/3.5
      + btts = 4). Each becomes a settleable observation once the fixture finishes.
    - ``weekly_covered_upcoming``: expected NEW covered upcoming fixtures per week. If
      not supplied, we use the number of covered upcoming fixtures currently visible
      (tier0) as a one-week proxy — labelled as such (a lower bound, since the fixture
      list only shows a short horizon).
    - ``target_n``: sample size deemed "meaningfully powered". Default 385 is the
      classic n for a +/-5% margin at 95% confidence on a proportion (worst case
      p=0.5) — a deliberately conservative, pre-registered anchor, PER market/line.

    Returns projected per-week settleable predictions and the number of weeks to
    reach ``target_n`` for a single market/line, with explicit caveats.
    """
    tier0 = plan.n_upcoming_both_covered
    weekly_fixtures = (
        weekly_covered_upcoming if weekly_covered_upcoming is not None else float(tier0)
    )
    weekly_predictions = weekly_fixtures * markets_per_fixture
    # Per market/line, one observation per fixture per week.
    weekly_per_market = weekly_fixtures
    weeks_to_power = (
        None if weekly_per_market <= 0 else target_n / weekly_per_market
    )
    return {
        "markets_per_fixture": markets_per_fixture,
        "covered_upcoming_fixtures_visible_now": tier0,
        "assumed_weekly_covered_upcoming_fixtures": weekly_fixtures,
        "projected_weekly_settleable_predictions": weekly_predictions,
        "projected_weekly_settleable_per_market_line": weekly_per_market,
        "target_n_per_market_line": target_n,
        "estimated_weeks_to_power_per_market_line": (
            round(weeks_to_power, 1) if weeks_to_power is not None else None
        ),
        "caveats": [
            "weekly rate is a proxy from the currently-visible fixture horizon; "
            "true weekly covered-fixture inflow may differ.",
            "target_n is per market/line; the multiple-testing family (see "
            "pre-registration) requires each tested cell to reach n independently.",
            "settleable != edge; reaching n only enables a conclusion, it does not "
            "imply one.",
        ],
    }
