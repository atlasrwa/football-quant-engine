"""Point-in-time enforcement verification for the look-ahead gate check (task 8.6).

Verifies that the look-ahead gate check recomputes a sampled feature from
history truncated STRICTLY BEFORE match M and asserts equality with the pipeline
value across profiling — i.e. adding later matches never changes an earlier
match's profile. This is Property 2's mechanism enforced at the gate level.

Validates: Requirements 6.5, 11.1, 11.3.
"""

from __future__ import annotations

import pytest

from src.research.asymmetric.gates import FeatureVerificationGate
from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch


def _mk(mid: int, d: int, home: str, away: str, hg: int, ag: int, **kw) -> ResearchMatch:
    return ResearchMatch(
        match_id=mid,
        date_unix=d,
        league_id=kw.get("lid", 1),
        season="s",
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        corners_home=kw.get("ch", 5),
        corners_away=kw.get("ca", 4),
        shots_on_target_home=kw.get("soth", 4),
        shots_on_target_away=kw.get("sota", 3),
        fouls_home=kw.get("fh", 10),
        fouls_away=kw.get("fa", 11),
        yellow_cards_home=kw.get("yh", 1),
        yellow_cards_away=kw.get("ya", 2),
        home_xg=kw.get("hxg", 1.2),
        away_xg=kw.get("axg", 0.9),
    )


def _history() -> list[ResearchMatch]:
    """A chronological history where team X appears home and away, mixed leagues."""
    return [
        _mk(1, 100, "X", "B", 2, 1, ch=5, ca=3, hxg=1.5, axg=0.7),
        _mk(2, 200, "C", "X", 0, 0, ch=4, ca=6, hxg=0.8, axg=1.1),
        _mk(3, 300, "X", "D", 1, 1, ch=7, ca=2, lid=2, hxg=1.3, axg=1.0),
        _mk(4, 400, "E", "X", 3, 2, ch=2, ca=8, hxg=2.1, axg=1.4),
        _mk(5, 500, "X", "F", 0, 2, ch=3, ca=5, lid=2, hxg=0.6, axg=1.7),
        _mk(6, 600, "G", "X", 2, 2, ch=6, ca=4, hxg=1.1, axg=1.2),
        _mk(7, 700, "X", "H", 1, 0, ch=8, ca=1, hxg=1.9, axg=0.5),
        _mk(8, 800, "I", "X", 2, 1, ch=5, ca=5, hxg=1.0, axg=1.0),
    ]


def test_look_ahead_check_passes_on_point_in_time_pipeline():
    """The look-ahead check reports no mismatch on a correct PIT pipeline."""
    matches = _history()
    gate = FeatureVerificationGate(window=10)
    check = gate._check_look_ahead(matches, TeamProfiler(window=10), leagues={1: "L1", 2: "L2"})
    assert check.name == "look_ahead"
    assert check.metric == 0.0, check.detail
    assert check.passed is True
    assert "mismatches=0" in check.detail


def test_truncated_recompute_equals_pipeline_value():
    """Directly assert: profile for M from full history == from history <= M.

    This is the exact mechanism the look-ahead check uses: recompute a sampled
    feature from history truncated strictly before-or-at M and require equality
    with the value the full pipeline produced.
    """
    matches = _history()
    profiler = TeamProfiler(window=10)
    full = profiler.compute_profiles_map(matches)

    ordered = sorted(matches, key=lambda m: m.date_unix)
    for i, target in enumerate(ordered):
        truncated = ordered[: i + 1]  # strictly-before M plus M itself
        trunc = profiler.compute_profiles_map(truncated)
        for key in (target.match_id, -target.match_id):
            fv = full[key].attacking.vector() + full[key].defensive.vector()
            tv = trunc[key].attacking.vector() + trunc[key].defensive.vector()
            assert fv == tv, f"look-ahead leak at match {target.match_id} key {key}"


def test_appending_future_matches_never_changes_earlier_profile():
    """Adding far-future matches must not alter an earlier match's profile."""
    profiler = TeamProfiler(window=10)
    base = _history()[:4]
    key = base[3].match_id
    before = profiler.compute_profiles_map(base)[key]

    future = base + [
        _mk(50, 5_000, "X", "Z", 4, 0, ch=9, ca=9, hxg=3.0, axg=0.2),
        _mk(51, 6_000, "Z", "X", 1, 3, ch=1, ca=1, hxg=0.3, axg=2.5),
    ]
    after = profiler.compute_profiles_map(future)[key]
    assert before.attacking.vector() == after.attacking.vector()
    assert before.defensive.vector() == after.defensive.vector()
    assert before.n_history == after.n_history


def test_look_ahead_check_detects_injected_leak(monkeypatch):
    """If the profiler leaked future info, the look-ahead check would fail.

    We simulate a leak by wrapping ``compute_profiles_map`` so that the FULL-map
    call (more matches) returns a perturbed vector for a sampled key relative to
    the truncated call, and assert the check reports a mismatch. This proves the
    check actually compares full-vs-truncated rather than trivially passing.
    """
    matches = _history()
    gate = FeatureVerificationGate(window=10)
    profiler = TeamProfiler(window=10)

    real_compute = profiler.compute_profiles_map
    call_state = {"n": 0}

    def leaky_compute(ms, leagues=None):
        result = real_compute(ms, leagues=leagues)
        call_state["n"] += 1
        # On the first (full-corpus) call, corrupt EVERY profile so that whatever
        # key the check samples, full != truncated. This proves the check truly
        # compares full-vs-truncated rather than trivially passing.
        if call_state["n"] == 1 and result:
            from src.research.asymmetric.models import ProfileDimension

            for key in list(result):
                tmp = result[key]
                w = tmp.attacking.width
                bad_dim = ProfileDimension(
                    name="width",
                    value=w.value + 999.0,
                    source_fields=w.source_fields,
                    n_matches_used=w.n_matches_used,
                    missing_fields=w.missing_fields,
                )
                bad_att = tmp.attacking.model_copy(update={"width": bad_dim})
                result[key] = tmp.model_copy(update={"attacking": bad_att})
        return result

    monkeypatch.setattr(profiler, "compute_profiles_map", leaky_compute)
    check = gate._check_look_ahead(matches, profiler, leagues=None)
    assert check.passed is False
    assert check.metric is not None and check.metric >= 1.0
    assert "LOOK-AHEAD LEAK" in check.detail
