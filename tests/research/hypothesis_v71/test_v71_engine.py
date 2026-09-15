"""V7.1 sections 6, 11-16, 19: compiler, similarity, recency, confounders, estimator,
controls, evaluability and the point-in-time red team.

Every check is structural or contractual. Nothing reads a confirmatory outcome; the corpus
tests run on the DEVELOPMENT window only.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import confounders as CF
from src.research.hypothesis_v71 import controls as CTRL
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import estimator as ES
from src.research.hypothesis_v71 import evaluability as EVAL
from src.research.hypothesis_v71 import freshsample as FS
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import leakage as LEAK
from src.research.hypothesis_v71 import ontology as ONT
from src.research.hypothesis_v71 import recency as REC
from src.research.hypothesis_v71 import similarity as SIM

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"
PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


@pytest.fixture(scope="module")
def index():
    recs = CI.load_records(include_fresh=False)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


@pytest.fixture(scope="module")
def ctx(index):
    cut = index.kick[int(len(index.kick) * 0.7)]
    ter, cache = {}, {}
    for axis in PROFILE_AXES:
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, s in index.series.items():
            pre = [e for e in s if e[1] < cut]
            if len(pre) < 6:
                continue
            vals = [index.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in pre]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mv = sum(vals) / len(vals)
            cache[(tid, axis)] = mv
            by_comp.setdefault(pre[-1][2], []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            if len(xs) >= 3:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    return EN.Context(index, ter, cache, SIM.SimilarityEngine(index)), cut


def _spec(**kw):
    base = {"target_metrics": ["total_shots"], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_OVERALL_BASELINE", "conditions": [],
            "window": "ALL_PRIOR", "research_family": "ATTACK_VOLUME",
            "required_capabilities": []}
    base.update(kw)
    return base


PROFILE = {"dimension": "opponent_profile", "axis": "goals_against", "value": "HIGH"}


def _first_target(index, cut, n=1):
    import bisect
    i0 = bisect.bisect_left(index.kick, cut)
    return list(range(i0, i0 + n))


# =======================================================================================
# Section 6 -- the compiler honours every declared comparator
# =======================================================================================
@pytest.mark.parametrize("comparator", sorted(ONT.COMPARATOR_BINDINGS))
def test_06_every_comparator_compiles_a_real_contrast(comparator, index, ctx, cap):
    """V7's executor branched on two comparators and fell through to one generic contrast
    for the rest. Every declared comparator must now produce a genuinely distinct query."""
    c, cut = ctx
    conditions = [PROFILE]
    # a comparator that DECLARES a required filter must receive it; the requirement is part
    # of the frozen binding, not a property of this test.
    req = ONT.COMPARATOR_BINDINGS[comparator].get("requires_filter")
    if req:
        conditions = [{"dimension": req["dimension"], "value": req["value"]}]
    spec = _spec(comparison=comparator, conditions=conditions,
                 required_capabilities=["opponent_profile"])
    ir = IRM.build_ir(spec)
    assert ir.status == IRM.OK, (comparator, ir.reasons)
    assert INV.check(ir, capability=cap)["ok"], comparator
    rr = (REC.Recency(REC.HALFLIVES_DAYS[0]) if ir.cohort.weighting == "TIME_DECAY"
          else REC.UniformRecency())
    compiled = 0
    for rec_i in _first_target(index, cut, 60):
        try:
            q = CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                                 axis_cache=c.axis_cache, similarity=c.similarity,
                                 recency=rr, capability=cap)
        except (CO.CompileRefused, SIM.SimilarityRefused):
            continue
        compiled += 1
        assert not q.is_degenerate(), comparator
        assert q.fixtures_read, comparator
    assert compiled > 0, f"{comparator} never compiled on the development window"


def test_06_a_comparator_that_collapses_at_one_fixture_is_refused_there(index, ctx, cap):
    """A comparator can be sound in the IR and still coincide at a particular fixture --
    SUBJECT_COMPETITION_BASELINE does exactly this when the subject's whole prior history sits
    in one competition. That fixture must be REFUSED, not given a zero-valued feature."""
    c, cut = ctx
    ir = IRM.build_ir(_spec(comparison="SUBJECT_COMPETITION_BASELINE",
                            conditions=[{"dimension": "competition", "value": "SAME"}]))
    assert INV.check(ir, capability=cap)["ok"]
    refused = compiled = 0
    for rec_i in _first_target(index, cut, 120):
        try:
            q = CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                                 axis_cache=c.axis_cache, similarity=c.similarity,
                                 recency=REC.UniformRecency(), capability=cap)
        except CO.CompileRefused:
            refused += 1
            continue
        compiled += 1
        assert not q.is_degenerate()
    assert refused > 0, "the single-competition collapse never occurred: test is vacuous"


def test_06_invalid_query_raises_before_the_fold_loop(index, ctx, cap):
    c, cut = ctx
    ir = IRM.build_ir(_spec())          # degenerate: cohort == baseline
    with pytest.raises(INV.InvariantViolation):
        CO.compile_query(ir, index, _first_target(index, cut)[0], metric="shots",
                         terciles=c.terciles, axis_cache=c.axis_cache,
                         similarity=c.similarity, recency=REC.UniformRecency(),
                         capability=cap)


def test_06_profile_filter_reads_the_opponent_not_the_subject():
    """Role inversion must raise, not produce a plausible number."""
    entry = (0, 0, "epl", True, "team_X")
    assert CO.assert_profile_reads_opponent(entry, "team_Y") == "team_X"
    with pytest.raises(INV.InvariantViolation):
        CO.assert_profile_reads_opponent(entry, "team_X")


def test_06_swapping_for_against_changes_the_compiled_values(index, ctx, cap):
    c, cut = ctx
    rec_i = _first_target(index, cut)[0]
    out = {}
    for side in ("FOR", "AGAINST"):
        ir = IRM.build_ir(_spec(side=side, conditions=[PROFILE],
                                required_capabilities=["opponent_profile"]))
        q = CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                             axis_cache=c.axis_cache, similarity=c.similarity,
                             recency=REC.UniformRecency(), capability=cap)
        out[side] = q.cohort_values
    assert out["FOR"] != out["AGAINST"]


def test_06_home_away_inversion_changes_the_compiled_values(index, ctx, cap):
    c, cut = ctx
    rec_i = _first_target(index, cut)[0]
    out = {}
    for subject in ("HOME_TEAM", "AWAY_TEAM"):
        ir = IRM.build_ir(_spec(subject=subject, conditions=[PROFILE],
                                required_capabilities=["opponent_profile"]))
        q = CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                             axis_cache=c.axis_cache, similarity=c.similarity,
                             recency=REC.UniformRecency(), capability=cap)
        out[subject] = q.cohort_fixtures
    assert out["HOME_TEAM"] != out["AWAY_TEAM"]


# =======================================================================================
# Section 19 -- point-in-time red team
# =======================================================================================
def test_19_guard_suite_rejects_every_mutation_and_accepts_a_valid_observation():
    r = LEAK.run_guard_suite(1_700_000_000, "mt_target")
    assert r["n_mutation_classes"] == 18
    assert r["all_mutations_rejected"], r["results"]
    assert r["legitimate_observation_accepted"], "the guards reject everything: vacuous"


def test_19_compiled_query_reads_only_strictly_prior_fixtures(index, ctx, cap):
    """Structural PIT proof: no fixture read may be at or after the target's kickoff."""
    c, cut = ctx
    ir = IRM.build_ir(_spec(conditions=[PROFILE], required_capabilities=["opponent_profile"]))
    checked = 0
    for rec_i in _first_target(index, cut, 40):
        try:
            q = CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                                 axis_cache=c.axis_cache, similarity=c.similarity,
                                 recency=REC.UniformRecency(), capability=cap)
        except CO.CompileRefused:
            continue
        ref = int(index.recs[rec_i].kickoff_unix)
        for fid in q.fixtures_read:
            assert int(index.recs[index.pos_of_fixture[fid]].kickoff_unix) < ref
        assert str(index.recs[rec_i].fixture_id) not in q.fixtures_read
        checked += 1
    assert checked > 0


