"""Permanent sanity gate: engine expected totals must track observed base rates.

Regression guard for the pre-merge blocker where the per-fixture readout emitted
E[total goals] ~5.3 and E[total corners] ~14 for a Championship fixture — roughly
double reality — because ``DirectionalCountModel`` shrank its profile-feature
inputs at FIT time but not at PREDICT time (train/predict feature-scale
mismatch). The fix makes the shrinkage transform symmetric across fit and
predict; this test locks the behaviour in so it cannot silently regress.

What it checks (the minimum honesty bar the reviewer required):
    For each covered league in the cached Rich corpus and each count market
    (goals, corners, cards), the MEAN predicted match total over a held-out slice
    of fixtures must sit close to the MEAN OBSERVED total on the same fixtures.
    "Close" = within ``TOLERANCE`` relative error. A 2x-style regression (the
    original bug) blows through this bar immediately.

Discipline:
    * Zero-API: loads the cached corpus only; never fetches.
    * Point-in-time: fits on the earlier slice, predicts each held-out fixture
      from history strictly before it, exactly as the CLI / evaluator do.
    * If the cached corpus is unavailable (e.g. CI without the data snapshot) the
      test SKIPS rather than failing spuriously.
"""
from __future__ import annotations

import collections
import statistics

import pytest

from src.research.asymmetric.corpus import RichCorpusLoader
from src.research.asymmetric.derived import DerivedOutcomeCombiner, pmf_mean
from src.research.asymmetric.interaction import (
    FixtureContext,
    InteractionModel,
    RefereeCardRate,
    build_training_observations,
)
from src.research.asymmetric.profiles import TeamProfiler

#: Relative-error band on the aggregate predicted-vs-observed match total, per
#: league/market. Empirically the fixed engine lands within ~11% across all three
#: cached leagues and all three markets; 0.25 leaves headroom for fold/seed
#: variation while still catching a ~2x miscalibration (the original bug).
TOLERANCE = 0.25

#: Cap the number of held-out fixtures scored per league (keeps the test fast;
#: 120 is comfortably enough for a stable aggregate mean).
MAX_TEST_FIXTURES = 120

#: Minimum scored fixtures for a league/market cell to be asserted (below this the
#: aggregate mean is too noisy to gate on).
MIN_SCORED = 25

_COUNT_MARKETS = ("goals", "corners", "cards")


def _load_corpus():
    try:
        loaded = RichCorpusLoader().load()
    except Exception:  # pragma: no cover - cache may be absent in some envs
        return None
    return [(lm.match, lm.league) for lm in loaded]


def _observed_total(match, market):
    if market == "goals":
        if match.home_goals is None or match.away_goals is None:
            return None
        return match.home_goals + match.away_goals
    if market == "corners":
        if match.corners_home is None or match.corners_away is None:
            return None
        return match.corners_home + match.corners_away
    if market == "cards":
        parts = [
            c for c in (
                match.yellow_cards_home, match.yellow_cards_away,
                match.red_cards_home, match.red_cards_away,
            ) if c is not None
        ]
        return sum(parts) if parts else None
    raise AssertionError(market)


def _predicted_total(derived, market):
    return {
        "goals": pmf_mean(derived.total_goals),
        "corners": pmf_mean(derived.total_corners),
        "cards": pmf_mean(derived.total_cards),
    }[market]


def _score_league(league_matches):
    """Return {market: (mean_predicted, mean_observed, n)} for one league."""
    ms = sorted(
        [m for m in league_matches if m.home_goals is not None],
        key=lambda m: m.date_unix,
    )
    if len(ms) < 200:
        return {}
    cut = int(len(ms) * 0.7)
    train, test = ms[:cut], ms[cut:]
    profiler = TeamProfiler(min_history=5)
    model = InteractionModel()
    model.fit(build_training_observations(train, profiler))
    ref = RefereeCardRate()
    combiner = DerivedOutcomeCombiner()
    history = sorted(train + test, key=lambda m: m.date_unix)

    pred = collections.defaultdict(list)
    obs = collections.defaultdict(list)
    for fx in test[:MAX_TEST_FIXTURES]:
        as_of = fx.date_unix
        hp = profiler.profile_for_team_at(fx.home_team, as_of, history)
        ap = profiler.profile_for_team_at(fx.away_team, as_of, history)
        if hp.n_history == 0 or ap.n_history == 0:
            continue
        rate = ref.rate_for_prediction(fx.league_id, as_of, history).rate
        ctx = FixtureContext(
            home_team=fx.home_team, away_team=fx.away_team, date_unix=as_of,
            home_profiles=hp, away_profiles=ap, league_id=fx.league_id,
            card_rate_home=rate, card_rate_away=rate,
        )
        derived = combiner.combine(model.predict_fixture(ctx))
        for market in _COUNT_MARKETS:
            o = _observed_total(fx, market)
            if o is None:
                continue
            pred[market].append(_predicted_total(derived, market))
            obs[market].append(float(o))

    return {
        market: (statistics.mean(pred[market]), statistics.mean(obs[market]), len(pred[market]))
        for market in _COUNT_MARKETS
        if pred[market] and obs[market]
    }


@pytest.fixture(scope="module")
def scored_by_league():
    corpus = _load_corpus()
    if not corpus:
        pytest.skip("cached Rich corpus unavailable; expected-totals sanity skipped")
    by_league = collections.defaultdict(list)
    for match, label in corpus:
        by_league[label].append(match)
    results = {lbl: _score_league(ms) for lbl, ms in by_league.items()}
    # Keep only leagues that produced any scored cells.
    return {lbl: cells for lbl, cells in results.items() if cells}


def test_at_least_one_covered_league_scored(scored_by_league):
    assert scored_by_league, "no covered league produced scored fixtures"


@pytest.mark.parametrize("market", _COUNT_MARKETS)
def test_expected_totals_track_observed_base_rates(scored_by_league, market):
    """Mean predicted total ≈ mean observed total, per league, within tolerance.

    This is the guard against the doubled-goals blocker: a ~2x inflation makes the
    relative error ~1.0, far outside TOLERANCE.
    """
    checked = 0
    failures = []
    for league, cells in scored_by_league.items():
        if market not in cells:
            continue
        mean_pred, mean_obs, n = cells[market]
        if n < MIN_SCORED or mean_obs <= 0:
            continue
        checked += 1
        rel_err = abs(mean_pred - mean_obs) / mean_obs
        if rel_err > TOLERANCE:
            failures.append(
                f"{league}/{market}: predicted {mean_pred:.2f} vs observed "
                f"{mean_obs:.2f} (rel err {rel_err:.0%} > {TOLERANCE:.0%}, n={n})"
            )
    if checked == 0:
        pytest.skip(f"no league had >= {MIN_SCORED} scored {market} fixtures")
    assert not failures, "expected totals drifted from observed base rates:\n" + "\n".join(failures)
