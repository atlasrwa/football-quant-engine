"""Focused tests for prior-season spatial profiles and modeling overlays."""
import sys
import types

import pytest

from scripts import heatmap_positional_experiment as exp


def test_positional_profile_is_touch_weighted_and_reports_structural_features():
    response = {"data": {"points": [
        {"x": 0, "y": 0, "count": 1},
        {"x": 100, "y": 100, "count": 3},
    ]}}
    profile = exp.positional_profile([response])
    assert profile["heatmap_mean_x"] == pytest.approx(75.0)
    assert profile["heatmap_mean_y"] == pytest.approx(75.0)
    assert profile["heatmap_width_sd_x"] == pytest.approx(43.30127019)
    assert profile["heatmap_depth_sd_y"] == pytest.approx(43.30127019)
    assert profile["heatmap_width_index"] == pytest.approx(1.0)
    assert profile["heatmap_pitch_height"] == pytest.approx(75.0)
    assert profile["heatmap_vertical_compactness"] == pytest.approx(0.0)
    assert profile["heatmap_final_third_share"] == pytest.approx(0.75)
    assert profile["heatmap_lr_asymmetry"] == pytest.approx(0.5)
    assert profile["heatmap_touch_count"] == pytest.approx(4.0)


def test_weighted_quantile_and_invalid_points_are_not_zero_filled():
    assert exp.weighted_quantile([0, 50, 100], [1, 2, 1], 0.5) == 50
    with pytest.raises(ValueError):
        exp.weighted_quantile([], [], 0.5)
    response = {"data": {"points": [
        {"x": None, "y": 20, "count": 3},
        {"x": 30, "y": 40, "count": 0},
        {"x": 101, "y": 40, "count": 1},
        {"x": 30, "y": 40, "count": -1},
    ]}}
    assert exp.valid_points(response) == []
    assert exp.positional_profile([response]) is None


def _profile(value):
    profile = {field: float(value) for field in exp.POSITIONAL_FIELDS}
    profile.update({"heatmap_player_coverage": 12.0, "heatmap_touch_count": 1000.0})
    return profile


def test_attach_prior_profiles_requires_strict_cutoff_and_drops_missing_profiles():
    profiles = {"h": _profile(10), "a": _profile(20)}
    rows = [
        {"date_unix": 101, "home_team_id": "h", "away_team_id": "a"},
        {"date_unix": 102, "home_team_id": "h", "away_team_id": "missing"},
    ]
    joined = exp.attach_prior_profiles(rows, profiles, profile_season_end_unix=100)
    assert len(joined) == 1
    assert joined[0]["heatmap_pitch_height_home"] == 10.0
    assert joined[0]["heatmap_pitch_height_away"] == 20.0
    assert joined[0]["heatmap_player_coverage_home"] == 12.0
    assert "heatmap_pitch_height_home" not in rows[1]
    with pytest.raises(AssertionError, match="strictly before"):
        exp.attach_prior_profiles(rows[:1], profiles, profile_season_end_unix=101)


def test_build_team_profiles_excludes_insufficient_coverage(monkeypatch):
    response = {"data": {"points": [{"x": 20, "y": 70, "count": 10}]}}
    monkeypatch.setattr(exp, "load_cached_response", lambda _player: response)
    profiles = exp.build_team_profiles(
        {"covered": ["p1", "p2"], "thin": ["p3"]},
        min_valid_players=2,
        min_total_touches=1,
    )
    assert set(profiles) == {"covered"}
    assert profiles["covered"]["heatmap_player_coverage"] == 2.0


def test_matchup_interactions_are_invariant_to_home_away_swap():
    row = {
        "heatmap_width_index_home": 0.2,
        "heatmap_width_index_away": 0.6,
        "heatmap_pitch_height_home": 60.0,
        "heatmap_pitch_height_away": 40.0,
        "heatmap_vertical_compactness_home": 0.7,
        "heatmap_vertical_compactness_away": 0.5,
        "heatmap_final_third_share_home": 0.3,
        "heatmap_final_third_share_away": 0.1,
        "heatmap_lr_asymmetry_home": -0.2,
        "heatmap_lr_asymmetry_away": 0.4,
    }
    swapped = {}
    for key, value in row.items():
        swapped[key.replace("_home", "_tmp").replace("_away", "_home").replace("_tmp", "_away")] = value
    first = exp.add_matchup_interactions([row])[0]
    second = exp.add_matchup_interactions([swapped])[0]
    for field in exp.MATCHUP_FIELDS:
        assert first[field] == pytest.approx(second[field])