def test_19_empirical_three_way_probe_with_live_negative_control(index, ctx, cap):
    """Corrupting the target or a future fixture must not move the feature; corrupting a
    genuine PRIOR fixture of the subject MUST. The third is the negative control -- without
    it the first two would pass for a feature that is simply constant."""
    c, cut = ctx
    ir = IRM.build_ir(_spec(conditions=[PROFILE], required_capabilities=["opponent_profile"]))
    target_i = None
    for rec_i in _first_target(index, cut, 200):
        try:
            CO.compile_query(ir, index, rec_i, metric="shots", terciles=c.terciles,
                             axis_cache=c.axis_cache, similarity=c.similarity,
                             recency=REC.UniformRecency(), capability=cap)
        except CO.CompileRefused:
            continue
        target_i = rec_i
        break
    assert target_i is not None

    def feature():
        index._pref.clear()
        q = CO.compile_query(ir, index, target_i, metric="shots", terciles=c.terciles,
                             axis_cache=c.axis_cache, similarity=c.similarity,
                             recency=REC.UniformRecency(), capability=cap)
        return (tuple(q.cohort_values), tuple(q.baseline_values))

    baseline = feature()
    subject = str(index.recs[target_i].home_id)
    prior = [e[0] for e in index.prior_entries(subject, target_i)]
    assert prior, "no prior observation: the probe would be vacuous"

    def corrupt(i):
        old = index.vals["shots"][i]
        index.vals["shots"][i] = None if old is None else (old[0] + 999.0, old[1] + 999.0)
        return old

    old = corrupt(target_i)
    assert feature() == baseline, "target fixture corruption moved the feature"
    index.vals["shots"][target_i] = old

    future_i = min(target_i + 1, len(index.recs) - 1)
    old = corrupt(future_i)
    assert feature() == baseline, "future fixture corruption moved the feature"
    index.vals["shots"][future_i] = old

    old = corrupt(prior[-1])
    moved = feature() != baseline
    index.vals["shots"][prior[-1]] = old
    index._pref.clear()
    assert moved, "NEGATIVE CONTROL DEAD: corrupting a prior fixture did not move the feature"


