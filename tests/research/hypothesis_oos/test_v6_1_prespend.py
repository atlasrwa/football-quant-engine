"""V6.1 pre-spend suite. ZERO SPEND -- nothing here calls a network or Bedrock.

This suite guards the ONE substantive V6.1 change: the repaired evaluator
(`v6_1_verdict`) and its generic metric-contract layer (`v6_1_metrics`). It covers:

  * TASK 2/4  the metric contracts (RATE/COUNT/SIGNED_RATE_DELTA/PROBABILITY/SD/SAMPLE_SIZE)
              and the specific compiler_valid_rate repair;
  * TASK 5    property-based / generative tests over randomized legal scorecards, asserting
              no legal scorecard can produce a rate < 0 or > 1, and that no scientific
              verdict is ever built on an impossible metric;
  * TASK 16   the pre-spend path proofs A..R, each as a named test;
  * immutability of the frozen V6 artifacts (the corrected evaluator must not touch them).

Everything runs through the SAME `v6_1_verdict.final_verdict` the corrected replay uses, so a
passing test is a statement about the repaired production path, not a mock of it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_1_metrics as MC
from src.research.hypothesis_oos import v6_1_verdict as V61
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_stop as STOP_MOD
from src.research.hypothesis_oos import v6_verdict as V6

V6_OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
EXEC = f"{V6_OUT}/execution"
CHAMPION = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = \
    "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

# Immutable V6 artifact hashes (verified in TASK 1; re-asserted here so the corrected
# evaluator work can NEVER silently mutate them).
FROZEN_HASHES = {
    "src/research/hypothesis_oos/v6_verdict.py":
        "f195cf7f2db48d47d1bedc20cf6a364efc7b7efca46f5089045d3803b4d99854",
    "src/research/hypothesis_oos/v6_scorecard.py":
        "0b89e96ec042a762bbaf78b4e3cdb9e65054b9514688d6d0c260663f86a13bcf",
    "research/hypothesis_oos/out/v6/EVALUATOR_FREEZE.json":
        "d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c",
    "research/hypothesis_oos/out/v6/execution/V6_VERDICT.json":
        "0225963d1ca6e0ca2accaf6f1e9c84ff1a9077816dd99d4675922782ceac86d6",
    "research/hypothesis_oos/out/v6/execution/scores.json":
        "4ba5f37b98aec2ad2a04cf62f3b40587786a907dd6abe19c6939d2f26cf5ec3c",
}


def _sha(path):
    return hashlib.sha256(open(f"/home/ubuntu/{path}", "rb").read()).hexdigest()


# ========================================================================================
# synthetic legal scorecard factory (matches the real v6_scorecard.score_response schema)
# ========================================================================================
def make_hyp(abstaining: bool, compiler_valid: bool, qualified: bool = False,
             redundant: bool = False) -> dict:
    return {"abstaining": abstaining, "compiler_valid": compiler_valid,
            "qualified": qualified, "redundant": redundant}


def make_scorecard(arm: str, fixture_id: str, hyps: list, rep: int = 0,
                   measured: bool = True) -> dict:
    """A legal per-response scorecard consistent with v6_scorecard semantics.

    Counts are derived from `hyps` so the numerator/denominator relationships are the SAME
    ones the real scorecard produces: n_compiler_valid counts EVERY compilable hypothesis
    (including abstentions -- this is exactly the V6 behavior the repair must tolerate),
    while n_nonabstaining counts only non-abstaining ones.
    """
    if not measured:
        return {"arm": arm, "fixture_id": fixture_id, "rep": rep, "measured": False,
                "response_fatal": True, "per_hypothesis": [], "n_nonabstaining": None,
                "n_compiler_valid": None, "qualified_rate": None}
    n_rec = len(hyps)
    n_abst = sum(1 for h in hyps if h["abstaining"])
    n_nonabst = n_rec - n_abst
    n_comp_all = sum(1 for h in hyps if h["compiler_valid"])          # V6-style (incl abst)
    n_qual = sum(1 for h in hyps if h["qualified"] and not h["abstaining"])
    n_redundant = sum(1 for h in hyps if h["redundant"])
    return {
        "arm": arm, "fixture_id": fixture_id, "rep": rep, "measured": True,
        "response_fatal": False,
        "per_hypothesis": hyps,
        "n_recoverable": n_rec,
        "n_nonabstaining": n_nonabst,
        "n_abstentions": n_abst,
        "n_compiler_valid": n_comp_all,
        "n_qualified": n_qual,
        "n_redundant": n_redundant,
        "n_refs": 0, "n_valid_refs": 0, "n_fabricated_refs": 0,
        "qualified_rate": (n_qual / n_nonabst) if n_nonabst else None,
        "redundancy_rate": (n_redundant / n_rec) if n_rec else None,
        "discipline_violation_rate": 0.0 if n_rec else None,
        "fabricated_evidence_rate": None,
    }


def build_run(base_cards: list, research_cards: list):
    """Assemble a scorecards list + the self-noise inputs the verdict needs."""
    scorecards = base_cards + research_cards
    cells = {}
    for s in scorecards:
        if not s.get("measured"):
            continue
        r = s.get("qualified_rate")
        if r is None:
            continue
        cells.setdefault((s["fixture_id"], s["arm"]), []).append(r)
    groups = [{"fixture_id": f, "arm": a, "values": v} for (f, a), v in cells.items()]
    self_noise = SN.pooled_sd(groups)
    return scorecards, self_noise["n_groups_by_arm"], self_noise


def evaluable_run(*, base_extra=None, research_extra=None):
    """A minimally-EVALUABLE run: 8 paired fixtures x (1 + 3 repeats on 4 of them) so both
    arms clear MIN_PAIRED_FIXTURES=8, MIN_VALID_RESPONSES_PER_ARM=8,
    MIN_REPEAT_GROUPS_PER_ARM=3 and MIN_QUALIFIED_DENOMINATOR=20. The caller can inject
    extra cards per arm to exercise a specific path."""
    base, research = [], []
    # 8 paired fixtures, each with 3 non-abstaining hypotheses (>=20 denominator total)
    for i in range(8):
        f = f"fx_{i:02d}"
        bh = [make_hyp(False, True, qualified=(i % 2 == 0)) for _ in range(3)]
        rh = [make_hyp(False, True, qualified=(i % 2 == 0) or (i % 3 == 0))
              for _ in range(3)]
        base.append(make_scorecard("base", f, bh, rep=0))
        research.append(make_scorecard("research", f, rh, rep=0))
    # add repeats on the first 4 fixtures to make >=3 repeat groups per arm
    for i in range(4):
        f = f"fx_{i:02d}"
        for rep in (1, 2):
            bh = [make_hyp(False, True, qualified=(rep == 1)) for _ in range(3)]
            rh = [make_hyp(False, True, qualified=(rep == 1)) for _ in range(3)]
            base.append(make_scorecard("base", f, bh, rep=rep))
            research.append(make_scorecard("research", f, rh, rep=rep))
    if base_extra:
        base += base_extra
    if research_extra:
        research += research_extra
    return build_run(base, research)


# ========================================================================================
# TASK 2 / 4 -- metric contracts and the compiler_valid_rate repair
# ========================================================================================
class TestMetricContracts:
    def test_rate_rejects_numerator_greater_than_denominator(self):
        with pytest.raises(MC.MetricContractViolation):
            MC.check_rate("compiler_valid_rate", 211, 183)     # the exact V6 defect

    def test_rate_zero_denominator_is_none_not_zero_or_one(self):
        assert MC.check_rate("x", 0, 0) is None

    def test_rate_valid_in_unit_interval(self):
        assert MC.check_rate("x", 183, 183) == 1.0
        assert MC.check_rate("x", 0, 5) == 0.0
        assert MC.check_rate("x", 3, 6) == 0.5

    def test_rate_rejects_negative(self):
        with pytest.raises(MC.MetricContractViolation):
            MC.check_rate("x", -1, 5)
        with pytest.raises(MC.MetricContractViolation):
            MC.check_rate("x", 1, -5)

    def test_rate_rejects_nonfinite(self):
        for bad in (float("inf"), float("nan"), float("-inf")):
            with pytest.raises(MC.MetricContractViolation):
                MC.check_rate("x", bad, 5)

    def test_signed_rate_delta_domain(self):
        assert MC.check_signed_rate_delta("d", 1.0) == 1.0
        assert MC.check_signed_rate_delta("d", -1.0) == -1.0
        assert MC.check_signed_rate_delta("d", None) is None
        with pytest.raises(MC.MetricContractViolation):
            MC.check_signed_rate_delta("d", 1.0001)
        with pytest.raises(MC.MetricContractViolation):
            MC.check_signed_rate_delta("d", -2.0)

    def test_count_and_sample_size(self):
        assert MC.check_count("c", 0) == 0
        with pytest.raises(MC.MetricContractViolation):
            MC.check_count("c", -1)
        with pytest.raises(MC.MetricContractViolation):
            MC.check_count("c", 1.5)
        with pytest.raises(MC.MetricContractViolation):
            MC.check_count("c", True)                          # bool is not a count

    def test_sd_nonnegative(self):
        assert MC.check_sd("sd", 0.0) == 0.0
        assert MC.check_sd("sd", None) is None
        with pytest.raises(MC.MetricContractViolation):
            MC.check_sd("sd", -0.001)

    def test_probability_like_domain(self):
        assert MC.check_value_in_unit_interval("p", 0.5) == 0.5
        with pytest.raises(MC.MetricContractViolation):
            MC.check_value_in_unit_interval("p", 1.5)

    def test_registry_declares_every_rate_semantics(self):
        for name, spec in MC.REGISTRY.items():
            assert spec["type"] in MC.version_stamp()["metric_types"]
            for field in ("numerator", "denominator", "eligibility", "abstention",
                          "zero_denominator", "domain", "aggregation", "arm_direction"):
                assert field in spec, f"{name} missing {field}"

    def test_compiler_repair_excludes_abstentions_from_numerator(self):
        # base arm: 3 non-abstaining (all compile) + 2 abstaining (both compile).
        # OLD numerator would be 5 over denominator 3 -> 1.667 (>1). Repaired: 3/3 = 1.0.
        card = make_scorecard("base", "fx", [
            make_hyp(False, True), make_hyp(False, True), make_hyp(False, True),
            make_hyp(True, True), make_hyp(True, True)])
        assert card["n_compiler_valid"] == 5          # V6-style count (defect source)
        assert card["n_nonabstaining"] == 3
        assert V61.compile_rate([card]) == 1.0        # repaired: never > 1


# ========================================================================================
# TASK 5 -- property-based / generative testing over randomized legal scorecards
# ========================================================================================
hyp_strategy = st.builds(
    make_hyp,
    abstaining=st.booleans(), compiler_valid=st.booleans(),
    qualified=st.booleans(), redundant=st.booleans())


@st.composite
def scorecard_strategy(draw, arm):
    fixture_id = draw(st.sampled_from(["f0", "f1", "f2", "f3", "f4"]))
    measured = draw(st.booleans())
    if not measured:
        return make_scorecard(arm, fixture_id, [], measured=False)
    hyps = draw(st.lists(hyp_strategy, min_size=0, max_size=40))
    return make_scorecard(arm, fixture_id, hyps, rep=draw(st.integers(0, 3)))


@st.composite
def run_strategy(draw):
    base = draw(st.lists(scorecard_strategy("base"), min_size=0, max_size=25))
    research = draw(st.lists(scorecard_strategy("research"), min_size=0, max_size=25))
    return base, research


class TestPropertyBased:
    @settings(max_examples=400, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(run_strategy())
    def test_no_legal_scorecard_yields_out_of_range_rate(self, run):
        """No randomized legal scorecard configuration may produce a rate < 0 or > 1, and
        the verdict must never crash on a legal-but-degenerate configuration -- it either
        returns a scientific status/verdict or an EVALUATOR_INVALID apparatus state."""
        base, research = run
        scorecards, rgpa, self_noise = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, self_noise)
        # the corrected compiler rate is always None or within [0,1]
        if "discipline" in out:
            for axis in out["discipline"]["axes"].values():
                for k in ("base", "research"):
                    v = axis.get(k)
                    assert v is None or (0.0 <= v <= 1.0), f"rate {v} out of range"
        # an invalid metric surfaces as apparatus invalidity, NEVER as a scientific verdict
        if out.get("evaluator_invalid"):
            assert out["scientific_verdict"] is None
            assert out["scientific_status"] == V61.EVALUATOR_INVALID

    @settings(max_examples=300, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(st.lists(hyp_strategy, min_size=0, max_size=60))
    def test_compile_rate_never_exceeds_one_over_any_hypset(self, hyps):
        card = make_scorecard("base", "fx", hyps)
        rate = V61.compile_rate([card])
        assert rate is None or (0.0 <= rate <= 1.0)

    @settings(max_examples=200, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(n_abst=st.integers(0, 30), n_nonabst=st.integers(0, 30),
           n_abst_compile=st.integers(0, 30))
    def test_abstention_heavy_arm_never_exceeds_one(self, n_abst, n_nonabst,
                                                    n_abst_compile):
        """L/M: an abstention-heavy arm (base OR research) with many COMPILABLE abstentions
        must not produce a compiler rate > 1 -- the exact failure mode V6 had."""
        n_abst_compile = min(n_abst_compile, n_abst)
        hyps = ([make_hyp(True, True) for _ in range(n_abst_compile)]
                + [make_hyp(True, False) for _ in range(n_abst - n_abst_compile)]
                + [make_hyp(False, True) for _ in range(n_nonabst)])
        card = make_scorecard("base", "fx", hyps)
        rate = V61.compile_rate([card])
        assert rate is None or rate <= 1.0

    @settings(max_examples=300, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(rate_key=st.sampled_from(["qualified_rate", "fabricated_evidence_rate",
                                     "redundancy_rate", "discipline_violation_rate",
                                     "valid_evidence_reference_rate",
                                     "evidence_specific_qualified_rate"]),
           bad_value=st.floats(allow_nan=True, allow_infinity=True))
    def test_malformed_rate_field_becomes_evaluator_invalid_never_verdict(self, rate_key,
                                                                          bad_value):
        """Phase 5: a MALFORMED scorecard rate (arbitrary float, incl NaN/inf/negative/>1)
        must surface as EVALUATOR_INVALID and NEVER as a scientific PASS/MIXED/FAIL. Only
        legal in-range values may pass; anything else aborts as apparatus invalidity."""
        bad = make_scorecard("base", "fx_bad", [make_hyp(False, True)])
        bad[rate_key] = bad_value
        scorecards, rgpa, sn = evaluable_run(base_extra=[bad])
        out = V61.final_verdict(scorecards, rgpa, sn)
        import math
        legal = isinstance(bad_value, float) and math.isfinite(bad_value) \
            and 0.0 <= bad_value <= 1.0
        if not legal:
            assert out["scientific_status"] == V61.EVALUATOR_INVALID
            assert out["scientific_verdict"] is None

    @settings(max_examples=150, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(base_verbosity=st.integers(1, 3), research_verbosity=st.integers(1, 30),
           dominant_fixture_extra=st.integers(0, 50))
    def test_verbosity_and_fixture_domination_never_break_range(self, base_verbosity,
                                                                research_verbosity,
                                                                dominant_fixture_extra):
        """Phase 5: one arm far more verbose, and one fixture with far more hypotheses,
        must not push any rate out of [0,1] nor invalidate an otherwise-legal run."""
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            nb = base_verbosity + (dominant_fixture_extra if i == 0 else 0)
            nr = research_verbosity + (dominant_fixture_extra if i == 0 else 0)
            base.append(make_scorecard("base", f,
                        [make_hyp(False, True, qualified=(j % 2 == 0)) for j in range(nb)]))
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=(j % 2 == 0))
                             for j in range(nr)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=(rep == 1))], rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=(rep == 1))], rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        if "discipline" in out:
            for axis in out["discipline"]["axes"].values():
                for k in ("base", "research"):
                    v = axis.get(k)
                    assert v is None or (0.0 <= v <= 1.0)


# ========================================================================================
# TASK 16 -- pre-spend path proofs A..R (each a named test)
# ========================================================================================
class TestPrespendPaths:
    def test_A_corrected_compiler_rate_cannot_exceed_one(self):
        card = make_scorecard("base", "fx", [make_hyp(False, True)] * 3
                              + [make_hyp(True, True)] * 10)
        assert V61.compile_rate([card]) <= 1.0

    def test_B_all_metric_contracts_hold_on_evaluable_run(self):
        scorecards, rgpa, sn = evaluable_run()
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert not out.get("evaluator_invalid")

    def test_C_invalid_metric_yields_evaluator_invalid_never_verdict(self):
        # inject a scorecard whose stored qualified_rate is impossible (1.5)
        bad = make_scorecard("base", "fx_bad", [make_hyp(False, True)])
        bad["qualified_rate"] = 1.5
        scorecards, rgpa, sn = evaluable_run(base_extra=[bad])
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_status"] == V61.EVALUATOR_INVALID
        assert out["scientific_verdict"] is None

    def test_D_v6_diagnostic_replay_succeeds(self):
        r = subprocess.run([sys.executable,
                            "/home/ubuntu/research/hypothesis_engine/_v6_1_replay.py"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        doc = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                             "V6_POSTHOC_CORRECTED_REPLAY.json"))
        assert doc["corrected_evaluator"]["discipline"]["axes"][
            "compiler_valid_rate"]["base"] <= 1.0

    def test_E_original_v6_frozen_fail_is_immutable(self):
        for path, want in FROZEN_HASHES.items():
            assert _sha(path) == want, f"{path} changed -- V6 must remain immutable"
        v = json.load(open(f"{EXEC}/V6_VERDICT.json"))["verdict"]
        assert v["scientific_verdict"] == "FAIL"

    def test_F_corrected_replay_is_labeled_non_confirmatory(self):
        doc = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                             "V6_POSTHOC_CORRECTED_REPLAY.json"))
        assert "NON_CONFIRMATORY" in doc["status_tags"]
        assert "DIAGNOSTIC_ONLY" in doc["status_tags"]
        assert doc["is_v6_scientific_verdict"] is False
        assert doc["is_v6_1_confirmatory_evidence"] is False

    def test_G_pass_path_works(self):
        # research strictly better on qualified_rate AND clears self-noise, discipline held
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(make_scorecard("base", f,
                        [make_hyp(False, True, qualified=False) for _ in range(3)]))
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=True) for _ in range(3)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=False) for _ in range(3)],
                            rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=True) for _ in range(3)],
                                rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_status"] == "EVALUABLE"
        assert out["scientific_verdict"] == "PASS", out.get("verdict_reason")

    def test_H_mixed_path_works(self):
        # small positive difference within self-noise -> MIXED
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            bq = 1 if i == 0 else 0
            rq = 2 if i == 0 else 0
            base.append(make_scorecard("base", f,
                        [make_hyp(False, True, qualified=(j < bq)) for j in range(3)]))
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=(j < rq)) for j in range(3)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=False) for _ in range(3)],
                            rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=False) for _ in range(3)],
                                rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_status"] == "EVALUABLE"
        assert out["scientific_verdict"] in ("MIXED", "FAIL")  # positive-within-noise or <=0
        # specifically verify the MIXED branch is reachable with a positive diff
        if out["primary"]["mean_paired_diff"] and out["primary"]["mean_paired_diff"] > 0:
            assert out["scientific_verdict"] == "MIXED"

    def test_I_fail_path_works(self):
        # research WORSE than base -> negative diff -> FAIL
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(make_scorecard("base", f,
                        [make_hyp(False, True, qualified=True) for _ in range(3)]))
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=False) for _ in range(3)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=True) for _ in range(3)],
                            rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=False) for _ in range(3)],
                                rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_verdict"] == "FAIL"

    def test_J_non_evaluable_null_path_works(self):
        # too few fixtures -> NON_EVALUABLE, scientific_verdict is None
        base = [make_scorecard("base", "f0", [make_hyp(False, True)])]
        research = [make_scorecard("research", "f0", [make_hyp(False, True)])]
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_status"] == "NON_EVALUABLE"
        assert out["scientific_verdict"] is None

    def test_K_discipline_gate_path_works(self):
        # research fabricates far more -> discipline degraded -> FAIL before primary
        def _bcard(f, rep=0):
            c = make_scorecard("base", f, [make_hyp(False, True) for _ in range(3)],
                               rep=rep)
            c["n_refs"] = 10; c["n_fabricated_refs"] = 0     # base: clean references
            c["fabricated_evidence_rate"] = 0.0
            return c

        def _rcard(f, rep=0):
            c = make_scorecard("research", f, [make_hyp(False, True) for _ in range(3)],
                               rep=rep)
            c["n_refs"] = 10; c["n_fabricated_refs"] = 9     # research fabricates 90%
            c["fabricated_evidence_rate"] = 0.9
            return c

        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(_bcard(f))
            research.append(_rcard(f))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(_bcard(f, rep))
                research.append(_rcard(f, rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_verdict"] == "FAIL"
        assert "fabricated_evidence_rate" in out["discipline"]["degraded_axes"]

    def test_L_abstention_heavy_base_no_rate_over_one(self):
        base_extra = [make_scorecard("base", "fx_00",
                      [make_hyp(True, True) for _ in range(15)]
                      + [make_hyp(False, True) for _ in range(2)], rep=3)]
        scorecards, rgpa, sn = evaluable_run(base_extra=base_extra)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert not out.get("evaluator_invalid")
        assert out["discipline"]["axes"]["compiler_valid_rate"]["base"] <= 1.0

    def test_M_abstention_heavy_research_no_rate_over_one(self):
        research_extra = [make_scorecard("research", "fx_00",
                          [make_hyp(True, True) for _ in range(15)]
                          + [make_hyp(False, True) for _ in range(2)], rep=3)]
        scorecards, rgpa, sn = evaluable_run(research_extra=research_extra)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert not out.get("evaluator_invalid")
        assert out["discipline"]["axes"]["compiler_valid_rate"]["research"] <= 1.0

    def test_N_zero_denominator_path_is_explicit_none(self):
        # an all-abstention arm has zero non-abstaining -> compiler rate None (not 0/1)
        allabst = [make_scorecard("base", "fx_z", [make_hyp(True, True) for _ in range(4)])]
        assert V61.compile_rate(allabst) is None
        assert MC.REGISTRY["compiler_valid_rate"]["zero_denominator"].startswith("None")

    def test_O_fixture_balanced_primary_unchanged_from_frozen(self):
        # the corrected verdict reuses the FROZEN primary verbatim; on the real scores the
        # mean paired diff must equal the frozen V6 value exactly.
        scores = json.load(open(f"{EXEC}/scores.json"))
        scorecards = [dict(s["scorecard"]) for s in scores]
        cells = {}
        for s in scorecards:
            if s.get("measured") and s.get("qualified_rate") is not None:
                cells.setdefault((s["fixture_id"], s["arm"]), []).append(
                    s["qualified_rate"])
        groups = [{"fixture_id": f, "arm": a, "values": v} for (f, a), v in cells.items()]
        sn = SN.pooled_sd(groups)
        prim = V6.primary(scorecards, sn)
        frozen = json.load(open(f"{EXEC}/V6_VERDICT.json"))["verdict"]["primary"]
        assert prim["mean_paired_diff"] == frozen["mean_paired_diff"]

    def test_P_verbosity_does_not_increase_fixture_weight(self):
        # the primary is fixture-balanced: adding many more hypotheses to one arm's
        # response does NOT change the number of paired fixtures or their equal weight.
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(make_scorecard("base", f, [make_hyp(False, True, qualified=True)]))
            # research response is 20x more verbose but same qualified_rate
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=True) for _ in range(20)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=True)], rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=True) for _ in range(20)],
                                rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        # equal qualified_rate (1.0 both arms) -> per-fixture diff 0 regardless of verbosity
        assert out["primary"]["mean_paired_diff"] == 0.0

    def test_Q_stop_rules_and_thresholds_frozen(self):
        # the corrected verdict reuses the frozen thresholds VERBATIM.
        vs = V61.version_stamp()
        assert vs["discipline_tolerance"] == V6.DISCIPLINE_TOLERANCE == 0.05
        assert vs["min_paired_fixtures"] == V6.MIN_PAIRED_FIXTURES
        assert vs["min_repeat_groups_per_arm"] == V6.MIN_REPEAT_GROUPS_PER_ARM
        assert vs["min_qualified_denominator"] == V6.MIN_QUALIFIED_DENOMINATOR
        assert vs["thresholds_unchanged"] is True

    def test_R_champion_isolation_intact(self):
        got = hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest()
        assert got == CHAMPION_FROZEN_SHA
        # the corrected evaluator must not import any production/prediction module
        import src.research.hypothesis_oos.v6_1_verdict as m
        src = open(m.__file__).read()
        assert "p_model" not in src
        assert "pilotC" not in src and "stat_mixer" not in src


class TestNoLegacyBugInVerdictPath:
    """Phase 2/3: prove the legacy buggy compiler function cannot enter the V6.1 verdict."""

    def test_legacy_compile_rate_unreachable_from_v6_1_verdict(self, monkeypatch):
        # trip-wire the legacy buggy functions; the V6.1 path must never call them.
        def _tripwire(*a, **k):
            raise AssertionError("legacy V6._compile_rate/discipline reached from V6.1")
        monkeypatch.setattr(V6, "_compile_rate", _tripwire)
        monkeypatch.setattr(V6, "discipline", _tripwire)
        scorecards, rgpa, sn = evaluable_run()
        out = V61.final_verdict(scorecards, rgpa, sn)   # must not raise
        assert not out.get("evaluator_invalid")

    def test_old_logic_reproduces_gt_one_new_logic_bounded(self):
        # 3 non-abstaining (compile) + 2 compilable abstentions -> old 5/3 > 1, new 3/3 = 1.
        card = make_scorecard("base", "fx",
                              [make_hyp(False, True)] * 3 + [make_hyp(True, True)] * 2)
        assert V6._compile_rate([card]) > 1.0
        assert 0.0 <= V61.compile_rate([card]) <= 1.0

    def test_exact_historical_v6_numbers_reproduced(self):
        scores = json.load(open(f"{EXEC}/scores.json"))
        base = [dict(s["scorecard"]) for s in scores
                if s["scorecard"].get("measured") and s["scorecard"].get("arm") == "base"]
        num = sum(int(s.get("n_compiler_valid") or 0) for s in base)
        den = sum(int(s.get("n_nonabstaining") or 0) for s in base)
        assert (num, den) == (211, 183)
        assert abs(V6._compile_rate(base) - 1.1530054644808743) < 1e-12
        assert V61.compile_rate(base) == 1.0            # repaired


class TestReplayFirewall:
    """Phase 6: the V6 corrected replay cannot become V6.1 confirmatory evidence."""

    def test_replay_artifact_is_labelled_non_confirmatory(self):
        doc = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                             "V6_POSTHOC_CORRECTED_REPLAY.json"))
        assert doc["status_tags"] == ["NON_CONFIRMATORY", "DIAGNOSTIC_ONLY"]
        assert doc["is_v6_scientific_verdict"] is False
        assert doc["is_v6_1_confirmatory_evidence"] is False
        assert doc["must_not_tune_v6_1"] is True

    def test_v6_fixtures_are_held_out_of_v6_1_selection(self):
        # a V6 fixture can NEVER be selected as a fresh V6.1 confirmatory fixture.
        from src.research.hypothesis_oos import v6_1_fixtures as FX
        sel = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                             "fixture_selection.json"))
        assert not (set(sel["selected_fixtures"]) & set(FX.V6_FIXTURES))
        assert not (set(sel["selected_fixtures"]) & set(FX.HELD_OUT))

    def test_freeze_does_not_read_v6_execution_scores(self):
        # structural firewall: the V6.1 freeze source never references V6 execution scores.
        src = open("/home/ubuntu/research/hypothesis_engine/_freeze_v6_1.py").read()
        assert "out/v6/execution" not in src
        assert "v6/execution/scores" not in src

    def test_injected_v6_response_cannot_populate_v6_1_selection(self):
        # attempt to inject a V6 fixture id into the V6.1 mix -> selection still excludes it.
        from src.research.hypothesis_oos import v6_1_fixtures as FX
        # even if a caller tried to add a V6 fixture, HELD_OUT filtering removes it from the
        # eligible universe, so it cannot enter the confirmatory set.
        universe_ids = {r["fixture_id"] for r in FX._priors_eligible_candidates(
            __import__("src.research.hypothesis_engine.corpus_adapter",
                       fromlist=["load_index"]).load_index())}
        assert not (universe_ids & set(FX.V6_FIXTURES)), \
            "a V6 fixture leaked into the eligible universe"


class TestArmIsolationAndPIT:
    """Phase 8/9: treatment contrast is evidence-only; PIT leakage is rejected."""

    def _packets(self):
        b = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/packets_base.json"))
        r = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                           "packets_research.json"))
        return b, r

    def test_arms_differ_only_in_evidence(self):
        from src.research.hypothesis_oos import v6_token_count as TC
        b, r = self._packets()
        M = "us.anthropic.claude-sonnet-4-6"
        for fid in sorted(b):
            rb = TC.canonical_converse_request(b[fid], model_id=M, temperature=0.0,
                                               max_tokens=8192)
            rr = TC.canonical_converse_request(r[fid], model_id=M, temperature=0.0,
                                               max_tokens=8192)
            assert rb["system"] == rr["system"]
            assert rb["modelId"] == rr["modelId"]
            assert rb["inferenceConfig"] == rr["inferenceConfig"]
            assert rb["toolConfig"] == rr["toolConfig"]      # identical schema/budget
            assert rb["messages"] != rr["messages"]          # only the evidence differs

    def test_all_fixtures_pit_safe(self):
        b, r = self._packets()
        for pk in (b, r):
            for fid, p in pk.items():
                cutoff = p["information_cutoff_unix"]
                for sec in p["sections"]:
                    if sec.get("section_type") != "MATCH_LEVEL_OBSERVATIONS":
                        continue
                    for blk in sec.get("blocks") or []:
                        for row in blk.get("rows") or []:
                            ts = row.get("kickoff_unix") or row.get("date_unix")
                            assert ts is None or ts < cutoff, f"{fid} obs {ts} >= {cutoff}"

    def test_no_market_or_odds_evidence_present(self):
        # market/odds may appear ONLY as firewall declarations that they are absent.
        b, r = self._packets()
        for pk in (b, r):
            for fid, p in pk.items():
                for sec in p["sections"]:
                    if sec.get("section_type") in ("AVAILABILITY_MAP", "METRIC_SEMANTICS",
                                                   "EVIDENCE_CITATION_INSTRUCTIONS"):
                        continue
                    s = json.dumps(sec).lower()
                    assert "over_odds" not in s and "closing_line" not in s

    def test_pit_audit_rejects_injected_leakage(self):
        import copy
        import sys as _sys
        _sys.path.insert(0, "/home/ubuntu/research/hypothesis_engine")
        import _freeze_v6_1 as FZ
        b, r = self._packets()
        fid = sorted(r)[0]
        cutoff = r[fid]["information_cutoff_unix"]
        for mutate in ("future_match", "at_cutoff", "id_leak"):
            pk = {"base": copy.deepcopy(b), "research": copy.deepcopy(r)}
            p = pk["research"][fid]
            sec = next((s for s in p["sections"]
                        if s.get("section_type") == "MATCH_LEVEL_OBSERVATIONS"), None)
            if mutate == "future_match" and sec and sec.get("blocks"):
                sec["blocks"][0].setdefault("rows", []).append(
                    {"kickoff_unix": cutoff + 86400, "cells": [None]})
            elif mutate == "at_cutoff" and sec and sec.get("blocks"):
                sec["blocks"][0].setdefault("rows", []).append(
                    {"date_unix": cutoff, "cells": [None]})
            elif mutate == "id_leak":
                p["sections"].append({"section_type": "NOTE", "leak": f"ref {fid} here"})
            res = FZ.pit_audit(pk)
            assert res["n_problems"] > 0, f"leakage {mutate} NOT rejected"


class TestDisciplineBoundaryAndPrimary:
    """Phase 11/12/13/14: discipline sign+boundary, primary fixture-balance, stop gating."""

    def _disc_card(self, arm, fid, fab_rate, rep=0):
        return {"arm": arm, "fixture_id": fid, "rep": rep, "measured": True,
                "response_fatal": False,
                "per_hypothesis": [{"abstaining": False, "compiler_valid": True}],
                "n_recoverable": 1, "n_nonabstaining": 1, "n_abstentions": 0,
                "n_compiler_valid": 1, "n_qualified": 1, "n_redundant": 0,
                "n_refs": 10, "n_valid_refs": int(round(10 * (1 - fab_rate))),
                "n_fabricated_refs": int(round(10 * fab_rate)),
                "qualified_rate": 1.0, "redundancy_rate": 0.0,
                "discipline_violation_rate": 0.0, "fabricated_evidence_rate": fab_rate}

    def _run_with_fab(self, research_fab):
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(self._disc_card("base", f, 0.0))
            research.append(self._disc_card("research", f, research_fab))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(self._disc_card("base", f, 0.0, rep))
                research.append(self._disc_card("research", f, research_fab, rep))
        return build_run(base, research)

    def test_discipline_degradation_exactly_at_tolerance_does_not_fire(self):
        scorecards, rgpa, sn = self._run_with_fab(0.05)     # delta exactly 0.05
        out = V61.final_verdict(scorecards, rgpa, sn)
        ax = out["discipline"]["axes"]["fabricated_evidence_rate"]
        assert abs(ax["delta"] - 0.05) < 1e-9
        assert ax["degraded"] is False                       # strict >, not >=

    def test_discipline_degradation_just_above_tolerance_fires(self):
        scorecards, rgpa, sn = self._run_with_fab(0.2)       # delta 0.2 > 0.05
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["scientific_verdict"] == "FAIL"
        assert "fabricated_evidence_rate" in out["discipline"]["degraded_axes"]

    def test_research_better_on_discipline_never_degrades(self):
        # base worse than research -> negative delta -> never degradation
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(self._disc_card("base", f, 0.3))     # base fabricates more
            research.append(self._disc_card("research", f, 0.0))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(self._disc_card("base", f, 0.3, rep))
                research.append(self._disc_card("research", f, 0.0, rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert "fabricated_evidence_rate" not in out["discipline"]["degraded_axes"]

    def test_duplicate_hypotheses_do_not_add_fixture_weight(self):
        # duplicating every hypothesis in one arm's response leaves the per-fixture
        # qualified_rate unchanged, so the paired diff is unchanged.
        base, research = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            base.append(make_scorecard("base", f, [make_hyp(False, True, qualified=True)]))
            # research: 5 identical qualified hypotheses -> same rate 1.0
            research.append(make_scorecard("research", f,
                            [make_hyp(False, True, qualified=True) for _ in range(5)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                base.append(make_scorecard("base", f,
                            [make_hyp(False, True, qualified=True)], rep=rep))
                research.append(make_scorecard("research", f,
                                [make_hyp(False, True, qualified=True) for _ in range(5)],
                                rep=rep))
        scorecards, rgpa, sn = build_run(base, research)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert out["primary"]["mean_paired_diff"] == 0.0     # rate identical, verbosity irrelevant
        assert out["primary"]["n_paired_fixtures"] == 8      # still 8 fixtures, not 8*5

    def test_stop_model_rate_gated_apparatus_immediate(self):
        # model firewall 10/10 at ONE fixture must NOT stop; infra failure at 1 call must.
        gated = STOP_MOD.classify_stop(
            n_calls_charged=2, fixtures_observed=["f0"],
            valid_calls_per_arm={"base": 1, "research": 1},
            class_counts={"MODEL_FIREWALL_VIOLATION": 10}, n_hypotheses_adjudicated=10,
            n_responses_fatal=0, n_infrastructure_failures=0,
            n_consecutive_transport_failures=0, spend_usd=0.0, ceiling_usd=8.52)
        assert gated["stop"] is False and gated["model_rules_gated"] is True
        apparatus = STOP_MOD.classify_stop(
            n_calls_charged=1, fixtures_observed=["f0"],
            valid_calls_per_arm={"base": 1, "research": 0}, class_counts={},
            n_hypotheses_adjudicated=0, n_responses_fatal=0,
            n_infrastructure_failures=1, n_consecutive_transport_failures=0,
            spend_usd=0.0, ceiling_usd=8.52)
        assert apparatus["stop"] is True

    def test_v6_1_schedule_prefix_balanced(self):
        sch = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                             "call_schedule.json"))
        p = sch["order_properties"]
        assert sch["n_calls"] == 36 and sch["frozen"] is True
        assert p["prefix_n_distinct_fixtures"] >= 3
        assert p["prefix_calls_per_arm"]["base"] == p["prefix_calls_per_arm"]["research"]
        assert p["arms_adjacent_within_fixture"] is True
        assert p["no_fixture_dominates_prefix"] is True


class TestCanonicalizationCostProvider:
    """Phase 15/16/17/18: request hash-bind, cost recompute, provider config, CHAMPION."""

    def test_canonical_request_hash_binds_all_executable_fields(self):
        import copy
        from src.research.hypothesis_oos import v6_token_count as TC
        pk = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                            "packets_base.json"))
        fid = sorted(pk)[0]
        M = "us.anthropic.claude-sonnet-4-6"
        r = TC.canonical_converse_request(pk[fid], model_id=M, temperature=0.0,
                                          max_tokens=8192)
        h0 = TC.request_sha256(r)
        mutations = [
            lambda x: dict(x, modelId="other.model"),
            lambda x: {**x, "inferenceConfig": {**x["inferenceConfig"],
                                                "temperature": 0.7}},
            lambda x: {**x, "inferenceConfig": {**x["inferenceConfig"],
                                                "maxTokens": 4096}},
            lambda x: {**x, "system": [{"text": "HACKED"}]},
            lambda x: {**x, "messages": [{"role": "user",
                                         "content": [{"text": "tampered"}]}]},
            lambda x: {**x, "toolConfig": {"tools": []}}]
        for mut in mutations:
            assert TC.request_sha256(mut(copy.deepcopy(r))) != h0
        # the frozen manifest binds to this exact hash
        tm = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                            "INPUT_TOKEN_MANIFEST.json"))
        e = [x for x in tm["entries"]
             if x["fixture_id"] == fid and x["arm"] == "base"][0]
        assert e["request_sha256"] == h0

    def test_hard_ceiling_recomputes_to_8_52_with_decimal(self):
        from decimal import ROUND_CEILING, Decimal
        exact = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v6_1/"
                              "EXACT_INPUT_TOKEN_MANIFEST.json"))
        pc = exact["pricing_contract"]
        pin = Decimal(str(pc["input_price_per_1k_usd"])) / Decimal(1000)
        pout = Decimal(str(pc["output_price_per_1k_usd"])) / Decimal(1000)
        total = Decimal(0)
        for e in exact["entries"]:
            it = int(e["exact_input_tokens"])
            ot = int(e["max_output_tokens"])
            assert 0 < it <= e["conservative_byte_upper_bound"]
            assert e["max_billable_attempts"] == 1
            total += (Decimal(it) * pin + Decimal(ot) * pout).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING)
        assert len(exact["entries"]) == 36
        assert str(total) == exact["hard_max_cost_usd"] == "8.52"

    def test_transport_retries_disabled_and_provider_frozen(self):
        from src.research.hypothesis_oos import v6_transport as TRN
        assert TRN.MODEL_ID == "us.anthropic.claude-sonnet-4-6"
        assert TRN.REGION_NAME == "us-east-1"
        assert TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL == 1
        c = TRN.build_client()
        assert TRN.client_max_attempts(c) == 1
        assert TRN.assert_no_retries(c)["retries_disabled_on_client"] is True

    def test_champion_isolated_and_unchanged(self):
        import importlib
        import types
        assert hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest() \
            == CHAMPION_FROZEN_SHA
        for mod in ("v6_1_metrics", "v6_1_verdict", "v6_1_fixtures"):
            m = importlib.import_module(f"src.research.hypothesis_oos.{mod}")
            for name in dir(m):
                obj = getattr(m, name)
                if isinstance(obj, types.ModuleType):
                    assert not any(t in obj.__name__.lower()
                                   for t in ("pilot", "stat_mixer", "champion", "p_model"))


class TestAdversarialVerdictPaths:
    """Phase 24: all verdict paths + explicit boundary semantics (no FP accident)."""

    def _run(self, b, r):
        return build_run(b, r)

    def _eval_run(self, base_q, research_q):
        """8 paired fixtures + 4x2 repeats; base_q/research_q = #qualified of 3 per fixture."""
        b, r = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            b.append(make_scorecard("base", f,
                     [make_hyp(False, True, qualified=(j < base_q[i])) for j in range(3)]))
            r.append(make_scorecard("research", f,
                     [make_hyp(False, True, qualified=(j < research_q[i]))
                      for j in range(3)]))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                b.append(make_scorecard("base", f,
                         [make_hyp(False, True)] * 3, rep=rep))
                r.append(make_scorecard("research", f,
                         [make_hyp(False, True)] * 3, rep=rep))
        return build_run(b, r)

    def test_path_clear_pass(self):
        sc, rg, sn = self._eval_run([0] * 8, [3] * 8)
        o = V61.final_verdict(sc, rg, sn)
        assert o["scientific_verdict"] == "PASS"
        assert o["primary"]["mean_paired_diff"] > o["primary"]["benchmark"]["benchmark"]

    def test_path_primary_fail_diff_negative(self):
        sc, rg, sn = self._eval_run([3] * 8, [0] * 8)
        o = V61.final_verdict(sc, rg, sn)
        assert o["scientific_verdict"] == "FAIL"
        assert o["primary"]["mean_paired_diff"] < 0

    def test_path_non_evaluable_few_fixtures(self):
        sc, rg, sn = build_run([make_scorecard("base", "f0", [make_hyp(False, True)])],
                               [make_scorecard("research", "f0", [make_hyp(False, True)])])
        o = V61.final_verdict(sc, rg, sn)
        assert o["scientific_status"] == "NON_EVALUABLE"
        assert o["scientific_verdict"] is None

    def test_path_evaluator_invalid_impossible_rate(self):
        bad = make_scorecard("base", "fxb", [make_hyp(False, True)])
        bad["qualified_rate"] = 1.5
        sc, rg, sn = self._eval_run([0] * 8, [0] * 8)
        sc = sc + [bad]
        o = V61.final_verdict(sc, rg, sn)
        assert o["scientific_status"] == V61.EVALUATOR_INVALID
        assert o["scientific_verdict"] is None

    def test_path_all_abstention_arm_non_evaluable_not_invalid(self):
        b, r = [], []
        for i in range(8):
            f = f"fx_{i:02d}"
            b.append(make_scorecard("base", f, [make_hyp(True, True)] * 3))
            r.append(make_scorecard("research", f,
                     [make_hyp(False, True, qualified=True)] * 3))
        for i in range(4):
            f = f"fx_{i:02d}"
            for rep in (1, 2):
                b.append(make_scorecard("base", f, [make_hyp(True, True)] * 3, rep=rep))
                r.append(make_scorecard("research", f,
                         [make_hyp(False, True, qualified=True)] * 3, rep=rep))
        sc, rg, sn = build_run(b, r)
        o = V61.final_verdict(sc, rg, sn)
        assert not o.get("evaluator_invalid")               # graceful, not a crash
        assert o["scientific_status"] in ("NON_EVALUABLE", "EVALUABLE")

    def test_primary_boundary_is_strict_greater_than(self):
        # exceeds_self_noise must be a strict >: at-benchmark is MIXED, above is PASS.
        import inspect
        src = inspect.getsource(V6.primary)
        assert "mean_diff > bench" in src.replace('["benchmark"]', "").replace(
            '"benchmark"', "bench") or "> bench" in src

    def test_discipline_boundary_is_strict_greater_than(self):
        import inspect
        src = inspect.getsource(V6.discipline)
        assert "delta > DISCIPLINE_TOLERANCE" in src         # strict, not >=


