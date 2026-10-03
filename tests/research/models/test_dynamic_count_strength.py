"""Adversarial tests for QFE V2 dynamic hierarchical count baseline."""

from __future__ import annotations

import math

import pytest

from src.research.data_source import ResearchMatch
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
    poisson_count_nll,
)


DAY = 86400
BASE = 1_700_000_000


def _match(
    *,
    ref: int,
    kickoff: int,
    home: int,
    away: int,
    comp: int = 1,
    season: int = 1,
    goals: tuple[int, int] = (1, 1),
    corners: tuple[int | None, int | None] = (5, 4),
    **overrides,
) -> ResearchMatch:
    values = dict(
        match_id=ref,
        date_unix=kickoff,
        league_id=comp,
        season=f"sn_{season}",
        home_team=f"Team {home}",
        away_team=f"Team {away}",
        source_provider="THESTATSAPI",
        source_match_ref=f"mt_{ref}",
        competition_ref=f"comp_{comp}",
        season_ref=f"sn_{season}",
        home_team_ref=f"tm_{home}",
        away_team_ref=f"tm_{away}",
        home_team_id=home,
        away_team_id=away,
        home_goals=goals[0],
        away_goals=goals[1],
        total_goals=sum(goals),
        corners_home=corners[0],
        corners_away=corners[1],
        total_corners=(
            None
            if corners[0] is None or corners[1] is None
            else corners[0] + corners[1]
        ),
    )
    values.update(overrides)
    return ResearchMatch(**values)


def test_cold_start_is_shrunk_to_declared_global_prior() -> None:
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET)
    forecast = model.forecast(
        _match(ref=1, kickoff=BASE, home=1, away=2)
    )
    assert forecast.lambda_home == pytest.approx(GOALS_TARGET.initial_home_rate)
    assert forecast.lambda_away == pytest.approx(GOALS_TARGET.initial_away_rate)
    assert forecast.effective_support == 0.0
    assert forecast.supported is False


def test_same_kickoff_batch_cannot_leak_one_result_into_another() -> None:
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET)
    a = _match(
        ref=1,
        kickoff=BASE,
        home=1,
        away=2,
        goals=(8, 0),
    )
    b = _match(
        ref=2,
        kickoff=BASE,
        home=1,
        away=3,
        goals=(0, 0),
    )
    fa, fb = model.process_batch([a, b])
    assert fa.lambda_home == pytest.approx(fb.lambda_home)
    assert fa.lambda_home == pytest.approx(GOALS_TARGET.initial_home_rate)

    later = model.forecast(
        _match(ref=3, kickoff=BASE + DAY, home=1, away=4)
    )
    assert later.lambda_home > GOALS_TARGET.initial_home_rate


def test_strong_scoring_history_moves_future_attack_but_is_shrunk() -> None:
    model = DynamicHierarchicalCountBaseline(
        GOALS_TARGET,
        DynamicCountConfig(
            team_global_prior_weight=8.0,
            team_comp_prior_weight=4.0,
            min_effective_team_support=1.0,
        ),
    )
    for i in range(6):
        model.process_batch(
            [
                _match(
                    ref=i + 1,
                    kickoff=BASE + i * 7 * DAY,
                    home=1,
                    away=2,
                    goals=(4, 0),
                )
            ]
        )

    forecast = model.forecast(
        _match(
            ref=100,
            kickoff=BASE + 7 * 7 * DAY,
            home=1,
            away=2,
        )
    )
    assert forecast.trace.home_attack_rate > forecast.trace.competition_home_rate
    assert forecast.lambda_home > forecast.trace.competition_home_rate
    assert forecast.trace.home_attack_rate < 4.0
    assert forecast.supported is True


def test_new_competition_resets_comp_specific_support_but_carries_global_team_signal() -> None:
    model = DynamicHierarchicalCountBaseline(
        GOALS_TARGET,
        DynamicCountConfig(
            team_global_prior_weight=4.0,
            team_comp_prior_weight=6.0,
        ),
    )
    for i in range(8):
        model.process_batch(
            [
                _match(
                    ref=i + 1,
                    kickoff=BASE + i * 7 * DAY,
                    home=1,
                    away=20 + i,
                    comp=1,
                    goals=(3, 0),
                )
            ]
        )

    promoted = model.forecast(
        _match(
            ref=50,
            kickoff=BASE + 9 * 7 * DAY,
            home=1,
            away=99,
            comp=2,
            season=2,
        )
    )
    assert promoted.trace.home_attack_support == 0.0
    assert promoted.trace.home_attack_rate > promoted.trace.competition_home_rate
    assert promoted.effective_support == 0.0
    assert promoted.supported is False


def test_long_time_gap_decays_team_influence_toward_priors() -> None:
    config = DynamicCountConfig(
        half_life_days=30.0,
        team_global_prior_weight=4.0,
        team_comp_prior_weight=3.0,
    )
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET, config)
    for i in range(4):
        model.process_batch(
            [
                _match(
                    ref=i + 1,
                    kickoff=BASE + i * 7 * DAY,
                    home=1,
                    away=10 + i,
                    goals=(5, 0),
                )
            ]
        )

    near = model.forecast(
        _match(ref=20, kickoff=BASE + 5 * 7 * DAY, home=1, away=50)
    )
    far = model.forecast(
        _match(ref=21, kickoff=BASE + 365 * DAY, home=1, away=51)
    )
    near_gap = near.trace.home_attack_rate - near.trace.competition_home_rate
    far_gap = far.trace.home_attack_rate - far.trace.competition_home_rate
    assert near_gap > 0
    assert abs(far_gap) < abs(near_gap)


