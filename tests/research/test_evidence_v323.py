import math

from src.research.evidence_v32.modeling_v323 import (
    MIN_VENUE_HISTORY, VENUE_RATE_KEYS, _venue_features, _venue_profile,
    _venue_side, _venue_supported, row_metrics_with_events,
)


def _row(home_goals=2, away_goals=0):
    return {
        "targets": {
            "goals.home": {"value": home_goals},
            "goals.away": {"value": away_goals},
            "bookings.home": {"value": 1},
            "bookings.away": {"value": 2},
            "corners.home": {"period_status": "NO_EXTRA_TIME_RECORDED"},
            "corners.away": {"period_status": "NO_EXTRA_TIME_RECORDED"},
        },
        "raw_stats": {},
        "period_checks": [],
    }


def test_clean_sheet_failed_to_score_and_btts_are_side_correct():
    metrics = row_metrics_with_events(_row(2, 0))
    assert metrics["home"]["clean_sheet"] == 1.0
    assert metrics["home"]["failed_to_score"] == 0.0
    assert metrics["away"]["clean_sheet"] == 0.0
    assert metrics["away"]["failed_to_score"] == 1.0
    assert metrics["home"]["btts"] == metrics["away"]["btts"] == 0.0
def test_venue_side_excludes_neutral_and_unknown_from_home_away_splits():
    assert _venue_side({"context": {"is_neutral": False}}, "home") == "home"
    assert _venue_side({"context": {"is_neutral": False}}, "away") == "away"
    assert _venue_side({"context": {"is_neutral": True}}, "home") == "neutral"
    assert _venue_side({"context": {"is_neutral": None}}, "away") == "unknown"


def test_venue_profile_shrinks_to_same_team_overall_profile():
    overall = {
        "own_goals": 1.5,
        "opp_goals": 1.0,
        "own_clean_sheet": 0.30,
        "opp_clean_sheet": 0.20,
    }
    entries = [
        {"ts": 100.0, "own": {"goals": 3.0, "clean_sheet": 1.0},
         "opp": {"goals": 0.0, "clean_sheet": 0.0}},
        {"ts": 200.0, "own": {"goals": 1.0, "clean_sheet": 0.0},
         "opp": {"goals": 2.0, "clean_sheet": 0.0}},
    ]
    profile = _venue_profile(entries, overall, 300.0, ("goals", "clean_sheet"))
    assert profile["own_goals_n"] == 2
    assert profile["opp_goals_n"] == 2
    assert 1.5 < profile["own_goals"] < 2.0
    assert 0.30 < profile["own_clean_sheet"] < 0.5
def test_venue_support_requires_three_prior_matches_and_xg_separately():
    profile = {}
    for key in ("goals", "shots", "sot", "box", "big"):
        for kind in ("own", "opp"):
            profile[f"{kind}_{key}_n"] = MIN_VENUE_HISTORY
            profile[f"{kind}_{key}"] = 1.0
    for key in VENUE_RATE_KEYS:
        profile[f"own_{key}_n"] = MIN_VENUE_HISTORY
        profile[f"own_{key}"] = 0.5
    assert _venue_supported(profile)
    assert not _venue_supported(profile, include_xg=True)
    profile.update({
        "own_xg_n": MIN_VENUE_HISTORY,
        "opp_xg_n": MIN_VENUE_HISTORY,
        "own_xg": 1.2,
        "opp_xg": 1.1,
    })
    assert _venue_supported(profile, include_xg=True)


def test_venue_feature_vector_contains_for_and_against_plus_rates():
    profile = {}
    for key in ("goals", "shots", "sot", "box", "big"):
        profile[f"own_{key}"] = 2.0
        profile[f"opp_{key}"] = 1.0
    for key in VENUE_RATE_KEYS:
        profile[f"own_{key}"] = 0.25
    values = _venue_features(profile)
    assert len(values) == 13
    assert values[:2] == [2.0, 1.0]
    assert values[-3:] == [0.25, 0.25, 0.25]