# ========================================================================================
# TASK 15 -- abstention contract (every metric states abstention treatment; abstentions
# never inflate compiler validity, never enter an inapplicable denominator, never auto-
# qualify, never auto-count as model failure)
# ========================================================================================
class TestAbstentionContract:
    def test_every_registry_metric_declares_abstention_treatment(self):
        for name, spec in MC.REGISTRY.items():
            assert spec["abstention"], f"{name} does not declare abstention treatment"

    def test_abstention_excluded_from_compiler_numerator_and_denominator(self):
        # a pure-abstention response: no non-abstaining -> compiler rate is None (undefined),
        # NOT 1.0 (which the defect would have implied by counting compilable abstentions).
        card = make_scorecard("base", "fx", [make_hyp(True, True) for _ in range(8)])
        assert card["n_nonabstaining"] == 0
        assert V61.compile_rate([card]) is None

    def test_compilable_abstention_does_not_inflate_compiler_validity(self):
        # 2 non-abstaining (both compile) + 8 compilable abstentions.
        # defect: numerator 10 / denominator 2 = 5.0. repaired: 2/2 = 1.0.
        card = make_scorecard("base", "fx",
                              [make_hyp(False, True), make_hyp(False, True)]
                              + [make_hyp(True, True) for _ in range(8)])
        assert card["n_compiler_valid"] == 10
        assert V61.compile_rate([card]) == 1.0

    def test_abstention_does_not_auto_qualify(self):
        # an abstention with qualified flag set must not enter n_qualified (non-abstaining
        # only) -- make_scorecard mirrors the frozen scorecard's non-abstaining gate.
        card = make_scorecard("base", "fx",
                              [make_hyp(True, True, qualified=True) for _ in range(3)])
        assert card["n_qualified"] == 0

    def test_abstention_heavy_asymmetry_does_not_break_verdict(self):
        # base abstains heavily (like V6), research does not: verdict must be valid, not
        # EVALUATOR_INVALID, and the compiler axis must be in-range for both arms.
        base_extra = [make_scorecard("base", f"fx_0{i}",
                      [make_hyp(True, True) for _ in range(10)]
                      + [make_hyp(False, True) for _ in range(2)], rep=3)
                      for i in range(2)]
        scorecards, rgpa, sn = evaluable_run(base_extra=base_extra)
        out = V61.final_verdict(scorecards, rgpa, sn)
        assert not out.get("evaluator_invalid")
        for arm in ("base", "research"):
            v = out["discipline"]["axes"]["compiler_valid_rate"][arm]
            assert v is None or (0.0 <= v <= 1.0)


# ========================================================================================
# immutability guard (re-asserted independently of the path tests)
# ========================================================================================
def test_v6_artifacts_untouched():
    for path, want in FROZEN_HASHES.items():
        assert _sha(path) == want
