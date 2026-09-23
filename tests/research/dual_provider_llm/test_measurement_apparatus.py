"""Direct-hypothesis measurement apparatus tests. SYNTHETIC league only: no real match data,
no outcome, no LLM. Nothing here measures a real historical effect."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from src.research.dual_provider_llm import packet as P
from src.research.dual_provider_llm.measurement import compiler as C
from src.research.dual_provider_llm.measurement import executor as E
from src.research.dual_provider_llm.measurement import measures as M
from src.research.dual_provider_llm.measurement import query_spec as Q
from src.research.dual_provider_llm.measurement import support as S
from src.research.dual_provider_llm.measurement.pit_history import (PITHistory, PITViolation,
                                                                     TeamMatch,
                                                                     UnsupportedMetric,
                                                                     check_metric)
from src.research.dual_provider_llm.measurement.similarity import nearest, profile, rms_distance

CONCEPTS = sorted(c for c, _, _, _ in P.CONCEPTS)
DAY = 86400
T0 = 1_700_000_000
CUT = T0 + 400 * DAY
ROOT = Path(__file__).resolve().parents[3]


def _vals(rng, null=()):
    return tuple((c, None if c in null else float(rng.integers(0, 30))) for c in CONCEPTS)


def _league(n_rounds=24, n_teams=20, comp="c1", seed=1, t0=T0):
    rng = np.random.default_rng(seed)
    rows, teams = [], [f"tm_{i:02d}" for i in range(n_teams)]
    for rd in range(n_rounds):
        order = list(rng.permutation(teams))
        for j in range(0, n_teams, 2):
            h, a = order[j], order[j + 1]
            mid, k = f"mt_{comp}_{rd:03d}_{j:02d}", t0 + rd * 7 * DAY + j * 60
            vh, va = _vals(rng), _vals(rng)
            rows.append(TeamMatch(mid, k, comp, "s1", h, a, "HOME", vh, va))
            rows.append(TeamMatch(mid, k, comp, "s1", a, h, "AWAY", va, vh))
    return rows


def _hist(rows=None, cut=CUT):
    return PITHistory(rows if rows is not None else _league(), cut)


def test_01_only_strictly_prior_matches_contribute():
    h = _hist()
    t = T0 + 100 * DAY
    assert all(r.kickoff_unix < t for r in h.team_rows("tm_00", t))
    at = [r for r in h.rows if r.kickoff_unix == T0][0]
    assert at.match_id not in {r.match_id for r in h.team_rows(at.team_id, T0)}
    with pytest.raises(PITViolation):
        h.team_rows("tm_00", CUT + 1)


def _add_future(rows, team, t, venue="AWAY", n=5):
    rng = np.random.default_rng(99)
    extra = [TeamMatch(f"mt_fut_{i}", t + (i + 1) * DAY, "c1", "s1", team, "tm_19", venue,
                       _vals(rng), _vals(rng)) for i in range(n)]
    return rows + extra


def test_02_future_opponent_history_does_not_change_past_similarity():
    rows = _league()
    t = T0 + 150 * DAY
    dims = (("possession", "AGAINST"), ("corners", "AGAINST"))
    p1, _ = profile(_hist(rows), "tm_03", t, "AWAY", dims)
    p2, _ = profile(_hist(_add_future(rows, "tm_03", t)), "tm_03", t, "AWAY", dims)
    assert p1 is not None and p1 == p2


def test_03_future_subject_history_does_not_change_past_state():
    from src.research.dual_provider_llm.measurement.similarity import state_vector
    rows = _league()
    t = T0 + 150 * DAY
    row = [r for r in rows if r.team_id == "tm_05" and r.kickoff_unix < t][-1]
    dims = (("possession", "FOR"), ("touches_in_box", "FOR"))
    s1 = state_vector(_hist(rows), row, dims, t, True)
    s2 = state_vector(_hist(_add_future(rows, "tm_05", t, "HOME")), row, dims, t, True)
    assert s1 == s2 and s1 is not None


def test_04_target_match_stats_are_never_read():
    rows = _league()
    rng = np.random.default_rng(7)
    target = TeamMatch("mt_target", CUT, "c1", "s1", "tm_00", "tm_01", "HOME",
                       _vals(rng), _vals(rng))
    h = PITHistory(rows + [target], CUT, excluded_match_ids=["mt_target"])
    assert "mt_target" not in {r.match_id for r in h.rows}
    assert h.n_dropped_at_or_after_cutoff == 1
    src = (ROOT / "src/research/dual_provider_llm/measurement/executor.py").read_text()
    assert "ok.pop(tid" in src and "i != tid" in src and "excluded_match_ids=[tid]" in src


def test_05_similarity_is_deterministic_with_ties():
    items = [("b", 0.5, 2), ("a", 0.5, 2), ("c", 0.5, 1), ("d", 0.1, 9)]
    assert nearest(items, 2) == nearest(list(reversed(items)), 2) == (["d", "c"], ["a", "b"])


def test_06_scaling_is_fit_on_prior_data_only():
    rows = _league()
    t = T0 + 120 * DAY
    r1 = _hist(rows).reference("corners", "c1", t)
    bad = rows + [TeamMatch("mt_x", t + DAY, "c1", "s1", "tm_00", "tm_01", "HOME",
                            tuple((c, 1e6) for c in CONCEPTS), tuple((c, 1e6) for c in CONCEPTS))]
    assert r1 == _hist(bad).reference("corners", "c1", t) and r1 is not None
    assert _hist(rows).reference("corners", "c1", T0 + DAY) is None   # < MIN_REFERENCE_OBS


def _doc():
    return C.compile_all(ROOT / "research/dual_provider_llm/out/direct_pilot/"
                                "CHATGPT_HYPOTHESES_V1.json",
                         ROOT / "research/dual_provider_llm/out/direct_pilot/"
                                "PILOT_FIXTURE_PACKET_V1.json")


def test_07_no_llm_numeric_threshold_every_number_is_a_named_constant():
    doc = _doc()
    for s in doc["specs"]:
        assert C._walk_numbers(s) == []
        assert s["numeric_tokens_used_as_parameters"] == [] and s["numeric_llm_input_used"] is False
    assert all(a["NUMERIC_LLM_INPUT_USED"] is False for a in doc["audits"])


def test_08_null_is_not_zero_imputed():
    rows = _league()
    t = T0 + 150 * DAY
    rng = np.random.default_rng(3)
    nulls = [TeamMatch(f"mt_n{i}", t - (i + 1) * 3600, "c1", "s1", "tm_new", "tm_00", "AWAY",
                       _vals(rng), _vals(rng, null=("corners",))) for i in range(10)]
    h = _hist(rows + nulls)
    p, meta = profile(h, "tm_new", t, "AWAY", (("corners", "AGAINST"),))
    assert p is None and meta["n_corners_AGAINST"] == 0      # abstains, never zero
    assert nulls[0].get("corners", "AGAINST") is None


def test_09_competition_handling_is_deterministic():
    rows = _league(comp="c1") + _league(comp="c2", seed=5)
    h = _hist(rows)
    t = T0 + 200 * DAY
    r = [x for x in h.rows if x.competition_id == "c2" and x.kickoff_unix < t][-1]
    ref2 = h.reference("shots", "c2", t)
    assert h.z(r, "shots", "FOR", t) == (r.get("shots", "FOR") - ref2[0]) / ref2[1]
    assert h.reference("shots", "c1", t) != ref2
    assert Q.COMMON_COMPETITION["policy"] == "B_COMPETITION_STANDARDIZED"


def test_10_venue_constraints_are_respected():
    h = _hist()
    assert all(r.venue == "HOME" for r in h.team_rows("tm_00", CUT, venue="HOME"))
    s = {x["mechanism_id"]: x for x in Q.specs()}
    assert s["DP1_BOX_PRESSURE_MATCHUP"]["venue_condition"]["subject_venue"] == "HOME"
    assert s["DP3_ALBACETE_DIRECT_PROGRESSION"]["venue_condition"]["subject_venue"] == "AWAY"
    assert s["DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION"]["venue_condition"][
        "subject_venue"] == "AWAY"


def test_11_dp2_remains_multivariate():
    s = {x["mechanism_id"]: x for x in Q.specs()}["DP2_WIDE_CENTRAL_INTERACTION"]
    assert s["design"] == "INTERACTION_REGRESSION" and s["multivariate"] is True
    assert "x1*x2" in s["primary_measurement"]["parameters"]
    rng = np.random.default_rng(0)
    x1, x2 = rng.normal(size=200), rng.normal(size=200)
    r = M.interaction_coef(x1, x2, x1 * x2 + 0.01 * rng.normal(size=200))
    assert abs(r["statistic"] - 1.0) < 0.05 and r["null"] == "freedman_lane_residual_permutation"


def test_12_dp6_never_uses_blocked_shots():
    for s in Q.specs():
        assert "blocked_shots" not in C.spec_metrics(s)
    with pytest.raises(UnsupportedMetric):
        check_metric("blocked_shots")


def test_13_unsupported_metrics_fail_closed(monkeypatch):
    with pytest.raises(UnsupportedMetric):
        check_metric("npxg")
    orig = Q.specs

    def bad():
        out = orig()
        out[0] = copy.deepcopy(out[0])
        out[0]["input_metrics"] = out[0]["input_metrics"] + ["npxg"]
        return out
    monkeypatch.setattr(Q, "specs", bad)
    with pytest.raises(C.CompileError):
        _doc()


def test_14_support_failure_returns_explicit_status():
    assert S.group_support(5)[0] == S.Status.INSUFFICIENT_SUPPORT
    assert S.regression_support(39, 4)[0] == S.Status.INSUFFICIENT_SUPPORT
    small = _hist(_league(n_rounds=12))
    spec = {x["mechanism_id"]: x for x in Q.specs()}["DP1_BOX_PRESSURE_MATCHUP"]
    r = E.run_neighbor_group(spec, small, "tm_00", "tm_01", CUT, "HOME", "AWAY")
    assert r["status"] in (S.Status.INSUFFICIENT_SUPPORT, S.Status.NO_QUERY_PROFILE)


def test_15_repeated_execution_is_byte_identical():
    assert C.dumps(_doc()) == C.dumps(_doc())
    cut = T0 + 1500 * DAY                       # long synthetic league: every design runs
    ctx = {"home_team_id": "tm_00", "away_team_id": "tm_01", "cutoff_unix": cut}
    rows = _league(n_rounds=200)
    a = json.dumps(E.run_all(_hist(rows, cut), ctx, Q.specs()), sort_keys=True, default=str)
    b = json.dumps(E.run_all(_hist(rows, cut), ctx, Q.specs()), sort_keys=True, default=str)
    assert a == b
    out = json.loads(a)
    assert set(out["results"]) == set(C.EXPECTED_IDS)
    assert all(r["status"] == S.Status.OK for r in out["results"].values())
    assert out["BH_FAMILY_FROZEN"] == [m for m in C.EXPECTED_IDS
                                if m != "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION"]
    assert out["results"]["DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION"]["primary"][
        "inferential"] is False


def test_specs_contain_no_wall_clock_and_six_compile():
    doc = _doc()
    body = C.dumps(doc)
    assert "created_at" not in body and "time.time" not in body
    assert [a["MECHANISM_ID"] for a in doc["audits"]] == list(C.EXPECTED_IDS)
    assert all(a["COMPILABLE"] for a in doc["audits"])
    assert "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION" not in doc["bh_family"]


def test_dp4_excludes_reference_matches_from_its_pool():
    cut = T0 + 1500 * DAY
    h = _hist(_league(n_rounds=200), cut)
    spec = {x["mechanism_id"]: x for x in Q.specs()}["DP4_GIRONA_CURRENT_TERRITORIAL_REGIME"]
    r = E.run_state_residual(spec, h, "tm_00", cut)
    assert r["status"] == S.Status.OK
    ref = {x.match_id for x in h.team_rows("tm_00", cut, n=10)}
    used = set(r["groups"]["near_recent_state"]) | set(r["groups"]["near_r10_state"])
    assert used and not used & ref and r["n_reference_matches_excluded"] > 0
    assert not set(r["groups"]["near_recent_state"]) & set(r["groups"]["near_r10_state"])


def test_runner_gate_refuses_unauthorized_head():
    with pytest.raises(E.GateError):
        E.gate(ROOT, "0" * 40)
