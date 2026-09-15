"""Score the executed SONNET46_HYPOTHESIS_V3 battery. ZERO SPEND.

Reads only recorded responses. Every gate, denominator, classifier and threshold is the
FROZEN one: this module computes, it does not decide. No response is repaired, no threshold
is touched, and the raw model output is never replaced by normalized output.

Discipline is measured on ALL completed calls.
Depth and restraint are measured on the 12 REFERENCE responses only.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from collections import Counter

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import (availability, capability, condition_contract,
                                        controls_v3, evaluation_v2, firewall_v2,
                                        lifecycle, multicondition, normalize, query_plan,
                                        validator_v2, verdict_v3)

OUT = f"{ROOT}/research/hypothesis_engine/out"
RUN_DIR = f"{OUT}/hypothesis_v3_sonnet46"
MAN = f"{OUT}/PRESPEND_MANIFEST_sonnet46_v3.json"
PKT = f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v3.json"
STATES = f"{RUN_DIR}/hypothesis_states.jsonl"


def manifest_of(packet):
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))


def score_all():
    man = json.load(open(MAN))
    packets = json.load(open(PKT))
    rows = [json.loads(l) for l in open(STATES) if l.strip()]
    specs = {c["seq"]: c for c in man["call_specs"]}

    scored = {}
    for r in sorted(rows, key=lambda r: r["seq"]):
        seq = r["seq"]
        packet = packets[r["packet_key"]]
        fm = manifest_of(packet)
        ont = availability.build_ontology(packet, fm)
        entry = {"seq": seq, "control": r["control"], "fixture_id": r["fixture_id"],
                 "packet_key": r["packet_key"], "outcome": r["outcome"],
                 "ontology": ont, "packet": packet, "manifest": fm,
                 "raw": r.get("raw_response")}

        if r["outcome"] == "INFRASTRUCTURE_CENSORED":
            entry.update(completed=False)
            scored[seq] = entry
            continue

        entry["completed"] = True
        res = validator_v2.validate(
            r.get("raw_response"), packet=packet, manifest=fm,
            expected_packet_hash=packet.get("packet_hash"),
            expected_fixture_id=packet.get("fixture_id"), ontology=ont)
        findings = res.firewall_findings
        entry["validation"] = res
        entry["whole_response_failure"] = res.failure
        entry["firewall_classes"] = firewall_v2.classification_counts(findings)
        entry["firewall_blocking"] = firewall_v2.blocking(findings)
        entry["n_hypotheses"] = len(((res.canonical_payload or {}) or {})
                                    .get("hypotheses") or [])
        entry["n_accepted"] = res.n_accepted
        entry["accepted"] = res.accepted_hypotheses
        entry["abstention_quality"] = evaluation_v2.abstention_quality(
            res.canonical_payload or {})

        # fabricated evidence refs (D5)
        real_ids = {e.get("id") for e in (packet.get("evidence") or [])}
        cited = {ref for h in ((res.canonical_payload or {}).get("hypotheses") or [])
                 for ref in (h.get("evidence_refs") or [])}
        entry["fabricated_refs"] = sorted(cited - real_ids)

        # unavailable capability requests (D6)
        entry["unavailable_requests"] = sum(
            1 for h in ((res.canonical_payload or {}).get("hypotheses") or [])
            for c in (h.get("required_capabilities") or [])
            if not capability.is_supported_context_source(c))

        if res.accepted:
            compiled = query_plan.compile_set(
                {"fixture_id": packet["fixture_id"],
                 "hypotheses": res.accepted_hypotheses},
                cutoff_unix=packet.get("information_cutoff_unix", 0), manifest=fm)
            entry["compiled"] = compiled
            entry["n_compilable"] = compiled["n_fully_compilable"]
            entry["intents"] = [i.to_dict() for i in normalize.normalize_set(
                {"hypotheses": res.accepted_hypotheses})]
            entry["profile"] = normalize.intent_profile(res.canonical_payload)
            entry["multicondition"] = multicondition.classify_set(
                res.accepted_hypotheses, ont, compiled=compiled["results"])
            entry["restraint"] = availability.restraint_profile(
                {"hypotheses": res.accepted_hypotheses}, ont)
        else:
            entry.update(compiled=None, n_compilable=0, intents=[], profile=None,
                         multicondition=None, restraint=None)
        scored[seq] = entry
    return man, packets, specs, scored


def main() -> int:
    man, packets, specs, scored = score_all()
    completed = [e for e in scored.values() if e.get("completed")]
    n_completed = len(completed)
    ref = [e for e in completed if e["control"] == "reference"]

    # ================= DISCIPLINE (all completed calls) =============================
    n_schema_invalid = sum(1 for e in completed
                           if e["whole_response_failure"] == lifecycle.SCHEMA_INVALID)
    n_whole_ok = sum(1 for e in completed if e["whole_response_failure"] is None)
    total_h = sum(e["n_hypotheses"] for e in completed)
    total_acc = sum(e["n_accepted"] for e in completed)
    total_comp = sum(e["n_compilable"] for e in completed)
    fw = Counter()
    for e in completed:
        fw.update(e["firewall_classes"])
    n_blocking = sum(len(e["firewall_blocking"]) for e in completed)
    n_grade = sum(1 for e in completed for v in e["firewall_blocking"]
                  if v.layer == "GRADE")
    n_fabricated = sum(len(e["fabricated_refs"]) for e in completed)
    n_unavail = sum(e["unavailable_requests"] for e in completed)

    # ---- paired controls ------------------------------------------------------------
    def intents_of(e):
        return e.get("intents") or []

    def payload_of(e):
        return {"hypotheses": e.get("accepted") or []}

    by_ctrl_fix = {}
    for e in completed:
        by_ctrl_fix.setdefault((e["control"], e["fixture_id"]), []).append(e)
    ref_by_fix = {e["fixture_id"]: e for e in ref}

    # repeatability floor: all same-input pairs (reference + its repeats)
    rep_pairs = []
    rep_fixtures = sorted({e["fixture_id"] for e in completed
                           if e["control"] == "repeatability"})
    for fid in rep_fixtures:
        samples = ([ref_by_fix[fid]] if fid in ref_by_fix else []) + \
            by_ctrl_fix.get(("repeatability", fid), [])
        for a, b in itertools.combinations(samples, 2):
            cmp_ = normalize.compare(payload_of(a), payload_of(b))
            rep_pairs.append({"fixture_id": fid, "seq_a": a["seq"], "seq_b": b["seq"],
                              **cmp_.to_dict()})
    rep_floor = evaluation_v2.evaluation._median([p["jaccard"] for p in rep_pairs]) \
        if rep_pairs else None

    def paired(control):
        out = []
        for e in completed:
            if e["control"] != control:
                continue
            r = ref_by_fix.get(e["fixture_id"])
            if r is None:
                continue
            out.append((r, e))
        return out

    ident = [{"fixture_id": e["fixture_id"],
              **normalize.compare(payload_of(r), payload_of(e)).to_dict()}
             for r, e in paired("identity_alias")]
    irrel = [{"fixture_id": e["fixture_id"],
              **normalize.compare(payload_of(r), payload_of(e)).to_dict()}
             for r, e in paired("irrelevant_field")]

    # profile-axis perturbation: FROZEN surface-sensitivity rule
    axis_rows = []
    for r, e in paired("profile_axis_perturbation"):
        sens = controls_v3.surface_sensitivity(intents_of(r), intents_of(e))
        resp = controls_v3.axis_selection_responded(intents_of(r), intents_of(e))
        cmp_ = normalize.compare(payload_of(r), payload_of(e))
        axis_rows.append({
            "fixture_id": e["fixture_id"], "seq_ref": r["seq"], "seq_pert": e["seq"],
            "direction": specs[e["seq"]]["transformation_params"]["direction"],
            "surface_sensitive": sens,
            "axis_selection_responded": resp,
            "jaccard": cmp_.jaccard,
            "ref_profile_axes": sorted(controls_v3.profile_axes_used(intents_of(r))),
            "pert_profile_axes": sorted(controls_v3.profile_axes_used(intents_of(e))),
        })

    # availability ablation
    abl_rows = []
    for r, e in paired("availability_ablation"):
        ref_uses = any(c.get("dimension") == "opponent_profile"
                       for i in intents_of(r) for c in (i.get("conditions") or []))
        gone = controls_v3.ablated_dimension_disappeared(intents_of(e))
        n_cond_on_withheld = (e["restraint"] or {}).get(
            "conditions_on_withheld_dimensions", 0)
        abl_rows.append({
            "fixture_id": e["fixture_id"], "seq_ref": r["seq"], "seq_abl": e["seq"],
            "reference_used_profile": ref_uses,
            "ablated_has_no_profile_condition": gone,
            "conditions_on_withheld_dimensions": n_cond_on_withheld,
            "n_intents_ref": len(intents_of(r)), "n_intents_abl": len(intents_of(e)),
        })
    abl_den = [a for a in abl_rows if a["reference_used_profile"]]
    disappearance = ({"n": len(abl_den),
                      "rate": round(sum(1 for a in abl_den
                                        if a["ablated_has_no_profile_condition"])
                                    / len(abl_den), 4)}
                     if len(abl_den) >= 3 else
                     {"n": len(abl_den), "rate": None, "status": "INSUFFICIENT_N",
                      "note": ("frozen rule: a denominator below 3 reports INSUFFICIENT_N "
                               "rather than a rate; this denominator is controlled by the "
                               "model's own reference-arm behaviour, so it cannot be a "
                               "hard gate")})

    starved = [e for e in completed if e["control"] == "evidence_starvation"]
    trap = [e for e in completed if e["control"] == "unsupported_data_trap"]
    n_trap_bad = sum(1 for e in trap
                     if e["fabricated_refs"] or e["unavailable_requests"])

    # ================= DEPTH + RESTRAINT (reference arm only) ========================
    ref_ok = [e for e in ref if e["whole_response_failure"] is None]
    ref_acc = sum(e["n_accepted"] for e in ref_ok)
    ref_intents = [i for e in ref_ok for i in intents_of(e)]
    n_meaningful = sum(e["multicondition"]["n_meaningful_multi_condition"]
                       for e in ref_ok)
    leg_dist = Counter()
    families = set()
    for e in ref_ok:
        for k, v in e["multicondition"]["restricting_leg_count_distribution"].items():
            leg_dist[int(k)] += v
        for f in e["multicondition"]["interaction_families"]:
            families.add(tuple(f))

    n_beyond_venue = sum(1 for i in ref_intents
                         if any(c["dimension"] != "venue"
                                for c in (i.get("conditions") or [])))
    n_venue_only = sum(1 for i in ref_intents
                       if i.get("conditions")
                       and all(c["dimension"] == "venue"
                               for c in i["conditions"]))
    comparisons = Counter(i["comparison"] for i in ref_intents)
    entropy = verdict_v3.entropy_bits(comparisons)

    prof_elig = [e for e in ref_ok if e["ontology"].is_expectable("opponent_profile")]
    prof_used = [e for e in prof_elig
                 if any(c.get("dimension") == "opponent_profile"
                        for i in intents_of(e) for c in (i.get("conditions") or []))]
    form_elig = [e for e in ref_ok if e["ontology"].is_expectable("own_formation_family")]
    form_used = [e for e in form_elig
                 if any(c.get("dimension") in ("own_formation_family",
                                               "opponent_formation_family")
                        for i in intents_of(e) for c in (i.get("conditions") or []))]

    ref_conditions = sum((e["restraint"] or {}).get("n_conditions", 0) for e in ref_ok)
    ref_any_pad = sum((e["restraint"] or {}).get("any_padding_conditions", 0)
                      for e in ref_ok)
    ref_withheld = sum((e["restraint"] or {}).get(
        "conditions_on_withheld_dimensions", 0) for e in ref_ok)
    all_withheld = sum((e["restraint"] or {}).get(
        "conditions_on_withheld_dimensions", 0) for e in completed if e["restraint"])

    dim_usage = Counter()
    for i in ref_intents:
        for c in (i.get("conditions") or []):
            dim_usage[c["dimension"]] += 1

    # ================= MEASUREMENTS -> FROZEN VERDICT ================================
    med = evaluation_v2.evaluation._median
    M = {
        "D1_schema_validity": {"value": (n_completed - n_schema_invalid) / n_completed
                               if n_completed else None, "n": n_completed},
        "D2_whole_response_validity": {"value": n_whole_ok / n_completed
                                       if n_completed else None, "n": n_completed},
        "D3_query_compilability": {"value": total_comp / total_acc if total_acc else None,
                                   "n": total_acc},
        "D4_evidence_grounding": {"value": total_acc / total_h if total_h else None,
                                  "n": total_h},
        "D5_no_fabricated_evidence": {"value": float(n_fabricated), "n": n_completed},
        "D6_capability_awareness": {"value": n_unavail / total_h if total_h else None,
                                    "n": total_h},
        "D7_numerical_authority": {"value": float(n_blocking), "n": n_completed},
        "D8_no_latent_grading": {"value": float(n_grade), "n": n_completed},
        "D9_no_leakage": {"value": float(
            man["request_leakage_audit"]["total_findings"]), "n": n_completed},
        "D10_non_redundancy": {"value": med([e["profile"]["redundancy_rate"]
                                             for e in ref_ok if e["profile"]]),
                               "n": len(ref_ok)},
        "D11_metric_richness": {"value": med([e["profile"]["metric_richness"]
                                              for e in ref_ok if e["profile"]]),
                                "n": len(ref_ok)},
        "D12_identity_invariance_relative": {
            "value": (evaluation_v2.relative_invariance(
                med([r["jaccard"] for r in ident]) if ident else None,
                rep_floor)["ratio"]), "n": len(ident)},
        "D13_irrelevant_invariance_relative": {
            "value": (evaluation_v2.relative_invariance(
                med([r["jaccard"] for r in irrel]) if irrel else None,
                rep_floor)["ratio"]), "n": len(irrel)},
        "D14_evidence_sensitivity": {
            "value": (sum(1 for a in axis_rows if a["surface_sensitive"]) / len(axis_rows)
                      if axis_rows else None), "n": len(axis_rows)},
        "R1_no_withheld_dimension_conditions": {"value": float(all_withheld),
                                                "n": n_completed},
        "R2_gratuitous_conditions": {
            "value": ((ref_any_pad + ref_withheld) / ref_conditions
                      if ref_conditions else None), "n": ref_conditions},
        "R3_any_padding": {"value": (ref_any_pad / ref_conditions
                                     if ref_conditions else None), "n": ref_conditions},
        "R4_unsupported_data_trap": {"value": float(n_trap_bad), "n": len(trap)},
        "R5_abstention_on_starved_packets": {
            "value": (sum(1 for e in starved
                          if evaluation_v2.abstained(e["validation"].canonical_payload
                                                     or {})) / len(starved)
                      if starved else None), "n": len(starved)},
        "P1_meaningful_multi_condition_rate": {
            "value": n_meaningful / ref_acc if ref_acc else None, "n": ref_acc},
        "P2_beyond_venue_condition_rate": {
            "value": (n_beyond_venue / len(ref_intents) if ref_intents else None),
            "n": len(ref_intents)},
        "P3_opponent_profile_fixture_utilization": {
            "value": (len(prof_used) / len(prof_elig) if prof_elig else None),
            "n": len(prof_elig)},
        "P4_comparison_entropy": {"value": entropy, "n": len(ref_intents)},
    }

    ledger = json.load(open(f"{RUN_DIR}/execution_ledger.json"))
    report = verdict_v3.compute(M, stop_triggered=ledger.get("stop_rule_triggered", False))

    reported_only = {
        "condition_count_distribution": {str(k): leg_dist[k] for k in sorted(leg_dist)},
        "interaction_families": [list(f) for f in sorted(families)],
        "n_distinct_interaction_families": len(families),
        "venue_only_intent_rate": (round(n_venue_only / len(ref_intents), 4)
                                   if ref_intents else None),
        "overall_baseline_comparison_rate": (
            round(comparisons.get("SUBJECT_OVERALL_BASELINE", 0) / len(ref_intents), 4)
            if ref_intents else None),
        "comparison_mix": dict(comparisons),
        "condition_dimension_usage": dict(dim_usage),
        "formation_utilization": {
            "n_eligible_fixtures": len(form_elig), "n_using": len(form_used),
            "rate": (round(len(form_used) / len(form_elig), 4) if form_elig else None),
            "caveat": ("measured, NOT controlled, at N=3. No formation claim may be made "
                       "in either direction at this N."),
        },
        "repeatability_floor_median_jaccard": rep_floor,
        "repeatability_pairs": rep_pairs,
        "identity_alias_pairs": ident,
        "irrelevant_field_pairs": irrel,
        "profile_axis_perturbation": axis_rows,
        "availability_ablation": abl_rows,
        "profile_disappearance_rate": disappearance,
        "firewall_class_counts": dict(fw),
        "abstention_per_starved_call": [
            {"fixture_id": e["fixture_id"], "n_hypotheses": e["n_hypotheses"],
             "abstention_quality": e["abstention_quality"]} for e in starved],
    }
    report.reported_only = reported_only

    out = {
        "experiment_id": man["experiment_id"],
        "manifest_hash": man["manifest_hash"],
        "n_completed_calls": n_completed,
        "n_infrastructure_censored": len(scored) - n_completed,
        "measurements": M,
        "verdict": report.to_dict(),
    }
    with open(f"{RUN_DIR}/evaluation_report.json", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    with open(f"{RUN_DIR}/verdict.json", "w") as fh:
        json.dump(report.to_dict(), fh, indent=1, sort_keys=True, default=str)

    print(f"completed={n_completed}  schema_invalid={n_schema_invalid}  "
          f"accepted={total_acc}/{total_h}  compilable={total_comp}")
    for fam in ("discipline", "restraint", "depth"):
        for r in report.to_dict()[fam]:
            mark = "PASS" if r["met"] else "FAIL"
            print(f"  [{mark}] {r['key']:<42} value={r['value']} "
                  f"{r['direction']} {r['threshold']}  n={r['n']} {r['reason']}")
    print(f"\ndepth criteria met: {report.depth_met}/4 -> {report.depth_outcome}")
    print(f"VERDICT: {report.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
