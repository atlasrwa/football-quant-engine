"""Tests for TheStatsAPI normalization: NULL != ZERO, ISO parsing, nested cells."""

from __future__ import annotations

from src.research.thestatsapi.normalizer import (
    TheStatsAPINormalizer,
    parse_iso_to_unix,
    _safe_int,
    _safe_float,
    _safe_possession,
)


def _fixture(**overrides):
    fx = {
        "id": "mt_010243001",
        "competition_id": "comp_3039",
        "season_id": "sn_3057848",
        "status": "finished",
        "utc_date": "2025-01-01T15:00:00.000Z",
        "home_team": {"id": "tm_1", "name": "Home FC"},
        "away_team": {"id": "tm_2", "name": "Away FC"},
        "score": {"home": 2, "away": 1},
    }
    fx.update(overrides)
    return fx


def _stats(**overview):
    return {"data": {"match_id": "mt_010243001", "overview": overview}}


class TestSafeCoercion:
    def test_none_stays_none(self):
        assert _safe_int(None) is None
        assert _safe_float(None) is None

    def test_genuine_zero_preserved(self):
        assert _safe_int(0) == 0
        assert _safe_float(0.0) == 0.0

    def test_non_numeric_is_none(self):
        assert _safe_int("abc") is None
        assert _safe_float("xyz") is None

    def test_bool_rejected(self):
        # bool is a subclass of int; must not be treated as 0/1 count
        assert _safe_int(True) is None
        assert _safe_float(False) is None

    def test_possession_range(self):
        assert _safe_possession(55) == 55
        assert _safe_possession(-1) is None
        assert _safe_possession(150) is None
        assert _safe_possession(0) == 0


class TestIsoParsing:
    def test_z_suffix(self):
        assert parse_iso_to_unix("2025-01-01T00:00:00.000Z") == 1735689600

    def test_missing_returns_none(self):
        assert parse_iso_to_unix(None) is None
        assert parse_iso_to_unix("") is None
        assert parse_iso_to_unix("not-a-date") is None


class TestNormalize:
    def test_minimal_fixture_without_stats(self):
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), stats=None)
        assert m is not None
        assert m.match_id == 10243001
        assert m.home_goals == 2 and m.away_goals == 1 and m.total_goals == 3
        # No stats -> stat fields are None (NULL != ZERO)
        assert m.total_corners is None
        assert m.home_xg is None

    def test_null_red_cards_not_coerced_to_zero(self):
        stats = _stats(
            yellow_cards={"all": {"home": 1, "away": 3}},
            red_cards={"all": None},  # provider reports null for red cards
            corner_kicks={"all": {"home": 9, "away": 5}},
        )
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), stats)
        # Yellow present, red null -> red stays None, not 0
        assert m.yellow_cards_home == 1 and m.yellow_cards_away == 3
        assert m.red_cards_home is None and m.red_cards_away is None
        # total_cards sums only the present components (1+3), not inventing reds
        assert m.total_cards == 4
        assert m.total_corners == 14

    def test_genuine_zero_corner_preserved(self):
        stats = _stats(corner_kicks={"all": {"home": 0, "away": 0}})
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), stats)
        assert m.corners_home == 0 and m.corners_away == 0
        assert m.total_corners == 0  # genuine zero, not missing

    def test_all_card_components_missing_gives_none_total(self):
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), _stats())  # no cards at all
        assert m.total_cards is None  # unknown, not 0

    def test_total_cards_requires_both_yellow_sides(self):
        # Regression: a total must not be fabricated from one side only.
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), _stats(yellow_cards={"all": {"home": 2}}))
        assert m.yellow_cards_home == 2 and m.yellow_cards_away is None
        assert m.total_cards is None  # not 2

    def test_total_cards_both_yellows_present_reds_null(self):
        n = TheStatsAPINormalizer()
        m = n.normalize(_fixture(), _stats(
            yellow_cards={"all": {"home": 2, "away": 1}},
            red_cards={"all": None},
        ))
        # both yellows present; reds null contribute nothing (not invented)
        assert m.total_cards == 3

    def test_non_finished_skipped(self):
        n = TheStatsAPINormalizer()
        assert n.normalize(_fixture(status="scheduled")) is None

    def test_missing_goals_skipped(self):
        n = TheStatsAPINormalizer()
        assert n.normalize(_fixture(score={"home": None, "away": 1})) is None

    def test_missing_team_name_skipped(self):
        n = TheStatsAPINormalizer()
        assert n.normalize(_fixture(home_team={"id": "tm_1"})) is None

    def test_deterministic(self):
        n1, n2 = TheStatsAPINormalizer(), TheStatsAPINormalizer()
        s = _stats(expected_goals={"all": {"home": 2.67, "away": 1.56}})
        m1 = n1.normalize(_fixture(), s)
        m2 = n2.normalize(_fixture(), s)
        assert m1.to_dict() == m2.to_dict()
