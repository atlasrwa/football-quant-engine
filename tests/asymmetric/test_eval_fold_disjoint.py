# Feature: asymmetric-matchup-engine, Property 12: Out-of-sample fold disjointness
"""Property 12: Out-of-sample fold disjointness (task 9.4).

**Property 12** — For every generated walk-forward fold, the set of fixture
identifiers used to FIT a model for that fold is disjoint from the set of fixture
identifiers used to SCORE it.

Validates: Requirements 8.2, 11.2.

The AsymmetryEvaluator fits on each fold's TRAIN window
``[train_start, train_end)`` and scores on the fold's TEST window
``[test_start, test_end)``. The FoldGenerator enforces strict chronological
ordering ``train_end <= (gap) <= test_start``, so the two windows are temporally
disjoint and therefore the fixture-id sets are disjoint. This test builds a
chronological corpus, generates the same folds the evaluator uses (via the
evaluator's own ``_build_folds`` / ``_auto_config``), partitions the fixtures the
same way ``evaluate`` does, and asserts the fit/score id sets never intersect.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is a deterministic ``pytest`` test sweeping several corpus sizes and
league mixes, exercising the same invariant a Hypothesis strategy would over
generated ``match_histories``. When task 12.1 lands, convert the corpus-size /
league-mix sweep to ``@given(...)`` over the ``match_histories`` strategy with
``@settings(max_examples=100)``; the per-fold disjointness assertion below maps
directly onto each generated example.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.research.data_source import ResearchMatch
from src.research.asymmetric.evaluation import AsymmetryEvaluator


def _corpus(n_weeks: int, n_teams: int, n_leagues: int, seed: int) -> list[ResearchMatch]:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(n_teams)]
    matches: list[ResearchMatch] = []
    mid = 1
    day = 1_600_000_000
    for _ in range(n_weeks):
        order = list(teams)
        rng.shuffle(order)
        for i in range(0, len(order) - 1, 2):
            h, a = order[i], order[i + 1]
            matches.append(
                ResearchMatch(
                    match_id=mid,
                    date_unix=day,
                    league_id=100 + (mid % n_leagues),
                    season="2023",
                    home_team=h,
                    away_team=a,
                    home_goals=int(rng.poisson(1.4)),
                    away_goals=int(rng.poisson(1.1)),
                    corners_home=int(rng.poisson(5)),
                    corners_away=int(rng.poisson(4)),
                    shots_on_target_home=int(rng.poisson(4)),
                    shots_on_target_away=int(rng.poisson(3)),
                    yellow_cards_home=int(rng.poisson(2)),
                    yellow_cards_away=int(rng.poisson(2)),
                    red_cards_home=0,
                    red_cards_away=0,
                )
            )
            mid += 1
            day += 3600 * 24
    return matches


@pytest.mark.parametrize(
    "n_weeks,n_teams,n_leagues,seed",
    [
        (40, 10, 1, 0),
        (60, 12, 2, 1),
        (52, 8, 2, 2),
        (80, 14, 3, 3),
    ],
)
def test_fit_and_score_fixture_ids_are_disjoint(n_weeks, n_teams, n_leagues, seed):
    matches = _corpus(n_weeks, n_teams, n_leagues, seed)
    completed = sorted(
        [m for m in matches if m.home_goals is not None and m.away_goals is not None],
        key=lambda m: m.date_unix,
    )

    ev = AsymmetryEvaluator(min_within_league=20, bootstrap_draws=50)
    folds = ev._build_folds(completed)
    assert folds, "expected at least one walk-forward fold"

    for fold in folds:
        train_ids = {
            m.match_id
            for m in completed
            if fold.train_start <= m.date_unix < fold.train_end
        }
        test_ids = {
            m.match_id
            for m in completed
            if fold.test_start <= m.date_unix < fold.test_end
        }
        # The core invariant: no fixture used to fit is used to score.
        assert train_ids.isdisjoint(test_ids), (
            f"fold {fold.fold_index}: {len(train_ids & test_ids)} overlapping ids"
        )
        # And the fold's own temporal ordering must be valid (train before test).
        valid, msg = fold.validate_temporal_order()
        assert valid, msg
        assert fold.train_end <= fold.test_start
