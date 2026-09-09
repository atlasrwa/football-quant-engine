"""Tests for the leakage-safe prospective research plane.

Grouped by the mission's Part 11 categories: point-in-time, odds, market prior,
lineups, player state, residual model, and evaluation.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from src.research.observation.model import MISSING
from src.research.prospective.api_contract import (
    KNOWN_DISCREPANCIES,
    LIVE_BASE_URL,
    Endpoint,
    ProspectiveClientConfig,
    endpoint_path,
)
from src.research.prospective.capture import (
    CaptureRecord,
    ProspectiveApiClient,
    ProspectiveConfigError,
)
from src.research.prospective.clv_eval import CLVRow, evaluate_clv
from src.research.prospective.decomposition import (
    common_support,
    compute_resolution,
    run_decomposition,
)
from src.research.prospective.disagreement import DisagreementRow, bucket_diagnostics, bucket_for
from src.research.prospective.fundamental import FundamentalForecast, compute_disagreement
from src.research.prospective.lineup_state import (
    AvailabilityReason,
    ExpectedXIState,
    LineupError,
    TeamLineup,
    compute_lineup_delta,
    normalize_lineup,
)
from src.research.prospective.market_prior import MarketAvailability, build_market_prior
from src.research.prospective.movement import compute_movement
from src.research.prospective.odds_capture import (
    CapturedPrice,
    OddsSemantics,
    extract_prices,
    genuine_close,
    select_benchmark_bookmaker,
)
from src.research.prospective.player_state import (
    PlayerMatchObservation,
    build_player_state,
    build_usual_starting_probabilities,
)
from src.research.prospective.residual_model import RidgeLogisticResidualModel, ResidualSample
from src.research.prospective.storage import CaptureStore
from src.research.prospective.vintages import (
    ProspectiveVintage,
    compute_cutoff,
    is_consultable,
)

KICKOFF = 1_700_000_000.0


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_live_base_url_has_api_suffix():
    assert LIVE_BASE_URL.endswith("/api")


def test_discrepancies_documented():
    topics = {d.topic for d in KNOWN_DISCREPANCIES}
    assert {"base_url", "authentication"} <= topics


def test_endpoint_path_renders():
    assert endpoint_path(Endpoint.MATCH_ODDS, match_id="mt_1") == "/football/matches/mt_1/odds"


def test_client_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("THESTATSAPI_API_KEY", raising=False)
    monkeypatch.delenv("THESTATS_API_KEY", raising=False)
    client = ProspectiveApiClient()
    assert not client.is_configured
    with pytest.raises(ProspectiveConfigError):
        client.get(Endpoint.MATCH_ODDS, match_id="mt_1")


def test_client_uses_bearer_header(monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "secret-key-value")
    seen = {}

    def transport(url, headers, params):
        seen["url"] = url
        seen["headers"] = headers
        return 200, {"ok": True}

    client = ProspectiveApiClient(transport=transport)
    client.get(Endpoint.MATCH_ODDS, match_id="mt_1")
    assert seen["headers"]["Authorization"] == "Bearer secret-key-value"
    assert seen["url"].startswith(LIVE_BASE_URL)


def test_client_404_returns_none(monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    client = ProspectiveApiClient(transport=lambda u, h, p: (404, None))
    assert client.get(Endpoint.MATCH_LINEUPS, match_id="mt_1") is None


# ---------------------------------------------------------------------------
# Point-in-time
# ---------------------------------------------------------------------------


def test_vintage_offsets_ordered():
    offs = [v.offset_seconds for v in (
        ProspectiveVintage.EARLY, ProspectiveVintage.MID,
        ProspectiveVintage.LATE, ProspectiveVintage.FINAL)]
    assert offs == sorted(offs, reverse=True)


def test_final_lineup_cannot_leak_into_early():
    early = compute_cutoff("f", KICKOFF, ProspectiveVintage.EARLY)
    # A confirmed XI observed 90m before kickoff is AFTER the early cutoff AND a
    # lineup concept => not consultable at EARLY on both counts.
    assert not is_consultable(concept="confirmed_xi", observed_at=KICKOFF - 5400, cutoff=early)


def test_late_may_consult_confirmed_lineup():
    late = compute_cutoff("f", KICKOFF, ProspectiveVintage.LATE)
    assert is_consultable(concept="confirmed_xi", observed_at=KICKOFF - 4000, cutoff=late)


def test_missing_observed_at_never_consultable():
    late = compute_cutoff("f", KICKOFF, ProspectiveVintage.LATE)
    assert not is_consultable(concept="odds", observed_at=None, cutoff=late)


def test_post_cutoff_observation_excluded():
    early = compute_cutoff("f", KICKOFF, ProspectiveVintage.EARLY)
    assert not is_consultable(concept="odds", observed_at=KICKOFF - 3600, cutoff=early)
    assert is_consultable(concept="odds", observed_at=KICKOFF - 90000, cutoff=early)


def test_equal_timestamp_is_consultable_deterministic():
    late = compute_cutoff("f", KICKOFF, ProspectiveVintage.LATE)
    assert is_consultable(concept="odds", observed_at=late.cutoff_ts, cutoff=late)


# ---------------------------------------------------------------------------
# Odds semantics
# ---------------------------------------------------------------------------


def _snap(odds, observed_at, sem=OddsSemantics.PROSPECTIVE_SNAPSHOT):
    return CapturedPrice("pinnacle", "match_corners", "over", 9.5, odds, sem, observed_at, "h")


def test_opening_is_not_prospective_snapshot():
    assert OddsSemantics.API_OPENING != OddsSemantics.PROSPECTIVE_SNAPSHOT


def test_last_seen_is_not_genuine_close():
    ls = [_snap(1.9, None, OddsSemantics.API_LAST_SEEN)]
    assert genuine_close(ls, kickoff_ts=KICKOFF) is None


def test_genuine_close_requires_observed_before_kickoff():
    only_after = [_snap(2.0, KICKOFF + 60)]
    assert genuine_close(only_after, kickoff_ts=KICKOFF) is None


def test_genuine_close_picks_latest_before_kickoff():
    snaps = [_snap(1.9, KICKOFF - 3600), _snap(1.95, KICKOFF - 600), _snap(2.1, KICKOFF + 60)]
    gc = genuine_close(snaps, kickoff_ts=KICKOFF)
    assert gc is not None
    assert gc.observed_at == KICKOFF - 600
    assert gc.price.semantics == OddsSemantics.PROSPECTIVE_LAST_BEFORE_KICKOFF


def test_bookmaker_hierarchy_deterministic_no_cherry_picking():
    assert select_benchmark_bookmaker(["bet365", "pinnacle"]) == "pinnacle"
    assert select_benchmark_bookmaker(["paddy-power", "bet365"]) == "bet365"
    assert select_benchmark_bookmaker(["betfair-exchange"]) is None


def test_null_not_zero_in_extract():
    payload = {"data": {"bookmakers": [{
        "bookmaker": "Pinnacle",
        "markets": {"match_corners": {"9.5": {"over": {"last_seen": None},
                                              "under": {"last_seen": "2.0"}}}},
    }]}}
    prices = extract_prices(payload, payload_hash="h")
    # Over price was null => skipped (not stored as 0); under present.
    sels = {(p.selection, p.decimal_odds) for p in prices}
    assert ("under", 2.0) in sels
    assert all(not (p.selection == "over") for p in prices)


def test_market_identity_preserved_in_extract():
    payload = {"data": {"bookmakers": [{
        "bookmaker": "Bet365",
        "markets": {"total_goals": {"2.5": {"over": {"last_seen": "1.9"},
                                            "under": {"last_seen": "2.0"}}}},
    }]}}
    prices = extract_prices(payload, payload_hash="h")
    p = next(x for x in prices if x.selection == "over")
    assert (p.bookmaker, p.market, p.line) == ("bet365", "total_goals", 2.5)


# ---------------------------------------------------------------------------
# Market prior
# ---------------------------------------------------------------------------


def test_no_market_when_side_missing():
    mp = build_market_prior(
        fixture_id="f", market="total_goals", line=2.5, selection="over",
        over_price=_snap(1.9, KICKOFF - 3600), under_price=None, cutoff_ts=KICKOFF - 3600)
    assert mp.availability_status == MarketAvailability.NO_MARKET
    assert mp.fair_probability is None


def test_valid_market_devigs_and_scores_fresh():
    over = CapturedPrice("pinnacle", "total_goals", "over", 2.5, 1.9,
                         OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    under = CapturedPrice("pinnacle", "total_goals", "under", 2.5, 2.0,
                          OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    mp = build_market_prior(
        fixture_id="f", market="total_goals", line=2.5, selection="over",
        over_price=over, under_price=under, cutoff_ts=KICKOFF)
    assert mp.availability_status == MarketAvailability.VALID_MARKET
    assert 0.0 < mp.fair_probability < 1.0
    assert mp.bookmaker == "pinnacle"


def test_stale_market_when_observed_after_cutoff():
    over = _snap(1.9, KICKOFF)  # observed after an earlier cutoff
    under = CapturedPrice("pinnacle", "match_corners", "under", 9.5, 2.0,
                          OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF, "h")
    mp = build_market_prior(
        fixture_id="f", market="match_corners", line=9.5, selection="over",
        over_price=over, under_price=under, cutoff_ts=KICKOFF - 3600)
    assert mp.availability_status == MarketAvailability.STALE_MARKET


# ---------------------------------------------------------------------------
# Fundamental / disagreement
# ---------------------------------------------------------------------------


def test_disagreement_sign():
    over = CapturedPrice("pinnacle", "total_goals", "over", 2.5, 2.0,
                         OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    under = CapturedPrice("pinnacle", "total_goals", "under", 2.5, 2.0,
                          OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    mp = build_market_prior(
        fixture_id="f", market="total_goals", line=2.5, selection="over",
        over_price=over, under_price=under, cutoff_ts=KICKOFF)  # market ~0.5
    ff = FundamentalForecast("f", "total_goals", 2.5, "over", 0.62, KICKOFF, "champ-v1", {})
    dis = compute_disagreement(ff, mp)
    assert dis.available
    assert dis.fundamental_minus_market > 0  # 0.62 > ~0.5


def test_disagreement_misalignment_raises():
    over = CapturedPrice("pinnacle", "total_goals", "over", 2.5, 2.0,
                         OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    under = CapturedPrice("pinnacle", "total_goals", "under", 2.5, 2.0,
                          OddsSemantics.PROSPECTIVE_SNAPSHOT, KICKOFF - 3000, "h")
    mp = build_market_prior(
        fixture_id="f", market="total_goals", line=2.5, selection="over",
        over_price=over, under_price=under, cutoff_ts=KICKOFF)
    ff = FundamentalForecast("f", "match_corners", 9.5, "over", 0.5, KICKOFF, "v", {})
    with pytest.raises(ValueError):
        compute_disagreement(ff, mp)


# ---------------------------------------------------------------------------
# Lineups
# ---------------------------------------------------------------------------


def _lineup_payload():
    return {"data": {"match_id": "mt_1", "confirmed": True,
        "home": {"id": "tm_h", "formation": "4-3-3",
                 "starting_xi": [{"id": "pl_1", "position": "G", "jersey_number": 1},
                                 {"id": "pl_2", "position": "D", "jersey_number": 2}],
                 "substitutes": [{"id": "pl_9", "position": "F", "jersey_number": 9}]},
        "away": {"id": "tm_a", "formation": "4-4-2",
                 "starting_xi": [{"id": "pl_20", "position": "G", "jersey_number": 1}],
                 "substitutes": []}}}


def test_stable_player_ids_required():
    with pytest.raises(LineupError):
        TeamLineup("tm", None, (), ())  # ok empty
        from src.research.prospective.lineup_state import LineupPlayer
        LineupPlayer("", None, None, True)


def test_lineup_home_away_and_bench():
    nl = normalize_lineup(_lineup_payload(), fixture_id="mt_1", observed_at=KICKOFF - 4000)
    assert nl.home.team_id == "tm_h"
    assert "pl_1" in nl.home.starter_ids
    assert "pl_9" in nl.home.bench_ids
    assert "pl_9" not in nl.home.starter_ids  # bench != starter
    assert nl.home.formation == "4-3-3"
    assert nl.pit_usable  # we passed our own observed_at


def test_missing_lineup_fails_neutrally():
    assert normalize_lineup(None, fixture_id="mt_1", observed_at=KICKOFF) is None
    assert normalize_lineup({"data": {}}, fixture_id="mt_1", observed_at=KICKOFF) is None


def test_historical_lineup_without_capture_time_not_pit_usable():
    nl = normalize_lineup(_lineup_payload(), fixture_id="mt_1", observed_at=None)
    assert nl is not None and not nl.pit_usable


def test_lineup_delta_continuity_and_availability():
    nl = normalize_lineup(_lineup_payload(), fixture_id="mt_1", observed_at=KICKOFF - 4000)
    expected = ExpectedXIState(
        usual_starting_probability={"pl_1": 0.9, "pl_2": 0.8, "pl_3": 0.7},
        modal_recent_formation="4-4-2")
    delta = compute_lineup_delta(nl.home, expected, fixture_id="mt_1")
    # pl_3 (usual starter) is missing today.
    assert delta.missing_usual_starters == 1
    assert delta.availability_reasons["pl_3"] == AvailabilityReason.UNKNOWN
    assert delta.formation_changed is True  # 4-3-3 vs modal 4-4-2
    assert 0.0 <= delta.xi_continuity_score <= 1.0


# ---------------------------------------------------------------------------
# Player state
# ---------------------------------------------------------------------------


def _pmo(pid, ts, minutes, started, **kw):
    return PlayerMatchObservation(pid, "tm", ts, minutes, started, **kw)


def test_future_and_current_matches_excluded():
    obs = [
        _pmo("pl_1", KICKOFF - 10 * 86400, 90, True, goals=1),
        _pmo("pl_1", KICKOFF, 90, True, goals=5),          # current fixture => excluded
        _pmo("pl_1", KICKOFF + 86400, 90, True, goals=5),  # future => excluded
    ]
    st = build_player_state("pl_1", obs, cutoff_ts=KICKOFF)
    assert st.appearances == 1
    assert st.goals_per_90 == pytest.approx(1.0)


def test_zero_minutes_denominator_is_none_not_zero():
    obs = [_pmo("pl_1", KICKOFF - 86400, 0, False, goals=0)]
    st = build_player_state("pl_1", obs, cutoff_ts=KICKOFF)
    assert st.goals_per_90 is None  # 0 minutes => undefined, not 0.0


def test_missing_stat_stays_missing():
    obs = [_pmo("pl_1", KICKOFF - 86400, 90, True)]  # no goals reported
    st = build_player_state("pl_1", obs, cutoff_ts=KICKOFF)
    assert st.goals_per_90 is None


def test_usual_starting_probability_prior_only():
    obs = [
        _pmo("pl_1", KICKOFF - 3 * 86400, 90, True),
        _pmo("pl_1", KICKOFF - 2 * 86400, 90, True),
        _pmo("pl_2", KICKOFF - 2 * 86400, 20, False),
        _pmo("pl_1", KICKOFF + 86400, 90, True),  # future ignored
    ]
    probs = build_usual_starting_probabilities(obs, team_id="tm", cutoff_ts=KICKOFF)
    assert probs["pl_1"] == pytest.approx(1.0)
    assert "pl_2" not in probs  # never started


# ---------------------------------------------------------------------------
# Residual model
# ---------------------------------------------------------------------------


def test_unfitted_reproduces_market():
    m = RidgeLogisticResidualModel()
    assert m.predict(ResidualSample(0.62, {"d": 0.4})) == pytest.approx(0.62)


def test_zero_features_reproduce_market_after_fit():
    m = RidgeLogisticResidualModel(l2=1.0).fit(
        [ResidualSample(0.55, {"d": 1.0}, True), ResidualSample(0.55, {"d": -1.0}, False)] * 20)
    assert m.predict(ResidualSample(0.55, {})) == pytest.approx(0.55, abs=1e-6)


def test_positive_and_negative_delta_directions():
    m = RidgeLogisticResidualModel(l2=0.5).fit(
        [ResidualSample(0.5, {"d": 1.0}, True), ResidualSample(0.5, {"d": -1.0}, False)] * 40)
    hi = m.predict(ResidualSample(0.5, {"d": 2.0}))
    lo = m.predict(ResidualSample(0.5, {"d": -2.0}))
    assert hi > 0.5 > lo


def test_missing_feature_not_extreme():
    m = RidgeLogisticResidualModel(l2=1.0).fit(
        [ResidualSample(0.55, {"d": 1.0}, True), ResidualSample(0.55, {"d": -1.0}, False)] * 20)
    p = m.predict(ResidualSample(0.55, {}))
    assert 0.5 < p < 0.6  # stays near market, not extreme


def test_deterministic_fit():
    data = [ResidualSample(0.5, {"d": (i % 3) - 1}, i % 2 == 0) for i in range(90)]
    a = RidgeLogisticResidualModel(l2=1.0).fit(list(data))
    b = RidgeLogisticResidualModel(l2=1.0).fit(list(data))
    s = ResidualSample(0.5, {"d": 0.7})
    assert a.predict(s) == pytest.approx(b.predict(s))


def test_standardization_fit_inside_training_only():
    # Train on features centered around 10; predict on a new value uses frozen
    # training mean/std (no refit), so it does not blow up.
    m = RidgeLogisticResidualModel(l2=1.0).fit(
        [ResidualSample(0.5, {"d": 10.0 + (i % 5)}, i % 2 == 0) for i in range(50)])
    assert m._mean is not None and m._mean[0] > 5.0
    p = m.predict(ResidualSample(0.5, {"d": 100.0}))
    assert 0.0 < p < 1.0


# ---------------------------------------------------------------------------
# Decomposition / resolution / evaluation
# ---------------------------------------------------------------------------


def test_common_support_intersection():
    a = {("f1",): 0.5, ("f2",): 0.5}
    b = {("f2",): 0.6, ("f3",): 0.6}
    assert common_support(a, b) == [("f2",)]


def test_resolution_reports_sharpness_and_murphy():
    probs = [0.1, 0.9, 0.2, 0.8, 0.5, 0.5]
    outs = [False, True, False, True, True, False]
    r = compute_resolution(probs, outs, n_bins=5)
    assert r.std_p > 0
    assert r.uncertainty == pytest.approx(0.25)  # base rate 0.5
    assert r.resolution >= 0 and r.reliability >= 0


def test_decomposition_common_support_only():
    keys = [("f1",), ("f2",)]
    layers = {
        "M0": {("f1",): 0.5, ("f2",): 0.5, ("f3",): 0.5},
        "M3": {("f1",): 0.6, ("f2",): 0.4},
    }
    outcomes = {("f1",): True, ("f2",): False}
    scores = run_decomposition(layers, outcomes, layer_order=["M0", "M3"])
    assert all(s.n == 2 for s in scores)  # f3 excluded (not common)
    assert scores[1].delta_log_loss_vs_prev is not None


def test_disagreement_buckets_fixed_thresholds():
    assert bucket_for(0.60, 0.50).value == "model_much_higher"
    assert bucket_for(0.505, 0.50).value == "agree"
    assert bucket_for(0.40, 0.50).value == "model_much_lower"


def test_bucket_diagnostics_clv():
    rows = [DisagreementRow(0.6, 0.5, outcome=True, later_market_prob=0.55),
            DisagreementRow(0.4, 0.5, outcome=False, later_market_prob=0.45)]
    diags = {d.bucket: d for d in bucket_diagnostics(rows)}
    assert diags["model_much_higher"].mean_clv_pp == pytest.approx(0.05)
    assert diags["model_much_lower"].mean_clv_pp == pytest.approx(-0.05)


def test_clv_directional_hit_rate():
    # model bullish, market later moves up => hit; model bearish, market up => miss
    rows = [CLVRow("f1", 0.6, 0.5, 0.55), CLVRow("f2", 0.4, 0.5, 0.55)]
    rep = evaluate_clv(rows)
    assert rep.n == 2
    assert rep.directional_hit_rate == pytest.approx(0.5)


def test_movement_none_when_endpoint_missing():
    mv = compute_movement(fixture_id="f", market="total_goals", line=2.5, selection="over",
                          vintage_probs={"early": 0.5, "late": None})
    assert mv.moves["mid_to_late_move"] is None
    assert mv.moves["early_to_mid_move"] is None


def test_movement_log_odds():
    mv = compute_movement(fixture_id="f", market="total_goals", line=2.5, selection="over",
                          vintage_probs={"mid": 0.5, "late": 0.6})
    expected = math.log(0.6 / 0.4) - math.log(0.5 / 0.5)
    assert mv.moves["mid_to_late_move"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Storage (append-only)
# ---------------------------------------------------------------------------


def test_capture_store_append_only_idempotent(tmp_path: Path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    rec = CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="odds:total_goals:over:2.5", value=1.9,
        observed_at=KICKOFF - 3600, retrieved_at=KICKOFF - 3600, raw_payload_hash="h")
    assert store.append(rec) is True
    assert store.append(rec) is False  # idempotent, not overwritten
    assert len(list(store.read_all())) == 1


def test_capture_store_replay_to_observation_store(tmp_path: Path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    store.append(CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="odds:total_goals:over:2.5", value=1.9,
        observed_at=KICKOFF - 3600, retrieved_at=KICKOFF - 3600, raw_payload_hash="h"))
    obs_store = store.to_observation_store()
    assert len(obs_store) == 1


def test_missing_sentinel_roundtrips(tmp_path: Path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    rec = CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="lineup", value=MISSING,
        observed_at=KICKOFF, retrieved_at=KICKOFF, raw_payload_hash="h")
    store.append(rec)
    back = list(store.read_all())[0]
    assert back.value is MISSING
