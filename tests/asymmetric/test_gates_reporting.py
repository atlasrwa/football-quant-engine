"""Unit tests for gate reporting and sanity records (task 8.5).

Covers:
  * identity-trace prints/collects between 3 and 5 teams (Req 6.2);
  * known-signal threshold check reports the xG->goals association (Req 6.3);
  * orientation cross-check against source data (Req 6.4);
  * sanity records present and NOT re-diagnosed (Req 7.2-7.4).

These are example-based ``pytest`` tests (not property tests). The real-corpus
checks skip gracefully if the cached corpus is unavailable so the suite stays
runnable in any environment.
"""

from __future__ import annotations

import pytest

from src.research.asymmetric.gates import (
    CARDS_CHAMPIONSHIP_STRUCTURAL_RESULT,
    CORNERS_STRUCTURAL_RESULT,
    FEATURE_VERIFICATION_GATE,
    IDENTITY_TRACE_MAX_TEAMS,
    IDENTITY_TRACE_MIN_TEAMS,
    KNOWN_SIGNAL_THRESHOLD,
    SANITY_GATE,
    FeatureVerificationGate,
    SanityGate,
    SanityRecord,
)
from src.research.asymmetric.profiles import TeamProfiler


# --------------------------------------------------------------------------- #
# Real-corpus helper
# --------------------------------------------------------------------------- #
def _load_rich_sample(n: int = 500):
    try:
        from src.research.asymmetric.corpus import RichCorpusLoader

        loaded = RichCorpusLoader().load()
    except Exception:
        return None, None
    if not loaded:
        return None, None
    matches = [lm.match for lm in loaded][:n]
    leagues = {lm.match.league_id: lm.league for lm in loaded}
    return matches, leagues


# --------------------------------------------------------------------------- #
# FeatureVerificationGate reporting (Req 6.2, 6.3, 6.4)
# --------------------------------------------------------------------------- #
def test_identity_trace_collects_three_to_five_teams():
    """The identity trace samples between 3 and 5 teams and reports them (6.2)."""
    matches, leagues = _load_rich_sample()
    if not matches:
        pytest.skip("rich corpus cache not available")
    gate = FeatureVerificationGate()
    check = gate._check_identity_trace(matches, leagues)
    assert check.name == "team_identity_trace"
    assert check.metric is not None
    n_teams = int(check.metric)
    assert IDENTITY_TRACE_MIN_TEAMS <= n_teams <= IDENTITY_TRACE_MAX_TEAMS
    # The trace text must actually enumerate the teams and roles.
    assert "traced" in check.detail
    assert "home_role" in check.detail and "away_role" in check.detail
    # No traced match may belong to another team.
    assert "wrong-team matches=0" in check.detail
    assert check.passed is True


def test_known_signal_reports_threshold_and_association():
    """Known-signal reports xG->goals association vs the ~0.10 threshold (6.3)."""
    matches, _ = _load_rich_sample()
    if not matches:
        pytest.skip("rich corpus cache not available")
    gate = FeatureVerificationGate()
    check = gate._check_known_signal(matches)
    assert check.name == "known_signal"
    assert check.metric is not None
    # On real data the xG->goals association must clear ~0.10 (Req 6.3).
    assert check.metric >= KNOWN_SIGNAL_THRESHOLD, check.detail
    assert check.passed is True
    assert "threshold" in check.detail
    assert "goals->goals" in check.detail


def test_orientation_cross_check_against_source():
    """Orientation confirms home features align with the home outcome (6.4)."""
    matches, _ = _load_rich_sample()
    if not matches:
        pytest.skip("rich corpus cache not available")
    gate = FeatureVerificationGate()
    check = gate._check_orientation(matches)
    assert check.name == "orientation"
    assert check.metric is not None
    # metric = corr(home_feat, home_col) - corr(home_feat, away_col) >= 0.
    assert check.passed is True, check.detail
    assert "home_goals" in check.detail and "away_goals" in check.detail
    assert "TRANSPOSITION" not in check.detail or "no transposition" in check.detail


def test_full_gate_reports_every_check_on_real_corpus():
    """The aggregate GateResult reports all five checks (Req 6.7)."""
    matches, leagues = _load_rich_sample()
    if not matches:
        pytest.skip("rich corpus cache not available")
    result = FeatureVerificationGate().run(matches, TeamProfiler(), leagues=leagues)
    assert result.gate == FEATURE_VERIFICATION_GATE
    names = {c.name for c in result.checks}
    assert names == {
        "team_identity_trace",
        "known_signal",
        "orientation",
        "look_ahead",
        "shuffle_null",
    }
    # On the real corpus the gate should pass end-to-end.
    assert result.passed is True
    assert result.stopped_modelling is False


# --------------------------------------------------------------------------- #
# SanityGate records (Req 7.1-7.4)
# --------------------------------------------------------------------------- #
LEAGUES = ["Championship", "Ligue 2", "La Liga 2"]
TARGETS = ["corners", "cards", "goals", "sot"]


def test_sanity_records_corners_persistence_every_league():
    """corners near-zero persistence recorded for every league (Req 7.2)."""
    records = SanityGate().run(LEAGUES, TARGETS)
    corners = [r for r in records if r.target == "corners"]
    assert {r.league for r in corners} == set(LEAGUES)
    for r in corners:
        assert r.structural_result == CORNERS_STRUCTURAL_RESULT
        assert r.do_not_rediagnose is True


def test_sanity_records_cards_championship_only():
    """cards persistence absence recorded for the Championship only (Req 7.3)."""
    records = SanityGate().run(LEAGUES, TARGETS)
    cards = [r for r in records if r.target == "cards"]
    assert len(cards) == 1
    (rec,) = cards
    assert rec.league == "Championship"
    assert rec.structural_result == CARDS_CHAMPIONSHIP_STRUCTURAL_RESULT
    assert rec.do_not_rediagnose is True


def test_sanity_records_not_rediagnosed():
    """Every recorded structural result is flagged do_not_rediagnose (Req 7.4)."""
    records = SanityGate().run(LEAGUES, TARGETS)
    assert records, "expected at least the corners + cards structural records"
    assert all(r.do_not_rediagnose for r in records)
    # No goals / sot structural results are invented (only known non-signals).
    assert all(r.target in {"corners", "cards"} for r in records)


def test_sanity_gate_result_wrapper_does_not_stop_modelling():
    """The GateResult wrapper records (passing) and never stops modelling (7.4)."""
    result = SanityGate().run_as_gate_result(LEAGUES, TARGETS)
    assert result.gate == SANITY_GATE
    assert result.passed is True
    assert result.stopped_modelling is False
    assert len(result.checks) == len(SanityGate().run(LEAGUES, TARGETS))
    assert all(c.passed for c in result.checks)


def test_sanity_records_are_frozen():
    """SanityRecord is an immutable value object."""
    rec = SanityRecord(league="Championship", target="corners", structural_result="x")
    with pytest.raises(Exception):
        rec.league = "other"  # type: ignore[misc]