def test_19_recency_weight_refuses_a_non_prior_observation():
    r = REC.Recency(REC.HALFLIVES_DAYS[0])
    assert r.weight(1000, 2000) > 0
    with pytest.raises(ValueError):
        r.weight(2000, 2000)
    with pytest.raises(ValueError):
        r.weight(3000, 2000)


# =======================================================================================
# Sections 11-14 -- similarity, recency, confounders, estimator
# =======================================================================================
def test_11_similarity_spec_is_the_frozen_v7_spec():
    from src.research.hypothesis_v7 import similarity as V7S
    assert SIM.DIMENSIONS == tuple(V7S.SIMILARITY_DIMENSIONS)
    assert SIM.PROFILE_SHRINKAGE_K == V7S.PROFILE_SHRINKAGE_K
    assert "xg" not in " ".join(SIM.DIMENSIONS)


def test_11_similarity_refuses_rather_than_imputing(index):
    engine = SIM.SimilarityEngine(index)
    rec = index.recs[5]
    with pytest.raises(SIM.SimilarityRefused):
        engine.similar_opponent_ids(index, "no_such_team", rec, 5)


def test_12_decay_family_is_frozen_and_not_searchable():
    assert REC.HALFLIVES_DAYS == (180, 365)
    assert [r.halflife_days for r in REC.family()] == [180.0, 365.0]
    with pytest.raises(ValueError):
        REC.Recency(90)


def test_13_unavailable_and_mediator_confounders_are_declared_not_invented():
    plan = CF.plan_for("SET_PIECE_GENERATION")
    assert "formation" not in plan["confounders"]
    assert CF.AVAILABLE["score_state"] is False
    assert "score_state" in CF.NEVER_ADJUST


def test_13_degenerate_design_columns_are_dropped_with_a_named_reason():
    """The V7 execution surprise: a venue column constant by construction made the design
    singular. It must now be dropped as constant, and SAID so."""
    res = CF.screen_design({"venue": [1.0] * 6, "comp": [0, 1, 0, 1, 0, 1],
                            "copy": [0, 1, 0, 1, 0, 1], "x": [1, 2, 3, 4, 5, 6]})
    reasons = {d["column"]: d["reason"] for d in res["dropped"]}
    assert reasons["venue"] == CF.DROPPED_CONSTANT
    assert reasons["copy"] == CF.DROPPED_COLLINEAR
    assert set(res["kept"]) == {"comp", "x"}
    assert res["identifiable"]


