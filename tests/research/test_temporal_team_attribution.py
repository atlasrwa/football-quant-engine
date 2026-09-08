from src.research.data_source import ResearchMatch
from src.research.forward.temporal_features import TemporalFeatureEngine


def _match(
    match_id: int,
    date_unix: int,
    home_team: str,
    away_team: str,
    *,
    home_goals: int,
    away_goals: int,
    corners_home: int,
    corners_away: int,
    yellow_cards_home: int,
    yellow_cards_away: int,
    red_cards_home: int = 0,
    red_cards_away: int = 0,
    shots_home: int,
    shots_away: int,
    dangerous_attacks_home: int,
    dangerous_attacks_away: int,
) -> ResearchMatch:
    return ResearchMatch(
        match_id=match_id,
        date_unix=date_unix,
        league_id=1,
        season="2026",
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        total_goals=home_goals + away_goals,
        corners_home=corners_home,
        corners_away=corners_away,
        total_corners=corners_home + corners_away,
        yellow_cards_home=yellow_cards_home,
        yellow_cards_away=yellow_cards_away,
        red_cards_home=red_cards_home,
        red_cards_away=red_cards_away,
        total_cards=(
            yellow_cards_home
            + yellow_cards_away
            + red_cards_home
            + red_cards_away
        ),
        shots_home=shots_home,
        shots_away=shots_away,
        dangerous_attacks_home=dangerous_attacks_home,
        dangerous_attacks_away=dangerous_attacks_away,
    )


def test_team_history_uses_actual_historical_side_not_target_side_label():
    matches = [
        _match(
            1,
            100,
            "10",
            "99",
            home_goals=2,
            away_goals=0,
            corners_home=8,
            corners_away=1,
            yellow_cards_home=1,
            yellow_cards_away=4,
            shots_home=15,
            shots_away=4,
            dangerous_attacks_home=70,
            dangerous_attacks_away=20,
        ),
        _match(
            2,
            200,
            "98",
            "10",
            home_goals=1,
            away_goals=3,
            corners_home=2,
            corners_away=6,
            yellow_cards_home=3,
            yellow_cards_away=2,
            shots_home=6,
            shots_away=12,
            dangerous_attacks_home=30,
            dangerous_attacks_away=60,
        ),
    ]

    snapshot = TemporalFeatureEngine(matches).build_snapshot(
        fixture_id="future",
        home_team_id=10,
        away_team_id=20,
        prediction_timestamp=300,
        kickoff_timestamp=400,
    )

    assert snapshot.features["avg_goals_home"] == 2.5
    assert snapshot.features["avg_corners_home"] == 7.0
    assert snapshot.features["avg_cards_home"] == 1.5
    assert snapshot.features["avg_shots_home"] == 13.5
    assert snapshot.features["avg_dangerous_attacks_home"] == 65.0
    assert snapshot.features["form_points_home"] == 3.0
    assert snapshot.features["matches_played_home"] == 2.0


def test_swapping_target_home_away_only_swaps_feature_suffixes():
    matches = [
        _match(
            1,
            100,
            "10",
            "20",
            home_goals=1,
            away_goals=2,
            corners_home=3,
            corners_away=7,
            yellow_cards_home=2,
            yellow_cards_away=1,
            shots_home=8,
            shots_away=14,
            dangerous_attacks_home=40,
            dangerous_attacks_away=75,
        ),
        _match(
            2,
            200,
            "20",
            "10",
            home_goals=0,
            away_goals=4,
            corners_home=5,
            corners_away=9,
            yellow_cards_home=4,
            yellow_cards_away=3,
            shots_home=7,
            shots_away=16,
            dangerous_attacks_home=35,
            dangerous_attacks_away=80,
        ),
    ]
    engine = TemporalFeatureEngine(matches)

    a = engine.build_snapshot(
        fixture_id="a",
        home_team_id=10,
        away_team_id=20,
        prediction_timestamp=300,
        kickoff_timestamp=400,
    )
    b = engine.build_snapshot(
        fixture_id="b",
        home_team_id=20,
        away_team_id=10,
        prediction_timestamp=300,
        kickoff_timestamp=400,
    )

    for stem in (
        "avg_goals",
        "avg_corners",
        "avg_cards",
        "avg_shots",
        "avg_dangerous_attacks",
        "form_points",
        "matches_played",
    ):
        assert a.features[f"{stem}_home"] == b.features[f"{stem}_away"]
        assert a.features[f"{stem}_away"] == b.features[f"{stem}_home"]


def test_same_timestamp_fixture_is_excluded_from_history():
    matches = [
        _match(
            1,
            100,
            "10",
            "99",
            home_goals=1,
            away_goals=0,
            corners_home=4,
            corners_away=2,
            yellow_cards_home=1,
            yellow_cards_away=1,
            shots_home=10,
            shots_away=5,
            dangerous_attacks_home=50,
            dangerous_attacks_away=25,
        ),
        _match(
            2,
            200,
            "10",
            "98",
            home_goals=9,
            away_goals=0,
            corners_home=15,
            corners_away=0,
            yellow_cards_home=5,
            yellow_cards_away=0,
            shots_home=30,
            shots_away=1,
            dangerous_attacks_home=120,
            dangerous_attacks_away=5,
        ),
    ]

    snapshot = TemporalFeatureEngine(matches, strict_mode=True).build_snapshot(
        fixture_id="future",
        home_team_id=10,
        away_team_id=20,
        prediction_timestamp=200,
        kickoff_timestamp=300,
    )

    assert snapshot.features["matches_played_home"] == 1.0
    assert snapshot.features["avg_goals_home"] == 1.0
    assert snapshot.features["avg_corners_home"] == 4.0
