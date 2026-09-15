"""COUNTERFACTUAL REPLAY of the frozen SONNET46_HYPOTHESIS_V2 outputs. ZERO SPEND.

WHAT THIS IS, AND EMPHATICALLY WHAT IT IS NOT
---------------------------------------------
This is a DIAGNOSTIC replay. It takes the immutable raw responses already recorded in
`hypothesis_states.jsonl` and passes them through the corrected V3 contract /
normalization / compiler apparatus, to answer one question:

    After removing known infrastructure defects, what evidence of research depth actually
    remains in the already-recorded V2 outputs?

It is NOT a corrected V2 verdict. It does not rescore V2, does not overwrite any V2 metric,
does not touch any V2 artifact, and makes no LLM call. The frozen verdict is unchanged and
unchangeable:

    SONNET46_HYPOTHESIS_V2 = FAIL

A REPLAY MEASURES THE APPARATUS, NOT THE MODEL
----------------------------------------------
The replay can only tell us what the EXISTING TEXT would have done under a corrected
contract. It cannot tell us what the model would have WRITTEN had it been shown the
corrected contract, the gated ontology and the evidence-reference channel -- those change
the input, and only a new run can measure their effect. Every depth number below is
therefore a lower bound on what a de-confounded experiment could observe, not a prediction
of one.

TWO DENOMINATORS, ALWAYS REPORTED TOGETHER
------------------------------------------
Fixing the firewall's class-C false positive changes WHICH responses survive to be
compiled at all, so a single compile rate would not be apples-to-apples:

  (a) SAME-SURVIVOR arm -- the 7 reference responses that survived firewall v1. Isolates
      the effect of canonicalization alone, denominator held fixed.
  (b) FULL arm -- every reference response surviving firewall v2. The rate the corrected
      apparatus would actually report.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import (availability, capability, condition_contract,
                                        firewall, firewall_v2, lifecycle, normalize,
                                        query_plan, schema, schema_v2, validator,
                                        validator_v2)

OUT = f"{ROOT}/research/hypothesis_engine/out"
RUN_DIR = f"{OUT}/hypothesis_v1_sonnet46_v2"
STATES = f"{RUN_DIR}/hypothesis_states.jsonl"
FROZEN_EVAL = f"{RUN_DIR}/evaluation_report.json"
PKT = f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v2.json"

DEST = f"{OUT}/V2_COUNTERFACTUAL_REPLAY_v3contract"

REPLAY_VERSION = "v2_counterfactual_replay_v1"


def _entropy(counter) -> float:
    """Shannon entropy over the comparison mix, in bits.

    Quantifies the V2 diagnosis's "152/159 against SUBJECT_OVERALL_BASELINE" collapse:
    0.0 bits means every intent named the same baseline.
    """
    import math
    total = sum(counter.values())
    if not total:
        return 0.0
    h = 0.0
    for n in counter.values():
        if n:
            p = n / total
            h -= p * math.log2(p)
    return round(h, 4)


def manifest_of(packet: dict) -> capability.FixtureCapabilityManifest:
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))


def load():
    packets = json.load(open(PKT))
    rows = [json.loads(l) for l in open(STATES) if l.strip()]
    frozen = json.load(open(FROZEN_EVAL))
    return packets, rows, frozen


# --------------------------------------------------------------------------------------
# Arm 1 -- ORIGINAL. Byte-for-byte the frozen V2 path.
# --------------------------------------------------------------------------------------
def original_arm(raw, packet, manifest):
    result = validator.validate(
        raw, packet=packet, expected_packet_hash=packet.get("packet_hash"),
        expected_fixture_id=packet.get("fixture_id"), manifest=manifest)
    out = {"whole_response_failure": result.failure,
           "n_hypotheses": len(raw.get("hypotheses") or []),
           "n_accepted": 0, "n_compilable": 0, "n_plans": 0,
           "failure_breakdown": {}, "compile_reasons": []}
    if not result.accepted:
        return out
    compiled = query_plan.compile_set(
        {"fixture_id": packet["fixture_id"], "hypotheses": result.accepted_hypotheses},
        cutoff_unix=packet.get("information_cutoff_unix", 0), manifest=manifest)
    out["n_accepted"] = result.n_accepted
    out["n_compilable"] = compiled["n_fully_compilable"]
    out["n_plans"] = sum(len(v) for v in compiled["results"].values())
    bd = Counter()
    reasons = []
    for results in compiled["results"].values():
        for r in results:
            if not r["ok"]:
                bd[r["failure"]] += 1
                reasons.extend(r["reasons"])
    out["failure_breakdown"] = dict(bd)
    out["compile_reasons"] = reasons
    return out


# --------------------------------------------------------------------------------------
# Arm 2 -- COUNTERFACTUAL. Corrected contract, same compiler, same granularity.
# --------------------------------------------------------------------------------------
def counterfactual_arm(raw, packet, manifest):
    """Canonicalize at the boundary, then run the UNCHANGED v1 compiler.

    Compilation granularity is deliberately held identical to the original arm
    (per-hypothesis, not whole-response), so the only variable between the two arms is
    the encoding contract. What schema-v2 would ADDITIONALLY have rejected outright is
    reported separately, in `schema_v2_whole_response_rejection`, rather than being folded
    into the compile rate -- mixing them would make the two arms incomparable.
    """
    canon, creport = condition_contract.canonicalize_payload(raw)

    # Firewall v2: class C suppressed, classes A and B still block.
    findings = firewall_v2.scan(canon, packet=packet)
    blocking = firewall_v2.blocking(findings)

    # What the real V3 pipeline would say (reported, not used for the rate).
    v2_full = validator_v2.validate(
        raw, packet=packet, manifest=manifest,
        expected_packet_hash=packet.get("packet_hash"),
        expected_fixture_id=packet.get("fixture_id"))

    out = {
        "canonicalization": creport.to_dict(),
        "firewall_classes": firewall_v2.classification_counts(findings),
        "n_suppressed_class_c": len(firewall_v2.suppressed(findings)),
        "whole_response_failure": None,
        "n_hypotheses": len(canon.get("hypotheses") or []),
        "n_accepted": 0, "n_compilable": 0, "n_plans": 0,
        "failure_breakdown": {}, "compile_reasons": [],
        "schema_v2_whole_response_rejection": (
            v2_full.failure if v2_full.failure == lifecycle.SCHEMA_INVALID else None),
        "schema_v2_rejection_reasons": (
            v2_full.reasons if v2_full.failure == lifecycle.SCHEMA_INVALID else []),
    }

    if blocking:
        out["whole_response_failure"] = (
            lifecycle.LATENT_GRADING_VIOLATION
            if all(v.layer == "GRADE" for v in blocking)
            else lifecycle.NUMERICAL_AUTHORITY_VIOLATION)
        out["blocking_classes"] = sorted({v.cls for v in blocking})
        return out

    # Grounding gate, unchanged from v1, applied to the canonicalized payload.
    valid_ids = {it.get("id") for it in (packet.get("evidence") or []) if it.get("id")}
    accepted = []
    for h in canon.get("hypotheses") or []:
        v = validator._validate_one(h, h.get("hypothesis_id", "<anon>"),
                                    valid_ids, manifest, True)
        if v.accepted:
            accepted.append(h)

    compiled = query_plan.compile_set(
        {"fixture_id": packet["fixture_id"], "hypotheses": accepted},
        cutoff_unix=packet.get("information_cutoff_unix", 0), manifest=manifest)
    out["n_accepted"] = len(accepted)
    out["n_compilable"] = compiled["n_fully_compilable"]
    out["n_plans"] = sum(len(v) for v in compiled["results"].values())
    bd = Counter()
    reasons = []
    for results in compiled["results"].values():
        for r in results:
            if not r["ok"]:
                bd[r["failure"]] += 1
                reasons.extend(r["reasons"])
    out["failure_breakdown"] = dict(bd)
    out["compile_reasons"] = reasons
    out["accepted_hypotheses"] = accepted
    return out


# --------------------------------------------------------------------------------------
# Research-structure diagnostics on the COUNTERFACTUAL intents
# --------------------------------------------------------------------------------------
def evidence_driven(intent: dict) -> bool:
    """Deterministic 'is this question fixture-specific, or a template?'

    Evidence-driven means the intent MATERIALLY uses fixture context: it conditions on a
    cohort dimension, or it names a baseline other than the subject's own unconditional
    one. A bare `SUBJECT_OVERALL_BASELINE` question with no condition would read the same
    on any fixture in the corpus and needed no evidence to write, however many evidence
    ids it happens to cite.
    """
    if intent.get("conditions"):
        return True
    if intent.get("comparison") != "SUBJECT_OVERALL_BASELINE":
        return True
    if (intent.get("period") or "ALL") != "ALL":
        return True
    return False


def main() -> int:
    packets, rows, frozen = load()
    os.makedirs(DEST, exist_ok=True)

    per_call = []
    for row in sorted(rows, key=lambda r: r["seq"]):
        raw = row.get("raw_response")
        packet = packets.get(row["packet_key"])
        if raw is None or packet is None:
            continue
        manifest = manifest_of(packet)
        orig = original_arm(raw, packet, manifest)
        cf = counterfactual_arm(raw, packet, manifest)
        per_call.append({
            "seq": row["seq"], "control": row["control"],
            "fixture_id": row["fixture_id"], "packet_key": row["packet_key"],
            "original": orig, "counterfactual": cf,
        })

    reference = [c for c in per_call if c["control"] == "reference"]

    # ---- compile rates, both denominators --------------------------------------------
    def rate(calls, arm):
        acc = sum(c[arm]["n_accepted"] for c in calls)
        comp = sum(c[arm]["n_compilable"] for c in calls)
        return {"n_accepted": acc, "n_compilable": comp,
                "compile_rate": (comp / acc) if acc else 0.0}

    survivors_v1 = [c for c in reference if c["original"]["whole_response_failure"] is None]
    survivors_v2 = [c for c in reference
                    if c["counterfactual"]["whole_response_failure"] is None]

    compile_rates = {
        "frozen_v2_reported_query_compile_rate":
            frozen["metrics"]["query_compile_rate"],
        "arm_original_recomputed_all_12_reference": rate(reference, "original"),
        "arm_counterfactual_all_12_reference": rate(reference, "counterfactual"),
        "same_survivor_arm": {
            "description": ("the reference responses that survived firewall v1; "
                            "denominator held fixed so the ONLY variable is "
                            "condition canonicalization"),
            "n_responses": len(survivors_v1),
            "original": rate(survivors_v1, "original"),
            "counterfactual": rate(survivors_v1, "counterfactual"),
        },
        "full_arm": {
            "description": ("every reference response surviving firewall v2; the rate "
                            "the corrected apparatus would actually report"),
            "n_responses": len(survivors_v2),
            "counterfactual": rate(survivors_v2, "counterfactual"),
        },
    }

    # ---- failure accounting -----------------------------------------------------------
    orig_fail = Counter()
    cf_fail = Counter()
    for c in reference:
        orig_fail.update(c["original"]["failure_breakdown"])
        cf_fail.update(c["counterfactual"]["failure_breakdown"])

    alias_counts = Counter()
    contract_failures = Counter()
    contract_failure_examples = defaultdict(list)
    for c in reference:
        cr = c["counterfactual"]["canonicalization"]
        for k, v in cr["alias_counts"].items():
            alias_counts[k] += v
        for hid, fails in cr["failures"].items():
            for f in fails:
                contract_failures[f["reason"]] += 1
                ex = {"fixture": c["fixture_id"], "hypothesis": hid,
                      "dimension": f["dimension"], "value": f["value"],
                      "axis": f["axis"]}
                if ex not in contract_failure_examples[f["reason"]]:
                    contract_failure_examples[f["reason"]].append(ex)

    failures_removed = {
        "original_reference_compiler_failures": dict(orig_fail),
        "counterfactual_reference_compiler_failures": dict(cf_fail),
        "n_removed_by_canonicalization": sum(orig_fail.values()) - sum(cf_fail.values()),
        "alias_resolutions_applied": dict(alias_counts),
        "remaining_contract_failures_by_reason": dict(contract_failures),
        "remaining_contract_failure_examples": {k: v for k, v in
                                                contract_failure_examples.items()},
    }

    # ---- utilization, availability-gated ----------------------------------------------
    per_fixture_util = []
    dim_used_total = Counter()
    dim_offered_fixtures = Counter()
    dim_used_fixtures = Counter()
    comparison_total = Counter()
    n_intents_total = 0
    n_evidence_driven = 0
    n_beyond_venue = 0
    n_hyps_total = 0
    n_interactions = 0
    n_justified_interactions = 0
    n_any_padding = 0
    n_withheld_conditions = 0

    for c in reference:
        cf = c["counterfactual"]
        packet = packets[c["packet_key"]]
        ont = availability.build_ontology(packet, manifest_of(packet))
        accepted = cf.get("accepted_hypotheses") or []
        payload = {"hypotheses": accepted}
        intents = [i.to_dict() for i in normalize.normalize_set(payload)]
        n_intents_total += len(intents)

        for i in intents:
            if evidence_driven(i):
                n_evidence_driven += 1
            beyond = [c for c in i["conditions"] if c["dimension"] != "venue"]
            if beyond:
                n_beyond_venue += 1
            comparison_total[i["comparison"]] += 1
            for cond in i["conditions"]:
                dim_used_total[cond["dimension"]] += 1

        util = availability.depth_utilization(intents, ont)
        comps = availability.comparison_utilization(intents, ont)
        restraint = availability.restraint_profile(payload, ont)

        for dim, d in ont.dimensions.items():
            if d.expectable:
                dim_offered_fixtures[dim] += 1
                if util[dim]["n_intents_using"] > 0:
                    dim_used_fixtures[dim] += 1

        n_hyps_total += restraint["n_hypotheses"]
        n_interactions += round(restraint["interaction_rate"] * restraint["n_hypotheses"])
        n_justified_interactions += round(
            restraint["justified_interaction_rate"] * restraint["n_hypotheses"])
        n_any_padding += restraint["any_padding_conditions"]
        n_withheld_conditions += restraint["conditions_on_withheld_dimensions"]

        per_fixture_util.append({
            "fixture_id": c["fixture_id"],
            "whole_response_failure": cf["whole_response_failure"],
            "n_intents": len(intents),
            "ontology": ont.to_dict(),
            "dimension_utilization": util,
            "comparison_utilization": comps,
            "restraint": restraint,
        })

    utilization = {
        "n_counterfactual_intents_over_12_reference_responses": n_intents_total,
        "condition_family_utilization_intent_level": dict(dim_used_total),
        "availability_gated_fixture_level": {
            dim: {
                "n_fixtures_where_expectable": dim_offered_fixtures.get(dim, 0),
                "n_of_those_fixtures_using_it": dim_used_fixtures.get(dim, 0),
                "utilization": (round(dim_used_fixtures.get(dim, 0)
                                      / dim_offered_fixtures[dim], 4)
                                if dim_offered_fixtures.get(dim) else None),
            }
            for dim in sorted(set(list(dim_offered_fixtures) + list(dim_used_total)))
        },
        "comparison_utilization_intent_level": dict(comparison_total),
        "depth_beyond_venue": {
            "n_intents_with_a_non_venue_condition": n_beyond_venue,
            "rate": (round(n_beyond_venue / n_intents_total, 4)
                     if n_intents_total else None),
            "why_reported": (
                "venue dominates the condition count, and no packet supplies a "
                "venue-SPLIT evidence item (every evidence scope is venue=ALL), so the "
                "headline evidence-driven rate is carried almost entirely by one "
                "dimension. This is the conditional breadth beyond it."),
        },
        "comparison_shannon_entropy_bits": _entropy(comparison_total),
        "restraint_aggregate": {
            "n_hypotheses": n_hyps_total,
            "n_two_condition_interactions": n_interactions,
            "interaction_rate": (round(n_interactions / n_hyps_total, 4)
                                 if n_hyps_total else None),
            "n_justified_interactions": n_justified_interactions,
            "any_padding_conditions": n_any_padding,
            "conditions_on_withheld_dimensions": n_withheld_conditions,
            "gratuitous_complexity_note": (
                "zero ANY-padding and zero conditions on withheld dimensions means the "
                "recorded outputs show no gratuitous complexity at all -- the model never "
                "asked for score-state, period or any dimension its packet withheld"),
        },
        "evidence_driven_vs_generic": {
            "n_evidence_driven": n_evidence_driven,
            "n_generic_overall_baseline": n_intents_total - n_evidence_driven,
            "evidence_driven_rate": (round(n_evidence_driven / n_intents_total, 4)
                                     if n_intents_total else None),
            "definition": ("evidence-driven = the normalized intent carries at least one "
                           "cohort condition, or a baseline other than the subject's own "
                           "unconditional one, or a non-ALL period; a bare "
                           "SUBJECT_OVERALL_BASELINE question with no condition would "
                           "read identically on any fixture in the corpus"),
        },
    }

    # ---- firewall reclassification ----------------------------------------------------
    fw = {"reference": Counter(), "all_controls": Counter()}
    fw_block = {"reference": 0, "all_controls": 0}
    v1_hits = {"reference": 0, "all_controls": 0}
    for row in rows:
        raw = row.get("raw_response")
        if raw is None:
            continue
        packet = packets.get(row["packet_key"])
        got = firewall_v2.scan(raw, packet=packet)
        scopes = ["all_controls"] + (["reference"] if row["control"] == "reference" else [])
        for s in scopes:
            fw[s].update(firewall_v2.classification_counts(got))
            fw_block[s] += len(firewall_v2.blocking(got))
            v1_hits[s] += len(firewall.scan(raw))

    firewall_report = {
        "v1_total_hits": v1_hits,
        "v2_classification": {k: dict(v) for k, v in fw.items()},
        "v2_blocking_hits": fw_block,
        "note": ("v2 finds the SAME matches as v1 and differs only in classification; "
                 "class C carries no number and is explained entirely by an approved "
                 "metric name, class B is a supplied value copied into prose and still "
                 "blocks, class A is a generated number and still blocks"),
        "responses_rejected_whole": {
            "original_firewall_v1_reference":
                sum(1 for c in reference
                    if c["original"]["whole_response_failure"]
                    == lifecycle.NUMERICAL_AUTHORITY_VIOLATION),
            "counterfactual_firewall_v2_reference":
                sum(1 for c in reference
                    if c["counterfactual"]["whole_response_failure"]
                    == lifecycle.NUMERICAL_AUTHORITY_VIOLATION),
        },
    }

    report = {
        "artifact": "V2_COUNTERFACTUAL_REPLAY",
        "replay_version": REPLAY_VERSION,
        "is_a_corrected_v2_verdict": False,
        "frozen_verdict_unchanged": "SONNET46_HYPOTHESIS_V2 = FAIL",
        "bedrock_calls_made": 0,
        "what_this_measures": (
            "what the ALREADY-RECORDED V2 response text would have done under the "
            "corrected V3 contract. It cannot measure what the model would have WRITTEN "
            "under the corrected prompt, gated ontology and evidence-reference channel; "
            "those change the input and only a new run can measure them."),
        "versions": {
            "original": {"schema": schema.SCHEMA_VERSION,
                         "firewall": firewall.FIREWALL_VERSION,
                         "validator": validator.VALIDATOR_VERSION,
                         "compiler": query_plan.QUERY_PLAN_VERSION},
            "counterfactual": {"schema": schema_v2.SCHEMA_VERSION,
                               "contract": condition_contract.CONTRACT_VERSION,
                               "firewall": firewall_v2.FIREWALL_VERSION,
                               "validator": validator_v2.VALIDATOR_VERSION,
                               "availability": availability.AVAILABILITY_VERSION,
                               "compiler": query_plan.QUERY_PLAN_VERSION},
            "compiler_is_unchanged_between_arms": True,
        },
        "compile_rates": compile_rates,
        "failures": failures_removed,
        "firewall": firewall_report,
        "utilization": utilization,
        "per_fixture": per_fixture_util,
    }

    with open(f"{DEST}/counterfactual_replay_report.json", "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, default=str)

    slim = []
    for c in per_call:
        cc = json.loads(json.dumps(c, default=str))
        cc["counterfactual"].pop("accepted_hypotheses", None)
        slim.append(cc)
    with open(f"{DEST}/per_call_original_vs_counterfactual.json", "w") as fh:
        json.dump(slim, fh, indent=1, sort_keys=True, default=str)

    print(json.dumps({k: v for k, v in report.items()
                      if k in ("compile_rates", "failures", "firewall", "utilization")},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
