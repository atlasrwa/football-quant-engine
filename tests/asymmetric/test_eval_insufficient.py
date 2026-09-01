# Feature: asymmetric-matchup-engine, Property 18: Insufficient-sample exclusion
"""Property 18: Insufficient-sample exclusion (task 9.7).

**Property 18** — For any league-target combination whose within-league sample is
below the minimum required for the significance test, the verdict is
"insufficient-sample", and that combination is excluded from BOTH findings and
artifacts.

Validates: Requirements 8.11.

Two layers of the invariant are checked:
  1. The pure decision logic (``classify_verdict``): whenever
     ``insufficient_sample`` is True, the verdict is "insufficient-sample"
     regardless of the CI/point/flags — so it can never be a finding or artifact.
  2. The end-to-end evaluator: a league whose held-out sample is below
     ``min_within_league`` produces only "insufficient-sample" league cells for
     that league, and those cells appear in neither ``findings()`` nor
     ``artifacts()``.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is a deterministic ``pytest`` test; convert to ``@given(...)`` over
the ``estimates`` strategy plus a below/above-threshold sample-size draw with
``@settings(max_examples=100)`` when task 12.1 lands.
"""

from __future__ import annotations

import itertools

import numpy as np

from src.research.data_source import ResearchMatch
from src.research.asymmetric.evaluation import (
    VERDICT_ARTIFACT,
    VERDICT_FINDING,
    VERDICT_INSUFFICIENT,
    AsymmetryEvaluator,
    classify_verdict,
)
from src.research.asymmetric.profiles import TeamProfiler


_ESTIMATES = [
    (0.05, 0.10),
    (-0.02, 0.10),
    (-0.30, -0.10),
    (0.0, 0.0),
]


def test_insufficient_sample_always_labelled_and_excluded():
    """insufficient_sample=True -> 'insufficient-sample', never finding/artifact."""
    for (ci_lower, point), within_sig, pooled_sig, fdr in itertools.product(
        _ESTIMATES, (True, False), (True, False), (True, False, None)
    ):
        verdict = classify_verdict(
            ci_lower=ci_lower,
            point=point,
            within_league_significant=within_sig,
            pooled_significant=pooled_sig,
            fdr_passed=fdr,
            insufficient_sample=True,
        )
        assert verdict == VERDICT_INSUFFICIENT
        assert verdict != VERDICT_FINDING
        assert verdict != VERDICT_ARTIFACT


def _corpus_with_small_league(seed: int = 0) -> list[ResearchMatch]:
    """Build a corpus with a large league and a tiny second league.

    The tiny league has far fewer than the min-within-league held-out sample, so
    its league-target cells must be labelled insufficient-sample.
    """
    rng = np.random.default_rng(seed)
    big_teams = [f"B{i}" for i in range(10)]
    small_teams = [f"S{i}" for i in range(4)]
    matches: list[ResearchMatch] = []
    mid = 1
    day = 1_600_000_000

    def emit(h, a, league_id):
        nonlocal mid, day
        matches.append(
            ResearchMatch(
                match_id=mid, date_unix=day, league_id=league_id, season="2023",
                home_team=h, away_team=a,
                home_goals=int(rng.poisson(1.4)), away_goals=int(rng.poisson(1.1)),
                corners_home=int(rng.poisson(5)), corners_away=int(rng.poisson(4)),
                shots_on_target_home=int(rng.poisson(4)), shots_on_target_away=int(rng.poisson(3)),
                yellow_cards_home=int(rng.poisson(2)), yellow_cards_away=int(rng.poisson(2)),
                red_cards_home=0, red_cards_away=0,
            )
        )
        mid += 1
        day += 3600 * 12

    for _ in range(70):
        order = list(big_teams)
        rng.shuffle(order)
        for i in range(0, len(order) - 1, 2):
            emit(order[i], order[i + 1], 100)
        # A couple of tiny-league matches only occasionally.
    # Only a handful of small-league matches total (well below the threshold).
    for _ in range(4):
        emit(small_teams[0], small_teams[1], 200)
        emit(small_teams[2], small_teams[3], 200)
    matches.sort(key=lambda m: m.date_unix)
    return matches


def test_evaluator_labels_small_league_insufficient_and_excludes_it():
    matches = _corpus_with_small_league()
    ev = AsymmetryEvaluator(min_within_league=40, bootstrap_draws=50)
    report = ev.evaluate(
        matches,
        TeamProfiler(),
        leagues={100: "Big", 200: "Small"},
        corpus_label="rich",
    )

    small_cells = [c for c in report.comparisons if c.league == "Small"]
    assert small_cells, "expected Small-league comparison cells"
    for c in small_cells:
        assert c.insufficient_sample is True
        assert c.verdict == VERDICT_INSUFFICIENT

    # Excluded from findings and artifacts entirely.
    assert all(c.league != "Small" for c in report.findings())
    assert all(c.league != "Small" for c in report.artifacts())