def test_hierarchical_probability_shrinks_more_with_thin_team_history():
    thin = exp.new_hierarchy_state()
    thin["global"][:] = [60.0, 100]
    thin["leagues"]["league"][:] = [6.0, 10]
    thin["teams"][("league", "home")][:] = [1.0, 2]
    thin["teams"][("league", "away")][:] = [1.0, 2]
    thin_result = exp.hierarchical_probability(
        0.95, thin, league_id="league", home_team_id="home", away_team_id="away"
    )

    supported = exp.new_hierarchy_state()
    supported["global"][:] = [60.0, 100]
    supported["leagues"]["league"][:] = [60.0, 100]
    supported["teams"][("league", "home")][:] = [60.0, 100]
    supported["teams"][("league", "away")][:] = [60.0, 100]
    supported_result = exp.hierarchical_probability(
        0.95, supported, league_id="league", home_team_id="home", away_team_id="away"
    )
    assert thin_result["model_weight"] < supported_result["model_weight"]
    assert abs(thin_result["probability"] - 0.95) > abs(supported_result["probability"] - 0.95)


def test_beta_uncertainty_narrows_and_abstention_targets_unsupported_confidence():
    empty = exp.bayesian_bin_posterior(0, 0)
    supported = exp.bayesian_bin_posterior(24, 30)
    assert supported["width"] < empty["width"]
    abstain, reasons = exp.abstention_decision(
        0.9, min_team_n=2, calibration_bin_n=0, interval_width=0.8
    )
    assert abstain
    assert set(reasons) == {"thin_team_history", "thin_calibration_bin", "wide_beta_interval"}
    assert exp.abstention_decision(
        0.55, min_team_n=0, calibration_bin_n=0, interval_width=0.8
    ) == (False, [])
    assert exp.abstention_decision(
        0.9, min_team_n=20, calibration_bin_n=30, interval_width=0.2
    ) == (False, [])


def test_fetch_uses_cache_contract_without_live_request(monkeypatch, tmp_path):
    fake = types.SimpleNamespace()
    monkeypatch.setattr(exp, "require_orientation_certificate", lambda: {"status": "CERTIFIED"})
    fake.live_requests_made = lambda: 0
    calls = []

    def get_json(_path, *, cache_key, allow_status):
        calls.append((cache_key, allow_status))
        return {"data": {"points": [{"x": 50, "y": 50, "count": 1}]}}, {
            "http_status": 200,
            "from_cache": True,
        }

    fake.get_json = get_json
    monkeypatch.setitem(sys.modules, "thestatsapi_client", fake)
    monkeypatch.setattr(exp, "HEATMAP_CACHE", tmp_path)
    monkeypatch.setattr(exp, "selected_team_players", lambda _max: {"team": ["pl_cached"]})
    manifest = exp.fetch_selected_heatmaps(max_players=1)
    assert manifest["live_requests_this_run"] == 0
    assert calls == [
        (f"player_pl_cached_{exp.COMPETITION_ID}_{exp.PROFILE_SEASON_ID}", (200, 404))
    ]
    calls.clear()
    exp.fetch_selected_heatmaps(max_players=1)
    assert calls == []


def test_paired_difference_keeps_simultaneous_fixtures_distinct():
    base = {
        "match_ids": [f"mt_{index}" for index in range(30)],
        "preds": exp.np.tile(exp.np.asarray([0.1, 0.9]), 15),
        "actuals": exp.np.tile(exp.np.asarray([0.0, 1.0]), 15),
    }
    augmented = {
        "match_ids": list(base["match_ids"]),
        "preds": exp.np.tile(exp.np.asarray([0.2, 0.8]), 15),
        "actuals": exp.np.tile(exp.np.asarray([0.0, 1.0]), 15),
    }
    result = exp.paired_bss_difference(base, augmented, n_boot=100)
    assert result["n_common"] == 30



def test_orientation_certificate_fails_closed_when_missing(tmp_path):
    with pytest.raises(RuntimeError, match="BLOCKED_UNVERIFIED_ORIENTATION"):
        exp.require_orientation_certificate(tmp_path / "missing.json")


def test_orientation_certificate_requires_exact_certified_scope(tmp_path):
    certificate = tmp_path / "certificate.json"
    certificate.write_text(
        '{"certifications":[{"league_key":"spain_segunda_division",'
        '"competition_id":"comp_0976","profile_season_id":"sn_8425423",'
        '"status":"CERTIFIED","evidence_reference":"audit-123",'
        '"certified_at":"2026-09-04T00:00:00Z"}]}'
    )
    assert exp.require_orientation_certificate(certificate)["status"] == "CERTIFIED"
