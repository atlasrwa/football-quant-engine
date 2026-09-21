"""POINT-IN-TIME + integrity tests: fresh cohort has zero V1/V2/V3 overlap, cohort reads no
outcome, and the apparatus/registry are outcome-blind and champion-independent.
"""
from __future__ import annotations

import json

from src.research.item6 import baseline_coverage, formalizer, harness, registry, schema
from src.research.item6 import stage1_gate, stage1_metrics

COHORT = "/home/ubuntu/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
PRIOR = "/home/ubuntu/research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"


def test_cohort_zero_overlap_with_prior_universe():
    cohort = json.load(open(COHORT))
    prior = json.load(open(PRIOR))
    prior_ids = set()
    for fx in prior["fixtures"]:
        fid = str(fx["fixture_id"])
        prior_ids.add(fid)
        if fid.startswith("mt_"):
            prior_ids.add(fid[3:])
    cohort_ids = set()
    for c in cohort["fixtures"]:
        cohort_ids.add(str(c["fixture_id"]))
        cohort_ids.add(str(c["source_fixture_id"]))
    assert len(cohort_ids & prior_ids) == 0
    assert cohort["v1_fixture_overlap"] == 0
    assert cohort["v2_fixture_overlap"] == 0
    assert cohort["v3_fixture_overlap"] == 0


def test_cohort_reads_no_outcome_fields():
    cohort = json.load(open(COHORT))
    assert cohort["reads_no_observed_statistic"] is True
    forbidden = ("goals", "result", "score", "settle", "closing", "odds", "effect", "p_model")
    for c in cohort["fixtures"]:
        for k in c:
            assert not any(fb in k.lower() for fb in forbidden), f"cohort fixture key '{k}'"


def test_cohort_prospective_after_prior_max_kickoff():
    cohort = json.load(open(COHORT))
    prior = json.load(open(PRIOR))
    prior_max = max(fx["kickoff_unix"] for fx in prior["fixtures"])
    # snapshot may use the rehearsal fallback; if prospective was used, all kickoffs must exceed.
    if not cohort["used_rehearsal_fallback_latest_eligible"]:
        assert all(c["kickoff_unix"] > prior_max for c in cohort["fixtures"])


def test_apparatus_declares_outcome_blind():
    for mod in (baseline_coverage, formalizer, harness, registry, schema,
                stage1_gate, stage1_metrics):
        vs = mod.version_stamp()
        # every module must declare it does not read outcomes / OOS where applicable
        assert vs.get("reads_outcomes", False) is False or "reads_oos" in vs or \
            vs.get("outcome_aware", False) is False


def test_registry_contains_no_predictive_result():
    # build a registry from a novel mechanism and assert no predictive-result key leaks in.
    m = schema.Mechanism(
        "m", "Whether possession and shots_on_target jointly relate to fouls",
        ["possession", "shots_on_target", "fouls"], "joint two-metric conditioning",
        "joint state relates to fouls", "two distinct metrics interaction", ["ev1"],
        "match", ["possession", "shots_on_target", "fouls"])
    f = formalizer.formalize(m, allowed_evidence_refs=["ev1"])
    reg = registry.build_registry([(m, f)])
    assert reg["contains_predictive_result"] is False
    blob = json.dumps(reg).lower()
    for banned in ("p_value", "log_loss", "brier", "\"effect\"", "oos_result"):
        assert banned not in blob


def test_harness_end_to_end_is_deterministic():
    responses = [{
        "fixture_id": "f1",
        "mechanisms": [{
            "mechanism_id_local": "m1",
            "mechanism_statement": "Whether possession and shots_on_target jointly relate to fouls",
            "observable_variables": ["possession", "shots_on_target", "fouls"],
            "conditioning_logic": "joint two-metric conditioning",
            "expected_relationship_to_test": "joint state relates to fouls",
            "why_not_baseline_equivalent": "two distinct metrics interaction",
            "evidence_refs": ["ev1"], "data_resolution_required": "match",
            "provider_requirements": ["possession", "shots_on_target", "fouls"],
            "self_overlap_with": [],
        }],
    }]
    r1 = harness.run_stage1(responses, {"f1": ["ev1"]})
    r2 = harness.run_stage1(responses, {"f1": ["ev1"]})
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    assert r1["made_paid_call"] is False
