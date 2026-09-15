"""V7.1 execution-closure -- synthetic full-execution + adversarial multiplicity (items 3, 9).

These drive the EXACT execution.py stages on a tiny hand-built corpus and synthetic records,
so every terminal state, the multiplicity FDR, Endpoint A, Endpoint B, clustering, the
candidate set, unit-inflation guards, persistence and deterministic resume are all exercised
without touching the real corpus or any fresh fixture.

SYNTHETIC_ONLY / NON_CONFIRMATORY throughout.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import estimator as ES
from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import matching as MATCH
from src.research.matchup.corpus import MatchRecord


# ---- a tiny synthetic corpus ---------------------------------------------------------
def _rec(fid, comp, kickoff, home, away, goals_h, goals_a, yc_h=2, yc_a=2, season="syn_1"):
    base = {"homeGoalCount": goals_h, "awayGoalCount": goals_a,
            "team_a_yellow_cards": yc_h, "team_b_yellow_cards": yc_a,
            "team_a_red_cards": 0, "team_b_red_cards": 0}
    return MatchRecord(fixture_id=fid, competition=comp, competition_id=comp,
                       season_id=season, kickoff_unix=kickoff, home=home, away=away,
                       home_id=home, away_id=away, base=base, rich={}, extra={})


def _synthetic_index(n_teams=12, n_rounds=20, comps=("epl", "laliga")):
    """A deterministic round-robin-ish schedule with a mild home-goal signal, so the engine
    finds SOMETHING to measure. No randomness, no real data."""
    recs, k = [], 1_600_000_000
    teams = [f"t{i}" for i in range(n_teams)]
    fid = 0
    for comp in comps:
        for r in range(n_rounds):
            for i in range(0, n_teams, 2):
                h, a = teams[(i + r) % n_teams], teams[(i + r + 1) % n_teams]
                if h == a:
                    continue
                gh = 1 + ((r + i) % 3)
                ga = (r + i) % 2
                recs.append(_rec(f"s{fid}", comp, k, h, a, gh, ga,
                                 yc_h=1 + (i % 3), yc_a=1 + (r % 3)))
                fid += 1
                k += 3600 * 24
    metrics = [m for m, rr in CAP.METRIC_SEMANTICS.items() if rr.get("block") == "base"]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


@pytest.fixture(scope="module")
def cap():
    import json
    return CAP.CapabilityContract(
        json.load(open("/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))


def _spec(**kw):
    base = {"target_metrics": ["goals"], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_COMPETITION_BASELINE",
            "conditions": [{"dimension": "competition", "value": "SAME"}],
            "window": "ALL_PRIOR", "research_family": "ATTACK_VOLUME",
            "required_capabilities": []}
    base.update(kw)
    return base


def _folds(index, n=4):
    positions = list(range(len(index.recs)))
    size = len(positions) // n
    return [{"fold_index": i, "positions": positions[i * size:(i + 1) * size]}
            for i in range(n)]


# =====================================================================================
# terminal taxonomy: each state is reachable by the real execution path
# =====================================================================================
def test_09_structurally_invalid_family_is_named_before_measurement(cap):
    """A degenerate comparator (cohort == baseline) is refused structurally, never scored."""
    index = _synthetic_index()
    treated = {"invalid": _spec(comparison="SUBJECT_OVERALL_BASELINE", conditions=[])}
    plan = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                uniform_specs={}, marginal_specs={},
                                matching={"assignments": [], "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    # a degenerate spec is not evaluable -> it never enters plan.treated
    assert plan.treated == []
    assert plan.all_treated_rows[0]["evaluable"] is False


def test_09_evaluable_family_scores_and_terminates_in_the_taxonomy(cap):
    index = _synthetic_index()
    treated = {"ok": _spec()}
    plan = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                uniform_specs={}, marginal_specs={},
                                matching={"assignments": [], "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    assert len(plan.treated) == 1
    rec = EX.evaluate_family_evidence(plan.treated[0], plan)
    assert rec["terminal_state"] in EN.TERMINAL_STATES
    # an evaluable family reaches at least the support taxonomy
    assert rec["terminal_state"] in (
        EN.INSUFFICIENT_SUPPORT, EN.CONFOUNDED_UNRESOLVED, EN.OOS_DIRECTION_UNSTABLE,
        EN.OOS_NO_EFFECT, EN.OOS_SURVIVES, EN.CANDIDATE_FEATURE_ELIGIBLE)


def test_09_insufficient_support_when_folds_are_tiny(cap):
    """Too few observations per fold -> INSUFFICIENT_SUPPORT, not a fabricated effect."""
    index = _synthetic_index(n_teams=6, n_rounds=3)
    treated = {"thin": _spec()}
    plan = EX.prepare_execution(index, _folds(index, n=4), treated_specs=treated,
                                uniform_specs={}, marginal_specs={},
                                matching={"assignments": [], "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    rec = EX.evaluate_family_evidence(plan.treated[0], plan)
    assert rec["terminal_state"] == EN.INSUFFICIENT_SUPPORT
    assert rec["score"] is None


# =====================================================================================
# Endpoint A + B end to end
# =====================================================================================
def test_09_full_run_produces_both_endpoints_and_a_hashed_bundle(cap):
    index = _synthetic_index()
    treated = {f"llm_{i}": _spec(research_family=rf)
               for i, rf in enumerate(("ATTACK_VOLUME", "DEFENSIVE_CONCESSION",
                                       "DISCIPLINE", "SET_PIECE_GENERATION"))}
    uniform = {f"uniform_{i}": _spec(research_family="ATTACK_VOLUME") for i in range(3)}
    marginal = {f"null_{i}": _spec(research_family="ATTACK_VOLUME") for i in range(6)}
    # match each treated family to a couple of controls, total weight 1
    assignments = []
    for i, cid in enumerate(sorted(treated)):
        ctrls = [f"null_{(i + j) % 6}" for j in range(3)]
        assignments.append({"canonical_hypothesis_id": cid, "tier": MATCH.TIER_1,
                            "control_ids": ctrls, "weight_per_control": 1.0 / len(ctrls),
                            "n_controls": len(ctrls)})
    matching = {"assignments": assignments, "control_weights": {}}
    plan = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                uniform_specs=uniform, marginal_specs=marginal,
                                matching=matching, capability=cap,
                                classification=EX.CLASS_SYNTHETIC)
    with tempfile.TemporaryDirectory() as d:
        result = EX.run_experiment(plan, d, experiment_id="SYN",
                                   champion_sha256="deadbeef", persist=True)
        # per-family evidence flushed BEFORE aggregate
        ev = os.listdir(os.path.join(d, "per_family_evidence"))
        assert ev, "no per-family evidence persisted"
    assert result["endpoint_a"]["endpoint_id"] == "END_TO_END_RESEARCH_YIELD"
    assert result["endpoint_b"]["endpoint_id"] == "CONDITIONAL_SIGNAL_QUALITY"
    assert result["endpoint_a"]["matched"] is False
    assert result["endpoint_b"]["matched"] is True
    assert result["confirmatory_oos_computed"] is False       # synthetic classification
    assert result["candidate_feature_promotion"] is False
    assert len(result["evidence_bundle_sha256"]) == 64
    assert result["champion_unchanged"] is True


def test_09_resume_is_deterministic_and_does_not_double_count(cap):
    index = _synthetic_index()
    treated = {f"llm_{i}": _spec() for i in range(4)}
    plan_kw = dict(uniform_specs={}, marginal_specs={},
                   matching={"assignments": [], "control_weights": {}},
                   capability=cap, classification=EX.CLASS_SYNTHETIC)
    with tempfile.TemporaryDirectory() as d:
        p1 = EX.prepare_execution(index, _folds(index), treated_specs=treated, **plan_kw)
        r1 = EX.run_experiment(p1, d, experiment_id="SYN", champion_sha256="x", persist=True)
        n1 = len(os.listdir(os.path.join(d, "per_family_evidence")))
        # resume against the SAME dir: evidence is reused, result identical
        p2 = EX.prepare_execution(index, _folds(index), treated_specs=treated, **plan_kw)
        r2 = EX.run_experiment(p2, d, experiment_id="SYN", champion_sha256="x", persist=True)
        n2 = len(os.listdir(os.path.join(d, "per_family_evidence")))
    assert n1 == n2, "resume changed the number of persisted families"
    assert r1["evidence_bundle_sha256"] == r2["evidence_bundle_sha256"]


def test_09_corrupt_persisted_record_is_recomputed_not_trusted(cap):
    index = _synthetic_index()
    treated = {"llm_0": _spec()}
    with tempfile.TemporaryDirectory() as d:
        p = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                 uniform_specs={}, marginal_specs={},
                                 matching={"assignments": [], "control_weights": {}},
                                 capability=cap, classification=EX.CLASS_SYNTHETIC)
        EX.run_experiment(p, d, experiment_id="SYN", champion_sha256="x", persist=True)
        # corrupt the persisted record's content without fixing its hash
        evdir = os.path.join(d, "per_family_evidence")
        fn = os.path.join(evdir, os.listdir(evdir)[0])
        import json
        rec = json.load(open(fn))
        rec["terminal_state"] = "TAMPERED"
        json.dump(rec, open(fn, "w"))
        # load_persisted must reject the tampered record (hash mismatch)
        loaded = EX.load_persisted(d)
        assert loaded == {}, "a tampered/partial record was trusted on resume"


# =====================================================================================
# adversarial multiplicity (item 9)
# =====================================================================================
def test_09_repeated_control_rows_do_not_inflate_the_unit(cap):
    """A control listed many times contributes total weight 1, and the per-pair count equals
    the number of DISTINCT treated families, never the control row count."""
    index = _synthetic_index()
    treated = {"llm_0": _spec()}
    marginal = {f"null_{i}": _spec() for i in range(50)}
    # 50 control ids for ONE treated family: naive counting would call this 50 votes
    assignments = [{"canonical_hypothesis_id": "llm_0", "tier": MATCH.TIER_1,
                    "control_ids": [f"null_{i}" for i in range(50)],
                    "weight_per_control": 1.0 / 50, "n_controls": 50}]
    plan = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                uniform_specs={}, marginal_specs=marginal,
                                matching={"assignments": assignments,
                                          "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    with tempfile.TemporaryDirectory() as d:
        result = EX.run_experiment(plan, d, experiment_id="SYN",
                                   champion_sha256="x", persist=True)
    eb = result["endpoint_b"]
    assert eb["n_matched_pairs"] <= 1, "50 control rows became 50 votes"
    for pair in eb["per_pair"]:
        # the control side is ONE weighted number, though it drew on 50 rows
        assert pair["n_controls"] == 50
        assert "weighted_control_oos_quality_score" in pair


def test_09_unit_inflation_guard_fires_on_duplicate_treated_ids(cap):
    """If the same canonical family id appeared twice in the matched pairs, the frozen
    estimator contract must refuse (repeated rows counted as evidence)."""
    with pytest.raises(ES.EvaluatorContractViolation):
        ES.assert_unit_not_inflated(3, ["a", "a", "b"])


def test_09_multi_metric_family_is_one_unit_not_one_vote_per_metric(cap):
    """A family naming several metrics is still ONE family: score_family aggregates over
    metrics with equal weight, so it cannot cast multiple independent votes."""
    index = _synthetic_index()
    multi = _spec(target_metrics=["goals", "yellow_cards"])
    plan = EX.prepare_execution(index, _folds(index), treated_specs={"m": multi},
                                uniform_specs={}, marginal_specs={},
                                matching={"assignments": [], "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    rec = EX.evaluate_family_evidence(plan.treated[0], plan)
    # one record, one terminal state, one score object -- not one per metric
    assert isinstance(rec["terminal_state"], str)
    assert rec["score"] is None or isinstance(rec["score"], dict)


def test_09_excluded_family_stays_in_endpoint_a_denominator(cap):
    """An unmeasurable/unscored family must NOT vanish from the Endpoint-A canonical
    denominator -- that is the whole point of the end-to-end yield endpoint."""
    index = _synthetic_index()
    # an unknown metric -> UNMEASURABLE, but still a canonical family
    treated = {"good": _spec(), "bad": _spec(target_metrics=["no_such_metric"])}
    plan = EX.prepare_execution(index, _folds(index), treated_specs=treated,
                                uniform_specs={}, marginal_specs={},
                                matching={"assignments": [], "control_weights": {}},
                                capability=cap, classification=EX.CLASS_SYNTHETIC)
    with tempfile.TemporaryDirectory() as d:
        result = EX.run_experiment(plan, d, experiment_id="SYN",
                                   champion_sha256="x", persist=True)
    assert result["endpoint_a"]["llm"]["canonical"] == 2, \
        "an unmeasurable family disappeared from the Endpoint-A denominator"
    assert len(plan.treated) == 1                      # only the measurable one is evaluable
