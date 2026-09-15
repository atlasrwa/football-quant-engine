"""Deterministic scoring + control analysis for SONNET46_HYPOTHESIS_V2.

Zero spend: reads only recorded responses. Uses the FROZEN scorer (evaluation.py),
FROZEN normalizer (normalize.py) and FROZEN thresholds. Makes no scientific choice and
repairs no response.
"""
from __future__ import annotations

import json, os, sys
from collections import defaultdict

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import (capability, evaluation, normalize, query_plan,
                                        validator, firewall, vocabulary)

OUT     = f"{ROOT}/research/hypothesis_engine/out"
RUN_DIR = f"{OUT}/hypothesis_v1_sonnet46_v2"
STATES  = f"{RUN_DIR}/hypothesis_states.jsonl"
PKT     = f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v2.json"
MANP    = f"{OUT}/PRESPEND_MANIFEST_sonnet46_v2.json"

#: The wide-play concession surface the profile control actually perturbs. A paired
#: response counts as MEANINGFULLY sensitive only if the intent/plan delta touches this
#: surface -- arbitrary hypothesis churn is explicitly NOT sensitivity (mandate).
PROFILE_LINKED_METRICS = {"corners_for", "corners_against",
                          "accurate_crosses_for", "accurate_crosses_against"}
PROFILE_LINKED_AXES    = {"corners_against", "accurate_crosses_against"}
PROFILE_LINKED_FAMILIES = {"SET_PIECE_GENERATION", "DEFENSIVE_CONCESSION",
                           "OPPONENT_PROFILE_INTERACTION"}


def manifest_of(packet: dict) -> capability.FixtureCapabilityManifest:
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()),
    )


def load():
    packets = json.load(open(PKT))
    man = json.load(open(MANP))
    rows = [json.loads(l) for l in open(STATES) if l.strip()]
    return packets, man, {r["seq"]: r for r in rows}


def intent_touches_profile(intent: dict) -> bool:
    if intent.get("metric") in PROFILE_LINKED_METRICS:
        return True
    if intent.get("research_family") in PROFILE_LINKED_FAMILIES:
        return True
    for c in intent.get("conditions") or []:
        if c.get("dimension") == "opponent_profile" and c.get("axis") in PROFILE_LINKED_AXES:
            return True
    return False


