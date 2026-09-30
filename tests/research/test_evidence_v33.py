from src.research.evidence_v32.modeling_v33_corners import (
    PRESSURE_KEYS, EXTENDED_KEYS, _venue_side, row_metrics
)
from research.evidence_v32.run_v33_goals_corners import _slice_goal_vector
from src.research.evidence_v32.modeling_v322 import GOALS_DEEP, GOALS_PRIMARY


def _corner_row():
    raw = {}
    paths = {
        "shots":"overview.total_shots",
        "blocked":"shots.blocked_shots",
        "crosses":"passes.accurate_crosses",
        "entries":"passes.final_third_entries",
        "box":"shots.shots_inside_box",
        "touches_box":"attack.touches_in_penalty_area",
        "possession":"overview.ball_possession",
        "clearances":"defending.clearances",
        "shots_off":"shots.shots_off_target",
        "throw_ins":"passes.throw_ins",
        "accurate_long_balls":"passes.accurate_long_balls",
        "offsides":"attack.offsides",
        "goal_kicks":"goalkeeping.goal_kicks",
        "free_kicks":"overview.free_kicks",
    }
    for i, (_, p) in enumerate(paths.items(), 1):
        raw[f"{p}.all.home"] = i
        raw[f"{p}.all.away"] = i + 1
    return {
        "targets": {
            "corners.home": {"value": 7, "period_status": "NO_EXTRA_TIME_RECORDED"},
            "corners.away": {"value": 3, "period_status": "NO_EXTRA_TIME_RECORDED"},
        },
        "raw_stats": raw,
        "period_checks": [],
        "context": {"is_neutral": False},
    }


def test_corner_metrics_use_provider_native_paths():
    m = row_metrics(_corner_row())
    assert m["home"]["corners"] == 7
    assert m["away"]["corners"] == 3
    assert m["home"]["shots"] == 1
    assert m["away"]["free_kicks"] == 15
    assert set(PRESSURE_KEYS).issubset(set(m["home"]))
    assert set(EXTENDED_KEYS).issubset(set(m["home"]))


def test_corner_venue_split_excludes_neutral_unknown():
    assert _venue_side({"context":{"is_neutral":False}}, "home") == "home"
    assert _venue_side({"context":{"is_neutral":False}}, "away") == "away"
    assert _venue_side({"context":{"is_neutral":True}}, "home") == "neutral"
    assert _venue_side({"context":{"is_neutral":None}}, "away") == "unknown"


def test_goal_compact_slice_is_strict_subset_of_deep():
    base_len = 7 + 4 * len(GOALS_DEEP)
    vec = list(range(base_len))
    compact_keys = tuple(GOALS_PRIMARY) + (
        "touches_box", "big_missed", "shots_off", "shots_outside"
    )
    compact = _slice_goal_vector(vec, compact_keys)
    rich = _slice_goal_vector(vec, tuple(GOALS_PRIMARY))
    assert len(rich) == 7 + 4 * len(GOALS_PRIMARY)
    assert len(compact) == 7 + 4 * len(compact_keys)
    assert len(compact) < len(vec)


def test_goal_venue_append_preserved_in_compact_slice():
    base_len = 7 + 4 * len(GOALS_DEEP)
    vec = list(range(base_len + 13))
    compact_keys = tuple(GOALS_PRIMARY) + (
        "touches_box", "big_missed", "shots_off", "shots_outside"
    )
    compact = _slice_goal_vector(vec, compact_keys, keep_venue_append=True)
    assert compact[-13:] == vec[-13:]
