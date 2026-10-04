from math import log

import pytest

from src.research.data_source import ResearchMatch
from src.research.models.dynamic_count_strength import GOALS_TARGET
from src.research.models.hierarchical_state_space import (
    GaussianLogState,
    HierarchicalLogStateSpaceModel,
    HierarchicalStateSpaceConfig,
    StateDynamics,
)


def _config() -> HierarchicalStateSpaceConfig:
    return HierarchicalStateSpaceConfig(
        global_state=StateDynamics(365.0, 0.12),
        competition_state=StateDynamics(180.0, 0.20),
        team_global_state=StateDynamics(120.0, 0.28),
        team_comp_state=StateDynamics(60.0, 0.20),
        team_influence=1.0,
        min_effective_team_support=2.0,
    )


def _match(
    match_id: int,
    kickoff: int,
    *,
    comp: str = "comp_a",
    home: str = "team_h",
    away: str = "team_a",
    hg: int = 1,
    ag: int = 1,
) -> ResearchMatch:
    return ResearchMatch(
        match_id=match_id,
        date_unix=kickoff,
        league_id=1,
        season="2025",
        home_team=home,
        away_team=away,
        source_provider="test",
        source_match_ref=f"m{match_id}",
        competition_ref=comp,
        season_ref="season_1",
        home_team_ref=home,
        away_team_ref=away,
        home_goals=hg,
        away_goals=ag,
        total_goals=hg + ag,
    )


def test_gaussian_log_state_batch_update_is_order_invariant():
    dynamics = StateDynamics(120.0, 0.4)
    obs = [(2, log(1.2)), (0, log(1.1)), (3, log(1.5))]
    a = GaussianLogState()
    b = GaussianLogState()
    a.update_batch(obs, timestamp=1000, dynamics=dynamics, center=0.0)
    b.update_batch(list(reversed(obs)), timestamp=1000, dynamics=dynamics, center=0.0)
    assert a.mean == pytest.approx(b.mean, abs=1e-12)
    assert a.variance == pytest.approx(b.variance, abs=1e-12)
    assert a.effective_observations == b.effective_observations == 3.0


def test_environment_relative_update_does_not_treat_absolute_count_as_strength():
    dynamics = StateDynamics(180.0, 0.5)
    low_env = GaussianLogState()
    high_env = GaussianLogState()
    # Both observations are 2x their environment rate. The higher-count case
    # contains more information, but both should estimate a positive residual
    # on the same log-relative scale rather than treating 4 as twice as strong.
    low_env.update_batch([(2, log(1.0))], timestamp=1000, dynamics=dynamics, center=0.0)
    high_env.update_batch([(4, log(2.0))], timestamp=1000, dynamics=dynamics, center=0.0)
    assert low_env.mean > 0
    assert high_env.mean > 0
    assert abs(low_env.mean - high_env.mean) < 0.20
    assert high_env.variance < low_env.variance


def test_same_kickoff_batch_is_order_invariant_for_future_state():
    m1 = _match(1, 1000, home="a", away="b", hg=2, ag=0)
    m2 = _match(2, 1000, home="c", away="d", hg=1, ag=3)

    left = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    right = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    left_forecasts = left.process_batch([m1, m2])
    right_forecasts = right.process_batch([m2, m1])

    lf = {f.fixture_key: f for f in left_forecasts}
    rf = {f.fixture_key: f for f in right_forecasts}
    assert lf.keys() == rf.keys()
    for key in lf:
        assert lf[key].lambda_home == pytest.approx(rf[key].lambda_home, abs=1e-12)
        assert lf[key].lambda_away == pytest.approx(rf[key].lambda_away, abs=1e-12)

    future = _match(3, 2000, home="a", away="d", hg=0, ag=0)
    f_left = left.forecast(future)
    f_right = right.forecast(future)
    assert f_left.lambda_home == pytest.approx(f_right.lambda_home, abs=1e-12)
    assert f_left.lambda_away == pytest.approx(f_right.lambda_away, abs=1e-12)
    assert f_left.latent_log_sd_home == pytest.approx(
        f_right.latent_log_sd_home, abs=1e-12
    )


def test_uncertainty_shrinks_with_repeated_team_evidence():
    fresh = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    fresh_forecast = fresh.forecast(_match(100, 1000, home="a", away="b"))

    trained = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    for i in range(10):
        trained.process_batch(
            [
                _match(
                    i + 1,
                    1000 + i * 86400,
                    home="a",
                    away="b",
                    hg=2 if i % 2 == 0 else 1,
                    ag=1,
                )
            ]
        )
    later = trained.forecast(_match(200, 1000 + 11 * 86400, home="a", away="b"))
    assert later.latent_log_sd_home < fresh_forecast.latent_log_sd_home
    assert later.latent_log_sd_away < fresh_forecast.latent_log_sd_away
    assert later.effective_support > 2.0
    assert later.supported is True


def test_forecast_exposes_positive_latent_rate_intervals_and_coherent_total():
    model = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    f = model.forecast(_match(1, 1000))
    assert f.lambda_home > 0
    assert f.lambda_away > 0
    assert f.lambda_total == pytest.approx(f.lambda_home + f.lambda_away)
    hlo, hhi = f.home_expected_rate_interval_90
    alo, ahi = f.away_expected_rate_interval_90
    assert 0 < hlo < hhi
    assert 0 < alo < ahi
    assert f.latent_log_sd_home > 0
    assert f.latent_log_sd_away > 0
    assert 0.0 <= f.probability_over(2.5) <= 1.0


def test_same_match_outcome_cannot_enter_its_own_forecast():
    model_a = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    model_b = HierarchicalLogStateSpaceModel(GOALS_TARGET, _config())
    a = _match(1, 1000, hg=0, ag=0)
    b = _match(1, 1000, hg=7, ag=6)
    fa = model_a.process_batch([a])[0]
    fb = model_b.process_batch([b])[0]
    assert fa.lambda_home == pytest.approx(fb.lambda_home, abs=1e-12)
    assert fa.lambda_away == pytest.approx(fb.lambda_away, abs=1e-12)
