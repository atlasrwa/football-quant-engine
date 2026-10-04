from src.research.data_source import ResearchMatch
from src.research.models.competition_local_count_strength import (
    COMPETITION_LOCAL_MODEL_VERSION,
    CompetitionLocalDynamicCountBaseline,
)
from src.research.models.dynamic_count_strength import (
    GOALS_TARGET,
    DynamicCountConfig,
)


def _config() -> DynamicCountConfig:
    return DynamicCountConfig(
        half_life_days=360.0,
        global_prior_weight=20.0,
        competition_prior_weight=40.0,
        team_global_prior_weight=16.0,
        team_comp_prior_weight=4.0,
        team_influence=1.0,
        transfer_factor_floor=0.60,
        transfer_factor_ceiling=1.67,
        min_effective_team_support=3.0,
    )


def _match(
    match_id: int,
    kickoff: int,
    *,
    competition: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
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
        competition_ref=competition,
        season_ref=f"{competition}-season",
        home_team_ref=home,
        away_team_ref=away,
        home_goals=home_goals,
        away_goals=away_goals,
        total_goals=home_goals + away_goals,
    )


def test_competition_local_model_never_creates_team_global_state():
    model = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    model.process_batch(
        [
            _match(
                1, 1000,
                competition="comp_a",
                home="team_x",
                away="team_y",
                home_goals=3,
                away_goals=1,
            )
        ]
    )
    assert model._team_global == {}
    assert model.model_version.startswith(COMPETITION_LOCAL_MODEL_VERSION)


def test_team_transition_to_new_competition_has_zero_local_support():
    model = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    model.process_batch(
        [
            _match(
                1, 1000,
                competition="comp_a",
                home="team_x",
                away="team_y",
                home_goals=4,
                away_goals=0,
            )
        ]
    )
    forecast = model.forecast(
        _match(
            2, 2000,
            competition="comp_b",
            home="team_x",
            away="team_z",
            home_goals=0,
            away_goals=0,
        )
    )
    assert forecast.trace.home_attack_support == 0.0
    assert forecast.trace.home_attack_rate == forecast.trace.competition_home_rate
    assert forecast.supported is False
    assert model._team_global == {}


def test_same_match_outcome_does_not_change_its_own_forecast():
    low = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    high = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    match_low = _match(
        1, 1000,
        competition="comp_a",
        home="a",
        away="b",
        home_goals=0,
        away_goals=0,
    )
    match_high = _match(
        1, 1000,
        competition="comp_a",
        home="a",
        away="b",
        home_goals=8,
        away_goals=7,
    )
    f_low = low.process_batch([match_low])[0]
    f_high = high.process_batch([match_high])[0]
    assert f_low.lambda_home == f_high.lambda_home
    assert f_low.lambda_away == f_high.lambda_away


def test_same_kickoff_order_is_invariant():
    a = _match(
        1, 1000,
        competition="comp_a",
        home="a",
        away="b",
        home_goals=2,
        away_goals=0,
    )
    b = _match(
        2, 1000,
        competition="comp_a",
        home="c",
        away="d",
        home_goals=1,
        away_goals=3,
    )
    left = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    right = CompetitionLocalDynamicCountBaseline(GOALS_TARGET, _config())
    lf = {x.fixture_key: x for x in left.process_batch([a, b])}
    rf = {x.fixture_key: x for x in right.process_batch([b, a])}
    assert lf.keys() == rf.keys()
    for key in lf:
        assert lf[key].lambda_home == rf[key].lambda_home
        assert lf[key].lambda_away == rf[key].lambda_away

    future = _match(
        3, 2000,
        competition="comp_a",
        home="a",
        away="d",
        home_goals=0,
        away_goals=0,
    )
    future_left = left.forecast(future)
    future_right = right.forecast(future)
    assert future_left.lambda_home == future_right.lambda_home
    assert future_left.lambda_away == future_right.lambda_away
