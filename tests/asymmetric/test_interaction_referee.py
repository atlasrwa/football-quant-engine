# Feature: asymmetric-matchup-engine, Property 5: Referee substitution and flagging for cards
"""Property 5: Referee substitution and flagging for cards (task 5.4).

**Property 5** — For any fixture, the cards Per_Side_Target uses the referee
expanding-window card rate when a sufficiently-observed referee is assigned
(BACKTEST mode), and otherwise substitutes the league-level expanding-window card
rate and sets ``referee_substituted = True``; the substituted prediction equals
the prediction produced by conditioning on the league rate. Additionally, the
pre-match / CLI mode ALWAYS uses the league rate (``referee_substituted = True``)
per Req 16.3.

Validates: Requirements 2.7, 2.11 (and audit-grounded Req 16.1-16.4).

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test over hand-built
histories exercising both the sufficiently-observed-referee and missing/thin
referee branches, plus the pre-match invariant. When task 12.1 lands, convert to
``@given`` drawing referee-presence and observation-count sequences with
``@settings(max_examples=100)``.
"""

from __future__ import annotations

import pytest

from src.research.asymmetric.interaction import (
    ConditioningMode,
    RefereeCardRate,
)
from src.research.data_source import ResearchMatch

LEAGUE = 100


def _match(mid: int, day: int, referee, yc_h, yc_a) -> ResearchMatch:
    """Build a completed match with a given referee and card totals."""
    return ResearchMatch(
        match_id=mid,
        date_unix=1_600_000_000 + day * 86_400,
        league_id=LEAGUE,
        season="2023",
        home_team=f"H{mid}",
        away_team=f"A{mid}",
        home_goals=1,
        away_goals=1,
        yellow_cards_home=yc_h,
        yellow_cards_away=yc_a,
        red_cards_home=0,
        red_cards_away=0,
        total_cards=yc_h + yc_a,
        referee=referee,
    )


def test_backtest_uses_referee_rate_when_sufficiently_observed():
    """BACKTEST: a referee with >= min prior matches gets a referee-specific rate."""
    rc = RefereeCardRate(min_referee_matches=5)
    # Referee "REF" officiates many high-card matches; league is otherwise low.
    matches = []
    day = 0
    # 6 prior REF matches with 8 cards each.
    for i in range(6):
        matches.append(_match(1000 + i, day, "REF", 5, 3))
        day += 1
    # Some other-referee low-card league matches interleaved earlier are not
    # needed; add a couple to move the league rate away from the referee rate.
    for i in range(4):
        matches.append(_match(2000 + i, day, "OTHER", 1, 1))
        day += 1
    # The target match, officiated by REF (now with >=5 prior obs).
    target = _match(9999, day, "REF", 4, 4)
    matches.append(target)

    results = rc.compute_rates(matches, mode=ConditioningMode.BACKTEST)
    res = results[9999]

    assert res.referee_substituted is False
    assert res.referee_rate is not None
    # REF's prior 6 matches were all 8 cards -> referee rate 8.0.
    assert res.referee_rate == pytest.approx(8.0)
    assert res.rate == pytest.approx(8.0)
    # League rate differs (mix of 8s and 2s) -> substitution really was avoided.
    assert res.league_rate != pytest.approx(res.referee_rate)


def test_backtest_substitutes_league_rate_when_referee_thin():
    """BACKTEST: an insufficiently-observed referee falls back to league rate."""
    rc = RefereeCardRate(min_referee_matches=5)
    matches = []
    day = 0
    for i in range(8):
        matches.append(_match(3000 + i, day, "COMMON", 2, 2))  # 4 cards each
        day += 1
    # Target officiated by a NEW referee with 0 prior obs -> substitute league.
    target = _match(9999, day, "NEWREF", 3, 3)
    matches.append(target)

    results = rc.compute_rates(matches, mode=ConditioningMode.BACKTEST)
    res = results[9999]

    assert res.referee_substituted is True
    assert res.referee_rate is None
    # League rate is 4.0 (8 prior matches at 4 cards).
    assert res.league_rate == pytest.approx(4.0)
    assert res.rate == pytest.approx(res.league_rate)


