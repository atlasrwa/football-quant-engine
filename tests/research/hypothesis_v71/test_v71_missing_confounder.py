"""V7.1 execution-closure mission -- defect D15: NULL is not ZERO.

A missing point-in-time confounder must never be coerced to a fabricated 0.0. These tests
guard the CLASS of the defect (any required confounder, any family), not the two instances
that triggered it. Nothing here reads a confirmatory outcome.
"""
from __future__ import annotations

import types

from src.research.hypothesis_v71 import confounders as CF
from src.research.hypothesis_v71 import engine as EN


class _FakeRec:
    def __init__(self, home_id, away_id, competition="epl", season_id="sn_2023"):
        self.home_id = home_id
        self.away_id = away_id
        self.competition = competition
        self.season_id = season_id
        self.fixture_id = f"{home_id}v{away_id}"


class _FakeIndex:
    """A minimal index whose pit_mean returns exactly what a test dictates, so a genuine
    absence (None) and a genuine measured zero (0.0) can be distinguished at the boundary."""

    def __init__(self, pit_values):
        # pit_values maps (team_id, metric) -> (mean_or_None, n)
        self._pit = pit_values

    def pit_mean(self, team_id, metric, perspective, before_rec_i, venue=None):
        return self._pit.get((str(team_id), metric), (None, 0))


def _plan(*confounders):
    return {"research_family": "TEST", "strategy": "regression_adjustment",
            "confounders": list(confounders), "removed": []}


def test_15_only_required_confounders_are_constructed():
    """A plan that does not name opponent_strength/cards must not read them at all."""
    assert EN._required_confounder_names(_plan("venue", "competition")) == frozenset()
    assert EN._required_confounder_names(_plan("opponent_strength")) == \
        frozenset({"opponent_strength"})
    assert EN._required_confounder_names(_plan("cards", "opponent_profile")) == \
        frozenset({"cards", "opponent_profile"})
    # season_regime / team_baseline_quality are always-present structural values, never
    # treated as missing-prone required confounders
    assert EN._required_confounder_names(
        _plan("venue", "competition", "season_regime", "team_baseline_quality")) == frozenset()


def test_15_missing_confounder_is_not_coerced_to_zero():
    """The opponent has NO prior match: its strength is None, never 0.0."""
    rec = _FakeRec("H", "A")
    idx = _FakeIndex({})           # every pit_mean returns (None, 0)
    row = EN._row_confounders(
        ir=types.SimpleNamespace(subject="HOME_TEAM"),
        index=idx, rec_i=10, rec=rec, subject="H", b=0.3, metric="shots",
        required=frozenset({"opponent_strength", "cards"}))
    assert row["opponent_strength"] is None, "missing opponent strength fabricated as a value"
    assert row["cards"] is None, "missing cards fabricated as a value"
    assert not EN._row_is_complete(row, frozenset({"opponent_strength"}))
    assert not EN._row_is_complete(row, frozenset({"cards"}))


def test_15_genuine_zero_confounder_is_preserved():
    """A genuine measured zero (e.g. a team that has literally conceded zero on this metric)
    must survive as 0.0 and count as PRESENT, not be confused with missing."""
    rec = _FakeRec("H", "A")
    idx = _FakeIndex({("A", "shots"): (0.0, 5), ("H", "yellow_cards"): (0.0, 8)})
    row = EN._row_confounders(
        ir=types.SimpleNamespace(subject="HOME_TEAM"),
        index=idx, rec_i=10, rec=rec, subject="H", b=0.3, metric="shots",
        required=frozenset({"opponent_strength", "cards"}))
    assert row["opponent_strength"] == 0.0
    assert row["cards"] == 0.0
    assert EN._row_is_complete(row, frozenset({"opponent_strength", "cards"})), \
        "a genuine zero was wrongly treated as missing"


def test_15_row_missing_required_confounder_is_excluded_not_imputed():
    """A row missing a required confounder is not complete; a row with all present is."""
    complete = {"opponent_strength": 1.2, "cards": 2.0, "venue": 1.0}
    partial = {"opponent_strength": None, "cards": 2.0, "venue": 1.0}
    zero = {"opponent_strength": 0.0, "cards": 0.0, "venue": 0.0}
    req = frozenset({"opponent_strength", "cards"})
    assert EN._row_is_complete(complete, req)
    assert not EN._row_is_complete(partial, req)
    assert EN._row_is_complete(zero, req), "genuine zeros must not be excluded"
    # opponent_profile aliases opponent_strength in the row
    assert not EN._row_is_complete({"opponent_strength": None},
                                   frozenset({"opponent_profile"}))


def test_15_policy_is_frozen_and_outcome_blind():
    pol = CF.MISSING_CONFOUNDER_POLICY
    assert pol["null_is_not_zero"] is True
    assert pol["fabricates_zero_for_missing"] is False
    assert pol["reads_outcomes"] is False
    assert pol["only_required_confounders_constructed"] is True
    # the engine spec advertises the policy so it is part of the frozen, hashed contract
    spec = EN.spec()
    assert spec["missing_confounder_fabricates_zero"] is False
    assert spec["missing_confounder_policy"] == pol["policy"]


def test_15_confounders_version_bumped_for_the_behavioural_change():
    assert CF.CONFOUNDERS_VERSION == "v71_confounders_v2"
    assert "missing_confounder_policy" in CF.version_stamp()
