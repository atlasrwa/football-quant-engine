"""Tests for TheStatsAPI odds normalization, genuine closing, and vintages."""

from __future__ import annotations

from src.research.forward.odds import OddsSelection, OddsType
from src.research.forward.vintage import (
    ForecastVintage,
    VintageAvailabilityGate,
    compute_cutoff,
)
from src.research.observation import ObservationKey, ObservationStore, ProviderObservation
from src.research.thestatsapi.closing_provider import (
    TheStatsAPIClosingOddsProvider,
    parse_capture_timestamp,
)
from src.research.thestatsapi.odds_normalizer import TheStatsAPIOddsNormalizer, safe_decimal_odds
from src.research.thestatsapi.odds_provider import TheStatsAPIOddsProvider, canonical_fixture_id


def _cma_payload(match_ref="mt_100"):
    return {
        "data": {
            "match_id": match_ref,
            "bookmakers": [
                {
                    "bookmaker": "Bet365",
                    "markets": {
                        "match_odds": {
                            "home": {"opening": "1.615", "last_seen": "1.550"},
                            "draw": {"opening": "3.900", "last_seen": "4.200"},
                            "away": {"opening": "5.000", "last_seen": "5.500"},
                        },
                        "total_goals": {
                            "2.5": {
                                "over": {"opening": "1.725", "last_seen": "1.800"},
                                "under": {"opening": "2.075", "last_seen": "2.000"},
                            },
                        },
                    },
                }
            ],
        }
    }


class TestOddsNormalization:
    def test_string_odds_and_market_line_identity_preserved(self):
        norm = TheStatsAPIOddsNormalizer()
        snaps = norm.normalize_payload(
            _cma_payload(), fixture_id="fx", snapshot_timestamp=1000.0, price_key="opening",
        )
        goals = [s for s in snaps if s.market == "GOALS_TOTAL"]
        over = [s for s in goals if s.selection == OddsSelection.OVER][0]
        assert over.line == 2.5
        assert abs(over.decimal_odds - 1.725) < 1e-9  # string "1.725" -> float

    def test_opening_and_last_seen_distinct(self):
        norm = TheStatsAPIOddsNormalizer()
        opening = norm.normalize_payload(
            _cma_payload(), fixture_id="fx", snapshot_timestamp=1000.0, price_key="opening")
        last = norm.normalize_payload(
            _cma_payload(), fixture_id="fx", snapshot_timestamp=2000.0, price_key="last_seen")
        o_over = [s for s in opening if s.market == "GOALS_TOTAL" and s.selection == OddsSelection.OVER][0]
        l_over = [s for s in last if s.market == "GOALS_TOTAL" and s.selection == OddsSelection.OVER][0]
        assert o_over.decimal_odds == 1.725 and l_over.decimal_odds == 1.800
        assert o_over.bookmaker.endswith(":opening")
        assert l_over.bookmaker.endswith(":last_seen")

    def test_invalid_odds_skipped(self):
        assert safe_decimal_odds("0") is None
        assert safe_decimal_odds("0.5") is None  # < 1.0
        assert safe_decimal_odds(None) is None
        assert safe_decimal_odds("abc") is None
        assert safe_decimal_odds("1.5") == 1.5


class TestOddsProviderTemporal:
    def test_pre_match_only_and_no_fabricated_closing(self):
        prov = TheStatsAPIOddsProvider()
        prov.ingest_cma_odds(_cma_payload(), opening_timestamp=1000.0, last_seen_timestamp=2000.0)
        fid = canonical_fixture_id("mt_100")
        assert all(s.odds_type == OddsType.PRE_MATCH for s in prov.get_odds_snapshot(fid))
        # cma_odds carries no capture time -> NOT closing.
        assert prov.get_closing_odds(fid) == []

    def test_odds_after_cutoff_excluded_for_prediction(self):
        prov = TheStatsAPIOddsProvider()
        prov.ingest_cma_odds(_cma_payload(), opening_timestamp=1000.0)
        fid = canonical_fixture_id("mt_100")
        snaps = prov.get_odds_snapshot(fid)
        assert snaps and all(s.is_valid_for_prediction(1500.0) for s in snaps)
        assert not any(s.is_valid_for_prediction(500.0) for s in snaps)