def test_14_impossible_values_abort_the_evaluator():
    for kind, bad in (("correlation", 1.5), ("rate", -0.1), ("p_value", 2.0),
                      ("direction_agreement", 1.01)):
        with pytest.raises(ES.EvaluatorContractViolation):
            ES.assert_in_range(kind, bad)
    ES.assert_in_range("correlation", 0.5)


def test_14_every_rate_has_a_denominator_contract():
    ES.assert_rate("measurable_rate", 5, 10, 0.5)
    with pytest.raises(ES.EvaluatorContractViolation):
        ES.assert_rate("invented_rate", 1, 2, 0.5)
    with pytest.raises(ES.EvaluatorContractViolation):
        ES.assert_rate("measurable_rate", 11, 10, 1.1)
    with pytest.raises(ES.EvaluatorContractViolation):
        ES.assert_rate("measurable_rate", 5, 10, 0.9)


def test_14_repeated_rows_cannot_inflate_the_experimental_unit():
    ES.assert_unit_not_inflated(3, ["a", "b", "c"])
    with pytest.raises(ES.EvaluatorContractViolation):
        ES.assert_unit_not_inflated(30, ["a", "b", "c"])


def test_14_clustered_se_always_reports_its_cluster_count():
    se, n = ES.clustered_se([0.1, 0.2, 0.3, 0.4], ["a", "a", "b", "b"])
    assert n == 2 and se is not None
    se, n = ES.clustered_se([0.1, 0.2], ["a", "a"])
    assert se is None and n == 1