def test_missing_corner_outcome_does_not_update_corner_state() -> None:
    model = DynamicHierarchicalCountBaseline(CORNERS_TARGET)
    missing = _match(
        ref=1,
        kickoff=BASE,
        home=1,
        away=2,
        corners=(None, None),
    )
    model.process_batch([missing])
    later = model.forecast(
        _match(ref=2, kickoff=BASE + DAY, home=1, away=3)
    )
    assert later.trace.home_attack_support == 0.0
    assert later.lambda_home == pytest.approx(CORNERS_TARGET.initial_home_rate)


def test_extra_time_fixture_does_not_update_regulation_target_state() -> None:
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET)
    cup = _match(
        ref=1,
        kickoff=BASE,
        home=1,
        away=2,
        goals=(3, 2),
        extra_time_home_goals=1,
        extra_time_away_goals=0,
    )
    model.process_batch([cup])
    later = model.forecast(
        _match(ref=2, kickoff=BASE + DAY, home=1, away=3)
    )
    assert later.trace.home_attack_support == 0.0


def test_walk_forward_is_deterministic_for_reordered_input() -> None:
    rows = [
        _match(ref=1, kickoff=BASE, home=1, away=2, goals=(2, 0)),
        _match(ref=2, kickoff=BASE + DAY, home=2, away=3, goals=(1, 1)),
        _match(ref=3, kickoff=BASE + 2 * DAY, home=1, away=3, goals=(3, 1)),
    ]
    a = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(rows)
    b = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
        list(reversed(rows))
    )
    assert [
        (x.fixture_key, x.lambda_home, x.lambda_away)
        for x in a
    ] == [
        (x.fixture_key, x.lambda_home, x.lambda_away)
        for x in b
    ]


def test_integer_line_preserves_push_probability() -> None:
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET)
    f = model.forecast(_match(ref=1, kickoff=BASE, home=1, away=2))
    over = f.probability_over(2.0)
    under = f.probability_under(2.0)
    push = f.push_probability(2.0)
    assert over + under + push == pytest.approx(1.0)


def test_half_line_is_binary_probability_partition() -> None:
    model = DynamicHierarchicalCountBaseline(GOALS_TARGET)
    f = model.forecast(_match(ref=1, kickoff=BASE, home=1, away=2))
    assert f.probability_over(2.5) + f.probability_under(2.5) == pytest.approx(1.0)


def test_quarter_line_probability_requires_split_settlement_layer() -> None:
    f = DynamicHierarchicalCountBaseline(GOALS_TARGET).forecast(
        _match(ref=1, kickoff=BASE, home=1, away=2)
    )
    with pytest.raises(ValueError):
        f.probability_over(2.25)


def test_poisson_nll_is_finite_and_prefers_rate_near_observation() -> None:
    good = poisson_count_nll(2, 2.0)
    bad = poisson_count_nll(2, 8.0)
    assert math.isfinite(good)
    assert good < bad


def test_walk_forward_respects_prediction_cutoff_and_result_embargo() -> None:
    # Source result is only 8h before the target kickoff. Under the registered
    # 6h prediction horizon + 6h availability embargo it is NOT yet available
    # at the target prediction cutoff and must not influence the forecast.
    source = _match(
        ref=201,
        kickoff=BASE,
        home=1,
        away=2,
        goals=(8, 0),
    )
    target = _match(
        ref=202,
        kickoff=BASE + 8 * 3600,
        home=1,
        away=2,
        goals=(0, 0),
    )
    forecasts = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
        [source, target],
        decision_horizon_seconds=6 * 3600,
        availability_embargo_seconds=6 * 3600,
    )
    assert forecasts[1].lambda_home == pytest.approx(
        GOALS_TARGET.initial_home_rate
    )
    assert forecasts[1].effective_support == 0.0


def test_walk_forward_admits_result_at_exact_availability_cutoff_equality() -> None:
    # Source kickoff + 6h == target kickoff - 6h when kickoffs are 12h apart.
    # Foundation PIT uses <= cutoff, so the result must be admitted exactly here.
    source = _match(
        ref=211,
        kickoff=BASE,
        home=1,
        away=2,
        goals=(8, 0),
    )
    target = _match(
        ref=212,
        kickoff=BASE + 12 * 3600,
        home=1,
        away=2,
        goals=(0, 0),
    )
    forecasts = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
        [source, target],
        decision_horizon_seconds=6 * 3600,
        availability_embargo_seconds=6 * 3600,
    )
    assert forecasts[1].lambda_home > GOALS_TARGET.initial_home_rate
    assert forecasts[1].effective_support > 0.0


def test_pit_walk_forward_is_deterministic_for_reordered_input() -> None:
    rows = [
        _match(ref=221, kickoff=BASE, home=1, away=2, goals=(2, 0)),
        _match(ref=222, kickoff=BASE + DAY, home=2, away=3, goals=(1, 1)),
        _match(ref=223, kickoff=BASE + 2 * DAY, home=1, away=3, goals=(3, 1)),
    ]
    a = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(rows)
    b = DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
        list(reversed(rows))
    )
    assert [
        (x.fixture_key, x.lambda_home, x.lambda_away)
        for x in a
    ] == [
        (x.fixture_key, x.lambda_home, x.lambda_away)
        for x in b
    ]


def test_pit_walk_forward_rejects_invalid_horizon_contract() -> None:
    row = _match(ref=231, kickoff=BASE, home=1, away=2)
    with pytest.raises(ValueError, match="decision_horizon_seconds"):
        DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
            [row], decision_horizon_seconds=0
        )
    with pytest.raises(ValueError, match="availability_embargo_seconds"):
        DynamicHierarchicalCountBaseline(GOALS_TARGET).walk_forward(
            [row], availability_embargo_seconds=-1
        )
