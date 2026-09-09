"""Tests for the live-capture phase (branch research/prospective-live-capture).

Covers Part 33 categories: live client contract, scheduling/vintage quality,
odds continuity + genuine close, lineups, injuries, price discovery, recovery,
time/DST, postponement, quota, schema drift, and the CLI capture-due path.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.research.prospective.api_contract import LIVE_BASE_URL, Endpoint
from src.research.prospective.availability import (
    UnavailabilityKind,
    normalize_availability,
)
from src.research.prospective.capture import (
    CaptureRecord,
    ProspectiveApiClient,
    ProspectiveConfigError,
    ProspectiveTransportError,
)
from src.research.prospective.cli import ProspectiveCollector, _parse_utc, main
from src.research.prospective.odds_capture import (
    CapturedPrice,
    CloseStatus,
    OddsSemantics,
    resolve_genuine_close,
)
from src.research.prospective.price_discovery import (
    PriceObservation,
    line_movement,
    price_movement_logit,
    signed_clv_direction,
)
from src.research.prospective.quality import (
    HealthState,
    SchemaDriftError,
    build_quality_report,
    validate_lineup_schema,
    validate_match_schema,
    validate_odds_schema,
)
from src.research.prospective.quota import estimate_budget, parse_rate_limit
from src.research.prospective.scheduler import (
    CaptureKind,
    CaptureScheduler,
    UpcomingFixture,
)
from src.research.prospective.storage import CaptureStore
from src.research.prospective.vintage_quality import (
    VintageQuality,
    best_capture_for_vintage,
    classify_capture,
)
from src.research.prospective.vintages import ProspectiveVintage

K = 1_700_000_000.0


# --------------------------------------------------------------------------
# Live client contract
# --------------------------------------------------------------------------


def test_client_base_url_and_bearer(monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "sekret")
    seen = {}

    def transport(url, headers, params):
        seen.update(url=url, headers=headers)
        return 200, {"data": {}}

    ProspectiveApiClient(transport=transport).get(Endpoint.MATCH_ODDS, match_id="mt_1")
    assert seen["url"].startswith(LIVE_BASE_URL)
    assert seen["headers"]["Authorization"] == "Bearer sekret"


def test_client_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("THESTATSAPI_API_KEY", raising=False)
    monkeypatch.delenv("THESTATS_API_KEY", raising=False)
    with pytest.raises(ProspectiveConfigError):
        ProspectiveApiClient().get(Endpoint.MATCHES)


def test_client_4xx_fails_clearly(monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    c = ProspectiveApiClient(transport=lambda u, h, p: (401, None))
    with pytest.raises(ProspectiveTransportError):
        c.get(Endpoint.MATCHES)


def test_client_404_is_none(monkeypatch):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    c = ProspectiveApiClient(transport=lambda u, h, p: (404, None))
    assert c.get(Endpoint.MATCH_LINEUPS, match_id="mt_1") is None


def test_api_key_alias_resolved(monkeypatch):
    """The shorter THESTATS_API_KEY name is accepted as an alias."""
    from src.research.prospective.api_contract import api_key_available, resolve_api_key

    monkeypatch.delenv("THESTATSAPI_API_KEY", raising=False)
    monkeypatch.setenv("THESTATS_API_KEY", "alias-key")
    assert api_key_available()
    assert resolve_api_key() == "alias-key"
    assert ProspectiveApiClient().is_configured


def test_documented_key_preferred_over_alias(monkeypatch):
    from src.research.prospective.api_contract import resolve_api_key

    monkeypatch.setenv("THESTATSAPI_API_KEY", "primary")
    monkeypatch.setenv("THESTATS_API_KEY", "alias")
    assert resolve_api_key() == "primary"


def test_discover_upcoming_scoped_to_window_and_universe(tmp_path, monkeypatch):
    """Discovery bounds by date_from/date_to + universe comp ids and horizon."""
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    ko_near = "2020-01-02T00:00:00Z"     # within a 48h window from 'now' below
    ko_far = "2020-02-01T00:00:00Z"      # outside the horizon
    seen_params = []

    def transport(url, headers, params):
        seen_params.append(params)
        # Return one near and one far fixture regardless of query.
        return 200, {"data": [
            {"id": "mt_near", "utc_date": ko_near},
            {"id": "mt_far", "utc_date": ko_far},
        ]}

    client = ProspectiveApiClient(transport=transport)
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    now = _parse_utc("2020-01-01T00:00:00Z")
    coll = ProspectiveCollector(client, store, clock=lambda: now)
    fx = coll.discover_upcoming(hours=48)
    ids = {f.fixture_id for f in fx}
    # Only the near fixture is within the 48h horizon; far one is dropped.
    assert ids == {"mt_near"}
    # The query was scoped to the universe (EPL comp id) with date filters.
    assert any(p.get("competition_id") == "comp_3039" for p in seen_params)
    assert all("date_from" in p and "date_to" in p for p in seen_params)


def test_rate_limit_headers_parsed():
    st = parse_rate_limit({
        "X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "1700",
        "X-Monthly-Quota-Limit": "50000", "X-Monthly-Quota-Remaining": "100",
        "Retry-After": "30",
    })
    assert st.minute_limit == 60 and st.monthly_remaining == 100
    assert st.retry_after == 30.0
    assert not st.minute_uncapped


def test_rate_limit_pause_on_exhaustion_and_unknown():
    exhausted = parse_rate_limit({"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "0",
                                  "X-Monthly-Quota-Limit": "-1", "X-Monthly-Quota-Remaining": "-1"})
    assert exhausted.should_pause()
    unknown = parse_rate_limit({})  # absent headers => conservative pause
    assert unknown.should_pause()


def test_budget_sustainability():
    b = estimate_budget(odds_snapshots_per_fixture=6, lineup_polls_per_fixture=4,
                        context_requests_per_fixture=2, fixtures_per_day=20, monthly_limit=50000)
    assert b.requests_per_fixture == 12
    assert b.requests_per_month == 12 * 20 * 30
    assert b.sustainable is True
    tight = estimate_budget(odds_snapshots_per_fixture=50, lineup_polls_per_fixture=50,
                           context_requests_per_fixture=50, fixtures_per_day=100, monthly_limit=1000)
    assert tight.sustainable is False
    unknown = estimate_budget(odds_snapshots_per_fixture=1, lineup_polls_per_fixture=1,
                             context_requests_per_fixture=1, fixtures_per_day=1)
    assert unknown.sustainable is None


# --------------------------------------------------------------------------
# Scheduling / vintage quality
# --------------------------------------------------------------------------


def test_vintage_targets_classified():
    for v, off in [(ProspectiveVintage.EARLY, 24 * 3600), (ProspectiveVintage.MID, 6 * 3600),
                   (ProspectiveVintage.LATE, 3600), (ProspectiveVintage.FINAL, 900)]:
        q = classify_capture(vintage=v, observed_at=K - off, kickoff_ts=K)
        assert q.quality == VintageQuality.ON_TARGET
        assert q.seconds_to_kickoff == pytest.approx(off)


def test_off_target_observation_retains_true_age():
    # A T-3h capture assessed against MID (~6h): NEAR/OFF but real age retained.
    q = classify_capture(vintage=ProspectiveVintage.MID, observed_at=K - 3 * 3600, kickoff_ts=K)
    assert q.seconds_to_kickoff == pytest.approx(3 * 3600)
    assert q.quality in (VintageQuality.NEAR_TARGET, VintageQuality.OFF_TARGET)


def test_missed_vintage_represented():
    q = best_capture_for_vintage(vintage=ProspectiveVintage.LATE,
                                 observed_ats=[K + 10], kickoff_ts=K)  # only post-kickoff
    assert q.quality == VintageQuality.MISSED


def test_post_kickoff_flagged():
    q = classify_capture(vintage=ProspectiveVintage.FINAL, observed_at=K + 1, kickoff_ts=K)
    assert q.post_kickoff and q.quality == VintageQuality.OFF_TARGET


def test_scheduler_due_from_persisted_state(tmp_path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    sched = CaptureScheduler(store)
    fx = UpcomingFixture("mt_1", kickoff_ts=K)
    # 55 minutes before kickoff => LATE odds + lineup poll due.
    due = sched.due_for_fixture(fx, now=K - 55 * 60)
    kinds = {(d.vintage, d.kind) for d in due}
    assert (ProspectiveVintage.LATE, CaptureKind.ODDS) in kinds
    assert (ProspectiveVintage.LATE, CaptureKind.LINEUP) in kinds


def test_scheduler_skips_already_captured_vintage(tmp_path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    # An on-target LATE odds capture already exists.
    store.append(CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="odds:total_goals:over:2.5:pinnacle", value=1.9,
        observed_at=K - 60 * 60, retrieved_at=K - 60 * 60, raw_payload_hash="h", event_time=K))
    sched = CaptureScheduler(store)
    due = sched.due_for_fixture(UpcomingFixture("mt_1", kickoff_ts=K), now=K - 55 * 60)
    assert not any(d.kind == CaptureKind.ODDS and d.vintage == ProspectiveVintage.LATE for d in due)


def test_scheduler_rescheduled_kickoff_does_not_rewrite(tmp_path):
    # An EARLY capture recorded under the ORIGINAL kickoff must survive when the
    # scheduler later sees a new kickoff (append-only; classification uses the
    # kickoff supplied at query time, old record untouched).
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    store.append(CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="odds:total_goals:over:2.5:pinnacle", value=1.9,
        observed_at=K - 24 * 3600, retrieved_at=K - 24 * 3600, raw_payload_hash="h", event_time=K))
    before = list(store.read_all())
    CaptureScheduler(store).due_for_fixture(
        UpcomingFixture("mt_1", kickoff_ts=K + 86400), now=K)  # kickoff moved +1d
    after = list(store.read_all())
    assert [r.to_dict() for r in before] == [r.to_dict() for r in after]


# --------------------------------------------------------------------------
# Odds continuity + genuine close
# --------------------------------------------------------------------------


def _snap(book, line, odds, ts, sem=OddsSemantics.PROSPECTIVE_SNAPSHOT):
    return CapturedPrice(book, "total_goals", "over", line, odds, sem, ts, "h")


def test_genuine_close_same_key_only():
    snaps = [_snap("pinnacle", 2.5, 1.9, K - 3600), _snap("pinnacle", 2.5, 1.95, K - 600)]
    r = resolve_genuine_close(snaps, kickoff_ts=K, bookmaker="pinnacle",
                              market="total_goals", selection="over", line=2.5)
    assert r.status == CloseStatus.GENUINE_CLOSE and r.close.observed_at == K - 600


def test_genuine_close_unknown_kickoff():
    r = resolve_genuine_close([_snap("pinnacle", 2.5, 1.9, K - 600)], kickoff_ts=None,
                              bookmaker="pinnacle", market="total_goals", selection="over", line=2.5)
    assert r.status == CloseStatus.NO_GENUINE_CLOSE and r.reason == "unknown_kickoff"


def test_genuine_close_never_last_seen():
    ls = [_snap("pinnacle", 2.5, 1.9, K - 600, OddsSemantics.API_LAST_SEEN)]
    r = resolve_genuine_close(ls, kickoff_ts=K, bookmaker="pinnacle",
                              market="total_goals", selection="over", line=2.5)
    assert r.status == CloseStatus.NO_GENUINE_CLOSE


def test_genuine_close_post_kickoff_excluded():
    r = resolve_genuine_close([_snap("pinnacle", 2.5, 1.9, K + 60)], kickoff_ts=K,
                              bookmaker="pinnacle", market="total_goals", selection="over", line=2.5)
    assert r.status == CloseStatus.NO_GENUINE_CLOSE


def test_price_movement_same_key():
    a = PriceObservation("pinnacle", "total_goals", "over", 2.5, K - 3600, 0.5)
    b = PriceObservation("pinnacle", "total_goals", "over", 2.5, K - 600, 0.6)
    assert price_movement_logit(a, b) == pytest.approx(math.log(0.6 / 0.4))


def test_cross_bookmaker_movement_refused():
    a = PriceObservation("pinnacle", "total_goals", "over", 2.5, K - 3600, 0.5)
    b = PriceObservation("bet365", "total_goals", "over", 2.5, K - 600, 0.6)
    assert price_movement_logit(a, b) is None


def test_cross_line_movement_refused_but_line_move_tracked():
    a = PriceObservation("pinnacle", "total_goals", "over", 2.5, K - 3600, 0.5)
    b = PriceObservation("pinnacle", "total_goals", "over", 3.5, K - 600, 0.6)
    assert price_movement_logit(a, b) is None
    lm = line_movement(a, b)
    assert lm is not None and lm.changed


def test_signed_clv_direction():
    # model bullish (+), market later moves up (+) => favourable (+)
    assert signed_clv_direction(model_disagreement=0.3, current_market_logit=0.0,
                                later_market_logit=0.4) == pytest.approx(0.4)
    # model bearish (-), market up => unfavourable (-)
    assert signed_clv_direction(model_disagreement=-0.3, current_market_logit=0.0,
                                later_market_logit=0.4) == pytest.approx(-0.4)
    assert signed_clv_direction(model_disagreement=None, current_market_logit=0.0,
                                later_market_logit=0.4) is None


# --------------------------------------------------------------------------
# Injuries / availability
# --------------------------------------------------------------------------


def test_injury_explicit_semantics_preserved():
    snap = normalize_availability(
        {"data": {"injuries": [{"player_id": "pl_1", "status": "out", "reason": "muscle_injury",
                                "expected_return": "2026-07-20T00:00:00Z", "active": True}],
                  "suspensions": [{"player_id": "pl_2", "reason": "yellow_card_accumulation",
                                   "matches": 1, "active": True}]}},
        team_id="tm_1", observed_at=K)
    inj = snap.player_status("pl_1")
    assert inj.kind == UnavailabilityKind.INJURY and inj.reason == "muscle_injury"
    susp = snap.player_status("pl_2")
    assert susp.kind == UnavailabilityKind.SUSPENSION
    assert snap.observed_at == K  # retrieval timestamp retained


def test_absence_not_inferred_as_injury():
    snap = normalize_availability({"data": {"injuries": [], "suspensions": []}},
                                  team_id="tm_1", observed_at=K)
    # A player not listed has NO status (never inferred injured from absence).
    assert snap.player_status("pl_999") is None
    assert not snap.available


def test_missing_injury_endpoint_neutral():
    snap = normalize_availability(None, team_id="tm_1", observed_at=K)
    assert not snap.available and snap.injuries == ()


# --------------------------------------------------------------------------
# Schema drift
# --------------------------------------------------------------------------


def test_schema_drift_missing_field():
    with pytest.raises(SchemaDriftError):
        validate_odds_schema({"data": {}})
    with pytest.raises(SchemaDriftError):
        validate_match_schema({"data": {"id": "mt_1"}})  # missing utc_date/teams


def test_schema_drift_wrong_type():
    with pytest.raises(SchemaDriftError):
        validate_lineup_schema({"data": {"home": [], "away": {}}})  # home wrong type


def test_valid_schemas_pass():
    validate_odds_schema({"data": {"bookmakers": []}})
    validate_match_schema({"data": {"id": "mt_1", "utc_date": "2026-01-01T00:00:00Z",
                                    "home_team": {}, "away_team": {}}})
    validate_lineup_schema({"data": {"home": {}, "away": {}}})


# --------------------------------------------------------------------------
# Time handling
# --------------------------------------------------------------------------


def test_parse_utc_z_and_offset():
    a = _parse_utc("2026-01-15T15:00:00.000Z")
    b = _parse_utc("2026-01-15T15:00:00+00:00")
    assert a == b
    # A winter vs summer date both parse to correct UTC (no DST drift for UTC).
    assert _parse_utc("2026-07-15T15:00:00Z") is not None
    assert _parse_utc("not-a-date") is None


# --------------------------------------------------------------------------
# Recovery / CLI capture-due
# --------------------------------------------------------------------------


def _collector(tmp_path, monkeypatch, responses, clock_seq):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")

    def transport(url, headers, params):
        if url.endswith("/odds"):
            body = responses.get("/odds")
        elif url.endswith("/lineups"):
            body = responses.get("/lineups")
        else:
            body = responses.get("/football/matches")
        return (200, body) if body is not None else (404, None)

    client = ProspectiveApiClient(transport=transport)
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    it = iter(clock_seq)
    return ProspectiveCollector(client, store, clock=lambda: next(it)), store


def test_capture_due_restart_safe(tmp_path, monkeypatch):
    # Upcoming fixture 55m before kickoff; odds present, lineup 404.
    ko_iso = "2020-01-01T00:00:00Z"
    ko = _parse_utc(ko_iso)
    responses = {
        "/football/matches": {"data": [{"id": "mt_1", "utc_date": ko_iso}]},
        "/odds": {"data": {"match_id": "mt_1", "bookmakers": [{
            "bookmaker": "Pinnacle",
            "markets": {"total_goals": {"2.5": {"over": {"last_seen": "1.90"},
                                                "under": {"last_seen": "2.00"}}}}}]}},
        "/lineups": None,
    }
    now = ko - 55 * 60
    coll, store = _collector(tmp_path, monkeypatch, responses, clock_seq=[now] * 50)
    r1 = coll.capture_due(hours=30)
    assert r1.odds_captured == 2  # over+under at LATE
    # Rerun at the same time: nothing new (idempotent + already-captured vintage).
    coll2, _ = _collector(tmp_path, monkeypatch, responses, clock_seq=[now] * 50)
    coll2.store = store  # same store file
    r2 = ProspectiveCollector(coll2.client, store, clock=lambda: now).capture_due(hours=30)
    assert r2.odds_captured == 0


def test_main_quality_report_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("THESTATSAPI_API_KEY", raising=False)
    rc = main(["--capture-root", str(tmp_path), "quality-report"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "health" in out


def test_quality_report_health_no_fixtures(tmp_path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    report = build_quality_report(store, now=K)
    assert report.health == HealthState.NO_UPCOMING_FIXTURES
