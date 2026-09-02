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



# ── RICH-corpus builder + guard ───────────────────────────────────────────────

from src.research.models.prior_only_features import (
    build_rich_prior_only_features,
    assert_no_same_match_leakage_rich,
    _RICH_TUPLE_FIELDS,
    _RICH_BASELINE_FLAT,
)


def _synth_rich_matches(n=120, seed=11):
    """Synthetic TheStatsAPI-rich-corpus matches: home_id/away_id (str) + _rich tuples."""
    rng = np.random.default_rng(seed)
    teams = [f"tm_{i:04d}" for i in range(10)]
    ms = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        def pair(lo, hi):
            return (int(rng.integers(lo, hi)), int(rng.integers(lo, hi)))
        rich = {f: pair(0, 20) for f in _RICH_TUPLE_FIELDS}
        # give corner_kicks / shots_on_target realistic ranges for the target
        rich["corner_kicks"] = (int(rng.integers(2, 9)), int(rng.integers(2, 9)))
        rich["shots_on_target"] = (int(rng.integers(1, 8)), int(rng.integers(1, 8)))
        ms.append({
            "match_id": f"mt_{i}", "date_unix": 1_600_000_000 + i * 86400,
            "home_id": str(h), "away_id": str(a),
            "team_a_fouls": int(rng.integers(6, 18)), "team_b_fouls": int(rng.integers(6, 18)),
            "team_a_shotsOnTarget": rich["shots_on_target"][0], "team_b_shotsOnTarget": rich["shots_on_target"][1],
            "team_a_xg": round(float(rng.uniform(0.3, 2.5)), 2), "team_b_xg": round(float(rng.uniform(0.3, 2.5)), 2),
            "team_a_yellow_cards": int(rng.integers(0, 4)), "team_b_yellow_cards": int(rng.integers(0, 4)),
            "team_a_red_cards": 0, "team_b_red_cards": 0,
            "_rich": rich,
        })
    return ms


RICH_TEST_FIELDS = ["corner_kicks", "tackles", "interceptions", "fouls", "shotsOnTarget"]


def test_rich_builder_passes_guard_corners():
    ms = _synth_rich_matches()
    feats = build_rich_prior_only_features(ms, target_field="total_corners", fields=RICH_TEST_FIELDS)
    assert_no_same_match_leakage_rich(ms, feats, fields=RICH_TEST_FIELDS)  # must not raise


def test_rich_builder_passes_guard_cards_and_sot():
    ms = _synth_rich_matches()
    for tgt in ("total_cards", "total_sot"):
        feats = build_rich_prior_only_features(ms, target_field=tgt, fields=RICH_TEST_FIELDS)
        assert_no_same_match_leakage_rich(ms, feats, fields=RICH_TEST_FIELDS)


def test_rich_feature_dict_has_no_raw_keys():
    ms = _synth_rich_matches()
    feats = build_rich_prior_only_features(ms, target_field="total_corners", fields=RICH_TEST_FIELDS)
    raw = {k for pair in _RICH_BASELINE_FLAT.values() for k in pair} | set(_RICH_TUPLE_FIELDS)
    for f in feats:
        assert raw.isdisjoint(f.keys())


def test_rich_guard_CATCHES_injected_same_match_leakage():
    """Decisive: inject the fixture's OWN realized tackles as the feature -> guard MUST raise."""
    ms = _synth_rich_matches()
    ms_sorted = sorted(ms, key=lambda m: m["date_unix"])
    feats = build_rich_prior_only_features(ms_sorted, target_field="total_corners", fields=RICH_TEST_FIELDS)
    leaked = [dict(f) for f in feats]
    for i, m in enumerate(ms_sorted):
        leaked[i]["tackles_home"] = float(m["_rich"]["tackles"][0])  # same-match value
    with pytest.raises(AssertionError, match="SAME-MATCH LEAKAGE"):
        assert_no_same_match_leakage_rich(ms_sorted, leaked, fields=RICH_TEST_FIELDS)


def test_rich_guard_catches_raw_bare_field_key():
    ms = _synth_rich_matches()
    feats = build_rich_prior_only_features(ms, target_field="total_corners", fields=RICH_TEST_FIELDS)
    bad = [dict(f) for f in feats]
    for f in bad:
        f["tackles"] = 10.0  # a bare rich field name = same-match value, forbidden as a feature
    with pytest.raises(AssertionError, match="raw same-match keys"):
        assert_no_same_match_leakage_rich(sorted(ms, key=lambda m: m["date_unix"]), bad, fields=RICH_TEST_FIELDS)
