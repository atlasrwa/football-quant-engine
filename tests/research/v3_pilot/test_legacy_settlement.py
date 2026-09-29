from src.research.v3_pilot import legacy_settlement as ls

def test_team_corner_settlement_uses_named_team_side():
    decl = {
        "market": "Faroe_Islands_team_corners",
        "side": "UNDER",
        "line": 4.5,
    }
    fx = {"home_name": "Moldova", "away_name": "Faroe Islands"}
    stats = {
        "data": {
            "overview": {
                "corner_kicks": {"all": {"home": 7, "away": 3}}
            }
        }
    }
    value, unit = ls._corner_value(decl, fx, stats)
    assert value == 3.0
    assert unit == "Faroe Islands_team_corners"
    assert ls._settled_result(value, 4.5, "UNDER") == "WIN"

def test_fixture_resolution_requires_name_and_kickoff():
    decl = {
        "fixture": "Finland vs Belarus",
        "kickoff_utc": "2026-09-29T16:00:00Z",
    }
    state = {
        "fixtures": {
            "x": {
                "match_id": "mt_x",
                "home_name": "Finland",
                "away_name": "Belarus",
                "ts": 1790697600.0,
            }
        }
    }
    expected = ls._kickoff_ts(decl["kickoff_utc"])
    state["fixtures"]["x"]["ts"] = expected
    assert ls._resolve_fixture(decl, state)["match_id"] == "mt_x"

def test_bookings_are_not_inferred_from_corner_helper():
    decl = {"market": "Rushbet_total_cards_points"}
    fx = {"home_name": "A", "away_name": "B"}
    stats = {"data": {"overview": {"corner_kicks": {"all": {"home": 1, "away": 2}}}}}
    assert ls._corner_value(decl, fx, stats) is None
