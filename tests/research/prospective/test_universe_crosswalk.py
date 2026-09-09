"""Tests for the data-driven universe: crosswalk, coverage, activation, quota,
funnel, and scoped discovery metrics (Part 27)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.prospective.activation import active_competition_ids, active_universe
from src.research.prospective.coverage_matrix import (
    CaptureClass,
    MarketEligibility,
    build_coverage_matrix,
    classify,
)
from src.research.prospective.coverage_funnel import analysis_support, competition_funnel
from src.research.prospective.crosswalk import (
    CrosswalkEntry,
    IdentityStatus,
    build_crosswalk,
    crosswalk_summary,
)
from src.research.prospective.quota import (
    FixtureCostModel,
    QuotaGuard,
    parse_rate_limit,
    plan_allocation,
)
from src.research.prospective.recon import CompetitionCoverage
from src.research.prospective.storage import CaptureStore
from src.research.prospective.capture import CaptureRecord

K = 1_700_000_000.0


# --------------------------------------------------------------------------
# Crosswalk / identity
# --------------------------------------------------------------------------


def test_crosswalk_every_league_present_and_deterministic():
    a = build_crosswalk()
    b = build_crosswalk()
    assert [e.to_dict() for e in a] == [e.to_dict() for e in b]  # deterministic
    # Registry has 49 leagues; none silently omitted.
    assert len(a) == 49


def test_crosswalk_status_counts():
    s = crosswalk_summary(build_crosswalk())
    assert s["VERIFIED"] == 46
    assert s["AMBIGUOUS"] == 2
    assert s["API_UNSUPPORTED"] == 1
    assert s["total"] == 49


def test_verified_requires_single_id_and_ambiguous_never_joined():
    cw = build_crosswalk()
    for e in cw:
        if e.identity_status == IdentityStatus.VERIFIED:
            assert e.thestatsapi_competition_id  # has a stable id
            assert e.canonical_competition_id     # linked canonically
        if e.identity_status == IdentityStatus.AMBIGUOUS:
            assert e.thestatsapi_competition_id is None  # fail closed, no auto-join


def _entry(status, cid="comp_9", odds=True):
    return CrosswalkEntry(
        canonical_competition_id="c1" if status == IdentityStatus.VERIFIED else None,
        canonical_name="Test", country="X", footystats_id="1", footystats_name="Test",
        thestatsapi_competition_id=(cid if status == IdentityStatus.VERIFIED else None),
        thestatsapi_name="Test", identity_status=status, verification_method="test",
        odds_available=odds, xg_available=None, has_team_stats=None, has_player_stats=None)


def test_name_match_alone_cannot_verify():
    # A row whose only evidence is a matching name must not be VERIFIED. We model
    # this as AMBIGUOUS identity => never CAPTURE_READY / never activated.
    amb = _entry(IdentityStatus.AMBIGUOUS)
    row = classify(amb, None)
    assert row.capture_classification == CaptureClass.IDENTITY_UNRESOLVED
    assert active_competition_ids([row]) == ()


def test_api_unsupported_never_activates():
    row = classify(_entry(IdentityStatus.API_UNSUPPORTED), None)
    assert row.capture_classification == CaptureClass.API_UNSUPPORTED
    assert active_competition_ids([row]) == ()


# --------------------------------------------------------------------------
# Coverage / classification
# --------------------------------------------------------------------------


def _cov(**kw):
    base = dict(canonical_name="Test", country="X", thestatsapi_competition_id="comp_9")
    base.update(kw)
    return CompetitionCoverage(**base)


def test_unknown_not_false_in_market_eligibility():
    # No coverage + registry odds UNKNOWN => market eligibility UNKNOWN, not UNSUPPORTED.
    e = _entry(IdentityStatus.VERIFIED, odds=None)
    row = classify(e, None)
    assert all(v == MarketEligibility.UNKNOWN.value for v in row.market_eligibility.values())


def test_endpoint_supported_vs_currently_available():
    # odds endpoint 404 on probe (odds_endpoint_verified False) but registry says
    # odds_available: classification stays PARTIAL, NOT market-insufficient.
    e = _entry(IdentityStatus.VERIFIED, odds=True)
    row = classify(e, _cov(odds_endpoint_verified=False, scheduled_fixtures_in_scan=5))
    assert row.capture_classification == CaptureClass.CAPTURE_PARTIAL


def test_capture_ready_with_market_and_pinnacle_is_priority_1():
    e = _entry(IdentityStatus.VERIFIED, odds=True)
    cov = _cov(odds_endpoint_verified=True, markets_present=("total_goals",),
               bookmakers_present=("pinnacle", "bet365"), pinnacle_available=True)
    row = classify(e, cov)
    assert row.capture_classification == CaptureClass.CAPTURE_READY
    assert row.capture_priority == 1


def test_market_specific_eligibility_retained():
    e = _entry(IdentityStatus.VERIFIED, odds=True)
    cov = _cov(odds_endpoint_verified=True, markets_present=("total_goals",),
               bookmakers_present=("bet365",))
    row = classify(e, cov)
    assert row.market_eligibility["total_goals"] == MarketEligibility.READY.value
    # corners not seen but registry odds true => PARTIAL, not UNSUPPORTED
    assert row.market_eligibility["match_corners"] == MarketEligibility.PARTIAL.value


# --------------------------------------------------------------------------
# Activation
# --------------------------------------------------------------------------


def test_activation_ready_only_vs_partial():
    e_ready = _entry(IdentityStatus.VERIFIED, odds=True)
    ready = classify(e_ready, _cov(odds_endpoint_verified=True, markets_present=("total_goals",),
                                   bookmakers_present=("bet365",)))
    partial = classify(_entry(IdentityStatus.VERIFIED, odds=True),
                       _cov(odds_endpoint_verified=False))
    rows = [ready, partial]
    assert len(active_universe(rows, include_partial=False)) == 1
    assert len(active_universe(rows, include_partial=True)) == 2


def test_activation_skips_when_no_eligible_markets():
    e = _entry(IdentityStatus.VERIFIED, odds=False)  # odds explicitly unavailable
    row = classify(e, _cov(odds_endpoint_verified=False))
    # market_coverage_insufficient => never active
    assert active_universe([row], include_partial=True) == []


# --------------------------------------------------------------------------
# Quota allocation
# --------------------------------------------------------------------------


def test_allocation_reserves_20pct():
    plan = plan_allocation(monthly_limit=100000, projected_fixtures_per_month=2000)
    assert plan.usable_monthly == 80000  # 20% reserve
    assert plan.requests_per_fixture > 14  # full lifecycle > naive odds-only
    assert plan.within_usable is True


def test_allocation_excludes_naive_division():
    # Naive 100000/odds would overstate capacity; full cost model is higher/fixture.
    plan = plan_allocation(monthly_limit=100000, projected_fixtures_per_month=1)
    cm = FixtureCostModel()
    assert plan.requests_per_fixture == pytest.approx(cm.requests_per_fixture())
    # capacity uses usable (80k) / full per-fixture, not 100k / odds_snapshots
    assert plan.fixtures_per_month_capacity < int(100000 / cm.odds_snapshots)


def test_quota_guard_protects_reserve():
    g = QuotaGuard(monthly_limit=100000)  # reserve floor 20000
    below = parse_rate_limit({"X-Monthly-Quota-Limit": "100000",
                              "X-Monthly-Quota-Remaining": "15000",
                              "X-RateLimit-Limit": "120", "X-RateLimit-Remaining": "50"})
    assert not g.may_request(below)
    ok = parse_rate_limit({"X-Monthly-Quota-Limit": "100000",
                           "X-Monthly-Quota-Remaining": "60000",
                           "X-RateLimit-Limit": "120", "X-RateLimit-Remaining": "50"})
    assert g.may_request(ok)


def test_quota_guard_exhausted_minute_fails_closed():
    g = QuotaGuard(monthly_limit=100000)
    exhausted = parse_rate_limit({"X-RateLimit-Limit": "120", "X-RateLimit-Remaining": "0",
                                  "X-Monthly-Quota-Limit": "100000",
                                  "X-Monthly-Quota-Remaining": "60000"})
    assert not g.may_request(exhausted)


# --------------------------------------------------------------------------
# Coverage funnel / analysis support
# --------------------------------------------------------------------------


def test_competition_funnel_from_real_crosswalk():
    cw = build_crosswalk()
    rows = build_coverage_matrix(cw, [])  # no coverage => classifies on identity
    f = competition_funnel(rows)
    assert f.footystats_supported == 49
    assert f.identity_verified == 46
    assert f.api_unsupported == 1


def test_analysis_support_strata_are_nested(tmp_path):
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    # fixture A: two same-book snapshots + lineup => deepest stratum
    for t in (K - 3600, K - 600):
        store.append(CaptureRecord(
            provider="thestatsapi", provider_entity_id="mt_A", canonical_entity_id="mt_A",
            concept="odds:total_goals:over:2.5:pinnacle", value=1.9,
            observed_at=t, retrieved_at=t, raw_payload_hash=f"h{t}", event_time=K))
    store.append(CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_A", canonical_entity_id="mt_A",
        concept="confirmed_lineup", value={"x": 1},
        observed_at=K - 500, retrieved_at=K - 500, raw_payload_hash="hl", event_time=K))
    # fixture B: single odds snapshot only
    store.append(CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_B", canonical_entity_id="mt_B",
        concept="odds:total_goals:over:2.5:bet365", value=2.0,
        observed_at=K - 700, retrieved_at=K - 700, raw_payload_hash="hb", event_time=K))
    s = analysis_support(store)
    assert s.all_captured_fixtures == 2
    assert s.fixtures_with_odds == 2
    assert s.fixtures_with_same_book_two_snapshots == 1  # only A
    assert s.fixtures_with_confirmed_lineup == 1
    assert s.fixtures_with_lineup_and_same_book_movement == 1  # only A


# --------------------------------------------------------------------------
# Scoped discovery metrics / health
# --------------------------------------------------------------------------


def test_capture_due_reports_waiting_for_vintage(tmp_path, monkeypatch):
    from src.research.prospective.activation import ActiveCompetition
    from src.research.prospective.capture import ProspectiveApiClient
    from src.research.prospective.cli import ProspectiveCollector, _parse_utc

    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    # Fixture ~80h out: discovered + inside horizon, but NOT due (EARLY is 16-32h).
    ko_iso = "2020-01-05T00:00:00Z"
    ko = _parse_utc(ko_iso)
    now = ko - 80 * 3600

    def transport(url, headers, params):
        if url.endswith("/odds") or url.endswith("/lineups"):
            return 404, None
        return 200, {"data": [{"id": "mt_1", "utc_date": ko_iso}]}

    client = ProspectiveApiClient(transport=transport)
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    coll = ProspectiveCollector(client, store, clock=lambda: now)
    active = [ActiveCompetition("L", "X", "comp_1", "sn_1", 1, ("total_goals",))]
    r = coll.capture_due(hours=96, active_competitions=active)
    assert r.fixtures_discovered == 1
    assert r.fixtures_inside_horizon == 1
    assert r.fixtures_due == 0
    assert r.health == "HEALTHY_WAITING_FOR_VINTAGE"


def test_capture_due_empty_universe_is_explicit(tmp_path, monkeypatch):
    from src.research.prospective.capture import ProspectiveApiClient
    from src.research.prospective.cli import ProspectiveCollector

    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")
    coll = ProspectiveCollector(ProspectiveApiClient(transport=lambda u, h, p: (200, {"data": []})),
                                CaptureStore(path=tmp_path / "cap.jsonl"), clock=lambda: K)
    r = coll.capture_due(hours=96, active_competitions=[])
    assert r.competitions_active == 0
    assert r.health == "NO_UPCOMING_FIXTURES"