def main() -> int:
    packets, man, byseq = load()
    specs = {c["seq"]: c for c in man["call_specs"]}

    # ---- per-call deterministic scoring ------------------------------------------------
    scored: dict[int, dict] = {}
    for seq, spec in sorted(specs.items()):
        row = byseq.get(seq)
        if row is None:
            continue
        pkt = packets[spec["packet_key"]]
        fm = manifest_of(pkt)
        raw = row.get("raw_response")
        entry = {"seq": seq, "control": spec["control"],
                 "fixture_id": spec["source_fixture"], "outcome": row["outcome"],
                 "packet_hash": pkt["packet_hash"], "raw": raw}
        if row["outcome"] != "COMPLETED" or raw is None:
            entry["scored"] = None
            scored[seq] = entry
            continue
        score = evaluation.score_response(raw, packet=pkt, manifest=fm)
        vres = validator.validate(raw, packet=pkt, manifest=fm,
                                  expected_packet_hash=pkt["packet_hash"],
                                  expected_fixture_id=pkt["fixture_id"])
        plans = query_plan.compile_set(
            {"fixture_id": pkt["fixture_id"], "hypotheses": vres.accepted_hypotheses},
            cutoff_unix=pkt["information_cutoff_unix"], manifest=fm)
        entry.update(score=score, score_dict=score.to_dict(),
                     validation=vres.to_dict(),
                     accepted_hypotheses=vres.accepted_hypotheses,
                     intents=[i.to_dict() for i in normalize.normalize_set(raw)],
                     intent_keys=sorted(normalize.intent_key_set(raw)),
                     profile=normalize.intent_profile(raw),
                     plans=plans,
                     firewall_violations=[v.__dict__ for v in firewall.scan(raw)])
        scored[seq] = entry

    # control -> fixture -> LIST of entries. `repeatability` is 6 fixtures x 2 calls, so a
    # fixture-keyed scalar would silently discard half the paid calls.
    by_ctrl: dict = defaultdict(lambda: defaultdict(list))
    for e in sorted(scored.values(), key=lambda x: x["seq"]):
        by_ctrl[e["control"]][e["fixture_id"]].append(e)

    ref = {fid: v[0] for fid, v in by_ctrl["reference"].items()}

    def paired(control: str):
        """(fixture, reference_entry, control_entry) for every usable pair."""
        for fid, ces in sorted(by_ctrl.get(control, {}).items()):
            re_ = ref.get(fid)
            for ce in ces:
                if re_ and re_.get("raw") and ce.get("raw"):
                    yield fid, re_, ce

    controls: dict = {}

    # ---- repeatability: intent stability on the byte-identical input -------------------
    # Every sample of the IDENTICAL input: the reference call plus its repeat calls.
    # All pairs among them are same-input comparisons, so all are counted.
    rep = []
    import itertools
    for fid in sorted(by_ctrl.get("repeatability", {})):
        samples = ([ref[fid]] if fid in ref and ref[fid].get("raw") else []) + \
                  [e for e in by_ctrl["repeatability"][fid] if e.get("raw")]
        for a, b in itertools.combinations(samples, 2):
            cmp_ = normalize.compare(a["raw"], b["raw"])
            rep.append({"fixture_id": fid, "seq_a": a["seq"], "seq_b": b["seq"],
                        **cmp_.to_dict()})
    controls["repeatability"] = {
        "n_fixtures": len(by_ctrl.get("repeatability", {})),
        "n_pairs": len(rep),
        "median_jaccard": evaluation._median([r["jaccard"] for r in rep]) if rep else None,
        "n_exactly_equivalent": sum(1 for r in rep if r["equivalent"]),
        "note": "same-input pairs (reference + repeats). This is the NOISE FLOOR against "
                "which identity/irrelevant/venue sensitivity must be read.",
        "per_case": rep,
    }

    # ---- identity_alias: invariance under synthetic aliases ---------------------------
    ida = []
    for fid, a, b in paired("identity_alias"):
        cmp_ = normalize.compare(a["raw"], b["raw"])
        ida.append({"fixture_id": fid, **cmp_.to_dict()})
    identity_jaccards = [r["jaccard"] for r in ida]
    controls["identity_alias"] = {
        "n_pairs": len(ida),
        "median_jaccard": evaluation._median(identity_jaccards) if ida else None,
        "threshold": man["pass_fail_thresholds"]["min_identity_intent_jaccard"],
        "per_case": ida,
    }

    # ---- formation_ablation: formation intent narrows, raw-stat survives --------------
    fab = []
    for fid, a, b in paired("formation_ablation"):
        def fcount(e):
            return sum(1 for i in e["intents"]
                       if any(c.get("dimension") in ("own_formation_family",
                                                     "opponent_formation_family")
                              for c in (i.get("conditions") or []))
                       or i.get("research_family") == "FORMATION_INTERACTION")
        fa, fb = fcount(a), fcount(b)
        non_formation_b = len(b["intents"]) - fb
        fab.append({"fixture_id": fid,
                    "formation_intents_reference": fa,
                    "formation_intents_ablated": fb,
                    "narrowed": fb < fa,
                    "eliminated": fb == 0,
                    "raw_stat_intents_retained_after_ablation": non_formation_b,
                    "raw_stat_reasoning_survived": non_formation_b > 0,
                    "correct_behaviour": fb < fa and non_formation_b > 0})
    controls["formation_ablation"] = {
        "n_pairs": len(fab),
        "n_correct": sum(1 for r in fab if r["correct_behaviour"]),
        "per_case": fab,
    }

    # ---- profile_perturbation: MEANINGFUL, logically-linked sensitivity ----------------
    pp = []
    trips = []
    for fid, a, b in paired("profile_perturbation"):
        cmp_ = normalize.compare(a["raw"], b["raw"])
        delta = list(cmp_.only_a) + list(cmp_.only_b)
        linked = [d for d in delta if intent_touches_profile(d)]
        meaningful = len(linked) > 0
        trips.append(meaningful)
        spec = next(s for s in man["call_specs"]
                    if s["control"] == "profile_perturbation" and s["source_fixture"] == fid)
        pp.append({"fixture_id": fid,
                   "direction": spec.get("transformation_params", {}),
                   "jaccard": cmp_.jaccard,
                   "n_intents_reference": cmp_.n_a, "n_intents_perturbed": cmp_.n_b,
                   "n_intent_delta": len(delta),
                   "n_delta_linked_to_wide_concession": len(linked),
                   "meaningfully_sensitive": meaningful,
                   "linked_delta_intents": linked[:12],
                   "note": "churn alone does NOT count; delta must touch corners/crosses "
                           "concession surface"})
    controls["profile_perturbation"] = {
        "n_pairs": len(pp),
        "trip_rate": (sum(1 for t in trips if t) / len(trips)) if trips else None,
        "threshold": man["pass_fail_thresholds"]["min_evidence_perturbation_trip_rate"],
        "per_case": pp,
    }

    # ---- venue_flip: bounded sensitivity ----------------------------------------------
    vf = []
    for fid, a, b in paired("venue_flip"):
        cmp_ = normalize.compare(a["raw"], b["raw"])
        def vcount(e):
            return sum(1 for i in e["intents"]
                       if any(c.get("dimension") == "venue" for c in (i.get("conditions") or []))
                       or i.get("research_family") == "VENUE_EFFECT")
        vf.append({"fixture_id": fid, "jaccard": cmp_.jaccard,
                   "venue_intents_reference": vcount(a), "venue_intents_flipped": vcount(b),
                   "n_intent_delta": len(cmp_.only_a) + len(cmp_.only_b),
                   "bounded": 0.0 < cmp_.jaccard < 1.0 or cmp_.jaccard == 1.0,
                   "collapsed": cmp_.jaccard == 0.0})
    controls["venue_flip"] = {
        "n_pairs": len(vf),
        "median_jaccard": evaluation._median([r["jaccard"] for r in vf]) if vf else None,
        "n_collapsed": sum(1 for r in vf if r["collapsed"]),
        "per_case": vf,
    }

    # ---- irrelevant_field: scientific-intent invariance --------------------------------
    irr = []
    invariances = []
    for fid, a, b in paired("irrelevant_field"):
        cmp_ = normalize.compare(a["raw"], b["raw"])
        inv = cmp_.equivalent
        invariances.append(inv)
        irr.append({"fixture_id": fid, **cmp_.to_dict(), "invariant": inv})
    controls["irrelevant_field"] = {
        "n_pairs": len(irr),
        "invariance_rate": (sum(1 for i in invariances if i) / len(invariances))
        if invariances else None,
        "median_jaccard": evaluation._median([r["jaccard"] for r in irr]) if irr else None,
        "threshold": man["pass_fail_thresholds"]["min_irrelevant_invariance_rate"],
        "per_case": irr,
    }

    # ---- evidence_starvation: narrowing / abstention / non-invention -------------------
    starv = []
    starved_flags = []
    for fid, ces in sorted(by_ctrl.get("evidence_starvation", {}).items()):
      for ce in ces:
        if not ce.get("raw"):
            continue
        hyps = (ce["raw"] or {}).get("hypotheses", []) or []
        n_abst = sum(1 for h in hyps if h.get("sufficiency") == vocabulary.SUFFICIENCY[1])
        rate = (n_abst / len(hyps)) if hyps else 0.0
        # non-invention: every cited evidence id must exist in the STARVED packet
        pkt = packets[f"evidence_starvation::{fid}"]
        real = {e["id"] for e in pkt["evidence"]}
        cited = {r for h in hyps for r in (h.get("evidence_refs") or [])}
        fabricated = sorted(cited - real)
        abstained = rate >= 0.5
        starved_flags.append(abstained)
        ref_e = ref.get(fid)
        starv.append({"fixture_id": fid, "n_hypotheses": len(hyps),
                      "n_abstentions": n_abst, "abstention_rate": round(rate, 4),
                      "counted_as_abstaining": abstained,
                      "n_intents_starved": len(ce["intents"]),
                      "n_intents_reference": len(ref_e["intents"]) if ref_e and ref_e.get("intents") else None,
                      "narrowed_vs_reference": (len(ce["intents"]) < len(ref_e["intents"]))
                      if ref_e and ref_e.get("intents") else None,
                      "fabricated_evidence_refs": fabricated,
                      "non_invention_clean": not fabricated})
    controls["evidence_starvation"] = {
        "n_cases": len(starv),
        "abstention_rate_on_starved_packets": (
            sum(1 for f in starved_flags if f) / len(starved_flags)) if starved_flags else None,
        "threshold": man["pass_fail_thresholds"]["min_abstention_rate_on_starved_packets"],
        "per_case": starv,
    }

    # ---- unsupported_data_trap: capability awareness ----------------------------------
    trap = []
    TRAP_WORDS = ("injur", "absence", "absent", "unavailab", "suspend", "doubtful",
                  "expected formation", "rumour", "rumor", "lineup", "team news",
                  "starting shape", "chatter")
    for fid, ces in sorted(by_ctrl.get("unsupported_data_trap", {}).items()):
      for ce in ces:
        if not ce.get("raw"):
            continue
        hyps = (ce["raw"] or {}).get("hypotheses", []) or []
        pkt = packets[f"unsupported_data_trap::{fid}"]
        real = {e["id"] for e in pkt["evidence"]}
        cited = {r for h in hyps for r in (h.get("evidence_refs") or [])}
        fabricated = sorted(cited - real)
        blob = json.dumps(ce["raw"]).lower()
        hits = sorted({w for w in TRAP_WORDS if w in blob})
        sc = ce.get("score")
        trap.append({"fixture_id": fid, "n_hypotheses": len(hyps),
                     "fabricated_evidence_refs": fabricated,
                     "trap_language_present": hits,
                     "unavailable_requests_scored": sc.unavailable_requests if sc else None,
                     "took_the_bait": bool(fabricated) or (sc.unavailable_requests > 0 if sc else False),
                     "resisted": not fabricated and (sc.unavailable_requests == 0 if sc else False)})
    controls["unsupported_data_trap"] = {
        "n_cases": len(trap),
        "n_resisted": sum(1 for t in trap if t["resisted"]),
        "n_took_bait": sum(1 for t in trap if t["took_the_bait"]),
        "per_case": trap,
    }

    # ---- preregistered aggregate over the 12 REFERENCE fixtures -----------------------
    ref_scores = [e["score"] for e in (ref[f] for f in sorted(ref)) if e.get("score")]
    report = evaluation.aggregate(
        ref_scores,
        identity_jaccards=identity_jaccards,
        evidence_perturbation_trips=trips,
        irrelevant_perturbation_invariances=invariances,
        starved_abstention_flags=starved_flags,
    )
    rd = report.to_dict()
    rd["repeatability_median_jaccard"] = controls["repeatability"]["median_jaccard"]

    json.dump(controls, open(f"{RUN_DIR}/controls.json", "w"), indent=2, sort_keys=True, default=str)
    json.dump(rd, open(f"{RUN_DIR}/evaluation_report.json", "w"), indent=2, sort_keys=True, default=str)

    # ---- inspectable artifact: raw + validated + normalized + plans + evidence --------
    insp = {}
    for e in scored.values():
        insp[f"seq{e['seq']:02d}::{e['control']}::{e['fixture_id']}"] = {
            "seq": e["seq"], "control": e["control"], "fixture_id": e["fixture_id"],
            "packet_hash": e["packet_hash"], "outcome": e["outcome"],
            "raw_sonnet_output": e.get("raw"),
            "validation": e.get("validation"),
            "validated_hypotheses": e.get("accepted_hypotheses"),
            "normalized_intents": e.get("intents"),
            "compiled_query_plans": e.get("plans"),
            "evidence_refs": sorted({r for h in ((e.get("raw") or {}).get("hypotheses") or [])
                                     for r in (h.get("evidence_refs") or [])}),
            "score": e.get("score_dict"),
        }
    json.dump(insp, open(f"{RUN_DIR}/inspectable_artifact.json", "w"),
              indent=2, sort_keys=True, default=str)

    print(json.dumps({"metrics": rd["metrics"], "gates": rd["gates"],
                      "passed": rd["passed"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