class TestGenuineClosing:
    def test_parse_capture_timestamp(self):
        fn = "research_odds_mt_1_bet365_20260906T131350108942Z-1788700430108955696.json"
        ts = parse_capture_timestamp(fn)
        assert ts is not None and ts > 0

    def test_last_before_kickoff_is_genuine_and_post_kickoff_excluded(self):
        prov = TheStatsAPIClosingOddsProvider()
        # Two captures: one before kickoff (T-30m), one after (T+10m).
        before_fn = "research_odds_mt_1_bet365_20260906T113000000000Z-1.json"
        after_fn = "research_odds_mt_1_bet365_20260906T121000000000Z-2.json"
        payload = _cma_payload("mt_1")
        prov.ingest_capture(before_fn, payload)
        prov.ingest_capture(after_fn, payload)
        # kickoff at 12:00:00 UTC 2026-09-06
        kickoff = parse_capture_timestamp("x_20260906T120000000000Z-0.json")
        prov.set_kickoff("mt_1", kickoff)
        fid = canonical_fixture_id("mt_1")
        obs = prov.get_closing_odds(fid, market="MATCH_RESULT_1X2")
        assert obs, "should have a genuine pre-kickoff close"
        chosen = obs[0]
        assert chosen.is_genuine
        assert chosen.closing_timestamp < kickoff  # the before-capture, not after

    def test_no_prekickoff_capture_returns_empty(self):
        prov = TheStatsAPIClosingOddsProvider()
        after_fn = "research_odds_mt_1_bet365_20260906T121000000000Z-2.json"
        prov.ingest_capture(after_fn, _cma_payload("mt_1"))
        prov.set_kickoff("mt_1", parse_capture_timestamp("x_20260906T120000000000Z-0.json"))
        assert prov.get_closing_odds(canonical_fixture_id("mt_1")) == []


class TestForecastVintage:
    def test_cutoffs(self):
        early = compute_cutoff("fx", 1_000_000, ForecastVintage.EARLY)
        late = compute_cutoff("fx", 1_000_000, ForecastVintage.LATE)
        assert early.cutoff_timestamp == 1_000_000 - 86400
        assert late.cutoff_timestamp == 1_000_000 - 3600
        assert not early.consults_lineups and late.consults_lineups

    def test_early_never_consults_lineups_even_if_observed(self):
        store = ObservationStore()
        store.append(ProviderObservation(
            key=ObservationKey("fx", "confirmed_xi"), source="thestatsapi",
            provider_entity_id="tm_1", value="XI", observed_at=1_000_000 - 90 * 60))
        gate = VintageAvailabilityGate(store)
        early = compute_cutoff("fx", 1_000_000, ForecastVintage.EARLY)
        assert gate.available(early, "confirmed_xi") is None

    def test_late_includes_lineup_only_if_observed_in_time(self):
        store = ObservationStore()
        # observed at T-90m (before LATE cutoff T-60m)
        store.append(ProviderObservation(
            key=ObservationKey("fx", "confirmed_xi"), source="thestatsapi",
            provider_entity_id="tm_1", value="XI", observed_at=1_000_000 - 90 * 60))
        gate = VintageAvailabilityGate(store)
        late = compute_cutoff("fx", 1_000_000, ForecastVintage.LATE)
        assert gate.available(late, "confirmed_xi").value == "XI"

    def test_late_excludes_lineup_observed_after_cutoff(self):
        store = ObservationStore()
        # observed at T-30m (AFTER LATE cutoff T-60m) -> not available, no fabrication
        store.append(ProviderObservation(
            key=ObservationKey("fx", "confirmed_xi"), source="thestatsapi",
            provider_entity_id="tm_1", value="XI", observed_at=1_000_000 - 30 * 60))
        gate = VintageAvailabilityGate(store)
        late = compute_cutoff("fx", 1_000_000, ForecastVintage.LATE)
        assert gate.available(late, "confirmed_xi") is None