# =======================================================================================
# Section 15 -- controls
# =======================================================================================
def test_15_control_pool_is_byte_deterministic():
    vocab = sorted(m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block"))
    a = CTRL.enumerate_pool(vocab, 200)
    b = CTRL.enumerate_pool(vocab, 200)
    assert CTRL.pool_hash(a) == CTRL.pool_hash(b)


def test_15_control_generator_can_occupy_every_comparator(cap):
    vocab = sorted(m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block"))
    pool = CTRL.enumerate_pool(vocab, 1200)
    assert set(p["comparison"] for p in pool) == set(ONT.COMPARATOR_BINDINGS)


def test_15_slot_inhabitation_detects_a_crippled_generator(cap):
    """Negative control for the proof itself: a generator that cannot express a comparator
    the treated arm uses must be reported as leaving a slot uninhabited."""
    vocab = sorted(m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block"))
    treated = [_spec(comparison="SUBJECT_RECENT_VS_LONG_BASELINE"),
               _spec(comparison="SUBJECT_OVERALL_BASELINE", conditions=[PROFILE])]
    crippled = [p for p in CTRL.enumerate_pool(vocab, 400)
                if p["comparison"] != "SUBJECT_RECENT_VS_LONG_BASELINE"]
    res = CTRL.slot_inhabitation(treated, crippled, cap)
    assert not res["no_structural_zero_from_generator_incapability"]
    assert any(s["slot"] == "comparator" for s in res["uninhabited"])


def test_15_uniform_pool_does_not_copy_treated_metric_preferences(cap):
    """The end-to-end control must not inherit the LLM's metric choices, or the endpoint
    cannot answer whether choosing what to ask about was worth anything."""
    vocab = sorted(m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block"))
    pool = CTRL.enumerate_pool(vocab, 600, sampling=CTRL.SAMPLING_UNIFORM)
    used = {m for p in pool for m in p["target_metrics"]}
    assert used >= set(vocab) - {"cards"}, "uniform pool is not spanning the vocabulary"


# =======================================================================================
# Section 16 -- evaluability gate
# =======================================================================================
def test_16_gate_blocks_a_thin_apparatus():
    thin = {"n_competitions": 6, "n_folds": 3, "min_fixtures_per_fold": 100,
            "n_evaluable_families": 4, "n_teams": 100,
            "expected_effective_sample": 50.0, "expected_clusters": 9}
    res = EVAL.assess(thin, {"cluster_sigma": 0.03})
    assert res["verdict"] == EVAL.BLOCKED
    assert any(f["check"] == "evaluable_families" for f in res["failures"])


def test_16_gate_passes_a_sufficient_apparatus():
    good = {"n_competitions": 6, "n_folds": 3, "min_fixtures_per_fold": 100,
            "n_evaluable_families": 40, "n_teams": 120,
            "expected_effective_sample": 60.0, "expected_clusters": 9}
    res = EVAL.assess(good, {"cluster_sigma": 0.03})
    assert res["verdict"] == EVAL.READY, res["failures"]


def test_16_required_clusters_scale_with_dispersion():
    assert EVAL.required_clusters(0.08) > EVAL.required_clusters(0.03)
    assert EVAL.required_clusters(0.0) == 0


def test_16_stability_threshold_is_not_loosened_from_v7():
    from src.research.hypothesis_v7 import measurement as V7M
    assert EVAL.DIRECTION_STABILITY_MIN == V7M.DIRECTION_STABILITY_MIN
    assert EVAL.STABILITY_UNIT == "FOLD"
    assert EVAL.CELL_UNIT_REJECTED["unit"] == "FOLD_X_COMPETITION_CELL"


# =======================================================================================
# Section 18 -- fresh sample
# =======================================================================================
def test_18_partition_is_by_season_id_not_by_date():
    recs = CI.load_records(include_fresh=True)
    dev, conf = FS.partition(recs)
    assert conf, "no fresh records loaded"
    assert {str(r.season_id) for r in conf} <= set(FS.FRESH_SEASON_IDS)
    assert not ({str(r.season_id) for r in dev} & set(FS.FRESH_SEASON_IDS))


def test_18_zero_overlap_is_proved_at_fixture_identifier_level():
    recs = CI.load_records(include_fresh=True)
    dev, conf = FS.partition(recs)
    proof = FS.zero_overlap_proof(conf, dev)
    assert proof["proof_level"] == "FIXTURE_IDENTIFIER_SET"
    assert proof["disjoint_from_development"]
    assert proof["disjoint_from_v7_confirmatory"]
    assert proof["n_v7_confirmatory_fixtures"] > 0, "the V7 window is empty: proof is vacuous"


def test_18_folds_are_chronological_and_outcome_blind():
    recs = CI.load_records(include_fresh=True)
    _dev, conf = FS.partition(recs)
    folds = FS.build_folds(conf)
    assert len(folds) == FS.N_FOLDS
    ends = [f["validate_end_unix"] for f in folds]
    starts = [f["validate_start_unix"] for f in folds]
    assert starts == sorted(starts) and ends == sorted(ends)
    ids = [set(f["fixture_ids"]) for f in folds]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            assert not (ids[i] & ids[j]), "folds share a fixture"


def test_18_engine_spec_hash_is_stable():
    assert EN.spec_hash() == EN.spec_hash()
    assert len(EN.spec_hash()) == 64


def test_12_reweighting_cohort_is_evaluated_at_every_frozen_halflife(index, ctx, cap):
    """The frozen recency contract reports BOTH half-lives and selects neither. An engine that
    evaluated one would silently turn a preregistered family into a chosen window."""
    ir = IRM.build_ir(_spec(comparison="SUBJECT_RECENT_VS_LONG_BASELINE"))
    fam = EN.recency_family_for(ir)
    assert len(fam) == len(REC.HALFLIVES_DAYS) > 1
    assert sorted(w.halflife_days for w in fam) == sorted(float(h)
                                                          for h in REC.HALFLIVES_DAYS)
    plain = IRM.build_ir(_spec(conditions=[PROFILE],
                               required_capabilities=["opponent_profile"]))
    assert len(EN.recency_family_for(plain)) == 1
    assert EN.recency_family_for(plain)[0].halflife_days is None


def test_12_averaging_the_family_is_not_the_same_as_picking_one(index, ctx, cap):
    c, cut = ctx
    ir = IRM.build_ir(_spec(comparison="SUBJECT_RECENT_VS_LONG_BASELINE"))
    pos = _first_target(index, cut, 120)
    plan = CF.plan_for(ir.research_family)
    full = EN.evaluate_cell(ir, "shots", index, pos, c, plan, cap,
                            EN.recency_family_for(ir))
    single = EN.evaluate_cell(ir, "shots", index, pos, c, plan, cap,
                              (REC.Recency(REC.HALFLIVES_DAYS[0]),))
    assert full["effect"] is not None and single["effect"] is not None
    assert full["effect"] != single["effect"], "the decay family is not being averaged"
