"""Structural anti-leakage tests for the leak-free feature builder.

This bug class (same-match feature leakage) has appeared twice in the project. The
guard must (a) PASS on the prior-only builder and (b) FAIL loudly when a same-match
feature is injected — proving it is a structural check, not a convention.
"""
import numpy as np
import pytest

from src.research.models.prior_only_features import (
    build_prior_only_features,
    assert_no_same_match_leakage,
    CORNERS_FEATURES,
    CARDS_FEATURES,
    _RAW_KEYS,
)


def _synth_matches(n=120, seed=7):
    """Synthetic corpus matches with team ids, dates, and per-team stats."""
    rng = np.random.default_rng(seed)
    teams = list(range(10))
    ms = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        ms.append({
            "id": 1000 + i, "date_unix": 1_600_000_000 + i * 86400,
            "homeID": int(h), "awayID": int(a),
            "team_a_shots": int(rng.integers(5, 20)), "team_b_shots": int(rng.integers(5, 20)),
            "team_a_dangerous_attacks": int(rng.integers(20, 60)),
            "team_b_dangerous_attacks": int(rng.integers(20, 60)),
            "team_a_attacks": int(rng.integers(60, 140)), "team_b_attacks": int(rng.integers(60, 140)),
            "team_a_possession": int(rng.integers(35, 65)), "team_b_possession": int(rng.integers(35, 65)),
            "team_a_fouls": int(rng.integers(6, 18)), "team_b_fouls": int(rng.integers(6, 18)),
            "totalCornerCount": int(rng.integers(4, 15)),
            "team_a_yellow_cards": int(rng.integers(0, 4)), "team_b_yellow_cards": int(rng.integers(0, 4)),
            "team_a_red_cards": 0, "team_b_red_cards": 0,
        })
    return ms


def test_prior_only_builder_passes_guard_corners():
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_corners")
    # Must not raise.
    assert_no_same_match_leakage(ms, feats)


def test_prior_only_builder_passes_guard_cards():
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_cards")
    assert_no_same_match_leakage(ms, feats)


def test_feature_dict_has_no_raw_same_match_keys():
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_corners")
    raw_keys = {k for pair in _RAW_KEYS.values() for k in pair}
    for f in feats:
        assert raw_keys.isdisjoint(f.keys())


def test_guard_CATCHES_injected_same_match_leakage():
    """The decisive test: inject the fixture's own realized shots as the feature and
    confirm the guard RAISES. If this does not raise, the guard is useless."""
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_corners")
    # Inject leakage: overwrite shots_home with THIS match's own realized home shots.
    leaked = [dict(f) for f in feats]
    ms_sorted = sorted(ms, key=lambda m: m["date_unix"])
    for i, m in enumerate(ms_sorted):
        leaked[i]["shots_home"] = float(m["team_a_shots"])  # same-match value
    with pytest.raises(AssertionError, match="SAME-MATCH LEAKAGE"):
        assert_no_same_match_leakage(ms_sorted, leaked)


def test_guard_catches_raw_key_injection():
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_corners")
    bad = [dict(f) for f in feats]
    for f in bad:
        f["team_a_shots"] = 12.0  # a raw same-match stat key must never be a feature
    with pytest.raises(AssertionError, match="raw same-match stat keys"):
        assert_no_same_match_leakage(sorted(ms, key=lambda m: m["date_unix"]), bad)


def test_features_are_strictly_prior_first_rows_use_neutral_prior():
    """The very first match has no prior history, so features fall back to the
    running global mean (0.0 at t=0), never the fixture's own values."""
    ms = _synth_matches()
    feats = build_prior_only_features(ms, target_field="total_corners")
    ms_sorted = sorted(ms, key=lambda m: m["date_unix"])
    first = feats[0]
    # first match: no prior data -> neutral prior 0.0, and definitely not its own shots
    assert first["shots_home"] == 0.0
    assert first["shots_home"] != float(ms_sorted[0]["team_a_shots"]) or ms_sorted[0]["team_a_shots"] == 0