def test_backtest_missing_referee_substitutes_league_rate():
    """BACKTEST: a match with no referee id uses the league rate and flags it."""
    rc = RefereeCardRate(min_referee_matches=5)
    matches = []
    day = 0
    for i in range(5):
        matches.append(_match(4000 + i, day, "R", 3, 1))  # 4 cards each
        day += 1
    target = _match(9999, day, None, 2, 2)  # no referee assigned
    matches.append(target)

    res = rc.compute_rates(matches, mode=ConditioningMode.BACKTEST)[9999]
    assert res.referee_substituted is True
    assert res.referee_rate is None
    assert res.rate == pytest.approx(res.league_rate)


def test_pre_match_always_uses_league_rate_and_flags_substituted():
    """PRE_MATCH / CLI: league rate ALWAYS, referee_substituted always True (Req 16.3)."""
    rc = RefereeCardRate(min_referee_matches=5)
    matches = []
    day = 0
    # Even with a heavily-observed referee, PRE_MATCH must ignore it.
    for i in range(10):
        matches.append(_match(5000 + i, day, "REF", 6, 4))  # 10 cards each
        day += 1
    target = _match(9999, day, "REF", 5, 5)
    matches.append(target)

    res = rc.compute_rates(matches, mode=ConditioningMode.PRE_MATCH)[9999]
    assert res.referee_substituted is True
    assert res.referee_rate is None
    assert res.rate == pytest.approx(res.league_rate)


def test_substituted_prediction_equals_league_rate_conditioning():
    """The substituted rate equals the pure league-rate value (Property 5 equality).

    Compute the league-rate-only value via PRE_MATCH and compare it to the
    substituted value produced by BACKTEST when the referee is too thin — they
    must be identical (the substitution conditions on exactly the league rate).
    """
    rc = RefereeCardRate(min_referee_matches=5)
    matches = []
    day = 0
    for i in range(7):
        matches.append(_match(6000 + i, day, "COMMON", 2, 3))  # 5 cards each
        day += 1
    target = _match(9999, day, "RARE", 1, 1)  # RARE has 0 prior obs
    matches.append(target)

    league_only = rc.compute_rates(matches, mode=ConditioningMode.PRE_MATCH)[9999]
    backtest_sub = rc.compute_rates(matches, mode=ConditioningMode.BACKTEST)[9999]

    assert backtest_sub.referee_substituted is True
    assert backtest_sub.rate == pytest.approx(league_only.rate)
    assert backtest_sub.rate == pytest.approx(backtest_sub.league_rate)


def test_look_ahead_free_only_prior_matches_count():
    """The rate for a match uses only STRICTLY PRIOR matches (look-ahead free)."""
    rc = RefereeCardRate(min_referee_matches=5)
    # First match has no prior history -> league rate 0.0.
    m1 = _match(1, 0, "REF", 5, 5)
    m2 = _match(2, 1, "REF", 0, 0)
    res = rc.compute_rates([m1, m2], mode=ConditioningMode.PRE_MATCH)
    assert res[1].rate == pytest.approx(0.0)  # nothing before it
    # m2's league rate reflects only m1 (10 cards) -> 10.0.
    assert res[2].rate == pytest.approx(10.0)


def test_rate_for_prediction_pre_match_uses_league_only():
    """The single-fixture CLI path mirrors PRE_MATCH league-only behaviour."""
    rc = RefereeCardRate(min_referee_matches=5)
    history = [
        _match(7000 + i, i, "REF", 3, 3) for i in range(6)  # 6 cards each
    ]
    target_ts = 1_600_000_000 + 100 * 86_400
    res = rc.rate_for_prediction(
        LEAGUE, target_ts, history, referee="REF", mode=ConditioningMode.PRE_MATCH
    )
    assert res.referee_substituted is True
    assert res.referee_rate is None
    assert res.rate == pytest.approx(6.0)  # league rate over the 6 prior matches


def test_rate_for_prediction_backtest_uses_referee_when_observed():
    """The single-fixture BACKTEST path uses a referee rate when observed."""
    rc = RefereeCardRate(min_referee_matches=5)
    # 6 REF matches (8 cards) and some non-REF league matches (2 cards).
    history = [_match(8000 + i, i, "REF", 4, 4) for i in range(6)]
    history += [_match(8100 + i, 10 + i, "OTHER", 1, 1) for i in range(4)]
    target_ts = 1_600_000_000 + 100 * 86_400
    res = rc.rate_for_prediction(
        LEAGUE, target_ts, history, referee="REF", mode=ConditioningMode.BACKTEST
    )
    assert res.referee_substituted is False
    assert res.referee_rate == pytest.approx(8.0)
    assert res.rate == pytest.approx(8.0)
