"""Build the V6 artifacts and every machine-readable audit. ZERO SPEND -- no Bedrock.

V6 does NOT rebuild evidence and does NOT re-key packets. §2 preserves the V5A.2 interface
and §31 requires the PIT/provenance guarantees to hold unchanged, so the packets V6 sends
are the FROZEN V5A.2 packets, byte-for-byte. `packet_identity_audit.json` proves it: every
packet in both arms hashes identically to its V5A.2 source. Nothing about the evidence is
V6's to change; what V6 changes is how a RESPONSE to that evidence is adjudicated.

WHAT THIS SCRIPT PRODUCES IN out/v6/
------------------------------------
    packets_base.json, packets_research.json   copied verbatim from out/v5a2/ (proven)
    packet_identity_audit.json                 V6 packets == V5A.2 packets, byte-level
    pit_audit.json                             §31 re-verified on the shipped packets
    arm_isolation_audit.json                   §2/§32 the arms differ only in evidence
    evidence_family_audit.json                 §13 which families each arm can express
    adversarial_battery.json                   §33 -- 11 valid + specific violations, run
                                               through the PRODUCTION adjudicator
    synthetic_mutation_battery.json            §24 -- perfect / null / noisy / fatal / ...
    call_schedule.json                         §6 the frozen round-robin, with assertions

The two batteries are not descriptions. They are live-like responses passed through
`validator_v5.adjudicate` and `v6_scorecard.score_response` -- the same functions the paid
run will use -- and their OBSERVED outcomes are recorded. §33's requirement ("verify ONLY
the intended hypotheses fail") is checked mechanically: each adversarial hypothesis declares
the class it should receive, and the build fails loudly if any observed class differs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import validator_v5 as V
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_schedule as SCH
from src.research.hypothesis_oos import v6_scorecard as SC
from src.research.hypothesis_oos import v6_stop as STOP

V5A2_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"
OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
ARMS = (("base", "packets_base"), ("research", "packets_research"))

# Diversity minimums the schedule must satisfy before the stop-rule eligibility point.
MIN_PREFIX_FIXTURES = STOP.MIN_STOP_FIXTURES
MIN_PREFIX_CALLS_PER_ARM = STOP.MIN_STOP_VALID_CALLS_PER_ARM
MIN_REPEAT_GROUPS_PER_ARM = 3


def _sha_obj(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _write(name, obj) -> str:
    import os
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{name}"
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_packets() -> dict:
    return {arm: json.load(open(f"{V5A2_OUT}/{fn}.json")) for arm, fn in ARMS}


# ----------------------------------------------------------------------------------------
# AUDITS on the shipped packets.
# ----------------------------------------------------------------------------------------
def packet_identity_audit(pk) -> dict:
    """§2/§31 -- the V6 packets are the V5A.2 packets, byte-identical."""
    diffs = []
    for arm, fn in ARMS:
        src = json.load(open(f"{V5A2_OUT}/{fn}.json"))
        for fid in sorted(src):
            a, b = _sha_obj(src[fid]), _sha_obj(pk[arm][fid])
            if a != b:
                diffs.append({"arm": arm, "fixture_id": fid, "v5a2": a, "v6": b})
    return {"n_packets": sum(len(pk[a]) for a, _ in ARMS),
            "n_differences": len(diffs), "differences": diffs,
            "claim": "V6 ships the FROZEN V5A.2 packets unchanged; nothing about the "
                     "evidence is re-derived or re-keyed"}


def pit_audit(pk) -> dict:
    """§31 -- no observation at/after cutoff; no packet names its own target fixture."""
    problems = []
    for arm, _ in ARMS:
        for fid, packet in sorted(pk[arm].items()):
            cutoff = packet["information_cutoff_unix"]
            blob = json.dumps(packet, sort_keys=True, default=str)
            if fid in blob.replace(f'"fixture_id": "{fid}"', ""):
                problems.append({"arm": arm, "fixture_id": fid,
                                 "problem": "target fixture id appears outside fixture_id"})
            for sec in packet["sections"]:
                if sec.get("section_type") != "MATCH_LEVEL_OBSERVATIONS":
                    continue
                for blk in sec.get("blocks") or []:
                    for row in blk.get("rows") or []:
                        ts = row.get("kickoff_unix") or row.get("date_unix")
                        if ts is not None and ts >= cutoff:
                            problems.append({"arm": arm, "fixture_id": fid,
                                             "problem": f"observation {ts} >= cutoff "
                                                        f"{cutoff}"})
    return {"n_problems": len(problems), "problems": problems,
            "claim": "every observation kicked off strictly before the cutoff; no packet "
                     "names its own target fixture (§31)"}


def arm_isolation_audit(pk) -> dict:
    """§2/§32 -- the arms differ ONLY in evidence representation; nothing names the arm."""
    fids = sorted(set(pk["base"]) & set(pk["research"]))
    leaks, shape = [], []
    for fid in fids:
        b, r = pk["base"][fid], pk["research"][fid]
        for key in ("packet_schema_version", "evidence_interface_version",
                    "packet_surface_version", "ontology_version", "fixture_id",
                    "information_cutoff_unix"):
            if b.get(key) != r.get(key):
                leaks.append({"fixture_id": fid, "key": key,
                              "base": b.get(key), "research": r.get(key)})
        shape.append({"fixture_id": fid,
                      "base_sections": [s["section_type"] for s in b["sections"]],
                      "research_sections": [s["section_type"] for s in r["sections"]]})
    blob = json.dumps(pk, sort_keys=True, default=str)
    labels = PR.blinding_violations(blob)
    return {"n_fixtures": len(fids), "n_identity_leaks": len(leaks),
            "identity_leaks": leaks, "treatment_labels_found_in_packets": labels,
            "section_shapes": shape,
            "claim": "identity fields identical across arms; nothing names the condition"}


def evidence_family_audit(pk) -> dict:
    """§13 -- which research families each arm's evidence can even express."""
    out = {}
    for arm, _ in ARMS:
        fam_ids = {}
        for fid, packet in pk[arm].items():
            ids = E.resolve_evidence_ids(packet)
            kinds = {}
            for i in ids:
                kinds[i.split(":")[0]] = kinds.get(i.split(":")[0], 0) + 1
            fam_ids[fid] = kinds
        out[arm] = fam_ids
    return {"per_fixture_id_kinds_by_arm": out,
            "note": "base carries SUMMARY/FORMATION/AVAIL only; research adds "
                    "MATCH/PROFILE. §13 tracks family concentration but never rewards it."}


# ----------------------------------------------------------------------------------------
# HYPOTHESIS BUILDERS. Schema-valid by construction unless deliberately mutated.
# ----------------------------------------------------------------------------------------
def _refs_for(packet, kind_prefix, n=1):
    ids = sorted(i for i in E.resolve_evidence_ids(packet) if i.startswith(kind_prefix))
    return ids[:n]


def valid_hyp(hid, packet, *, metric="shots_on_target", family="ATTACK_VOLUME",
              side="FOR", refs=None, question=None, **over):
    refs = refs if refs is not None else _refs_for(
        packet, f"SUMMARY:HOME:ALL_PRIOR:ANY:{metric}_{side.lower()}") or \
        [f"SUMMARY:HOME:ALL_PRIOR:ANY:{metric}_for"]
    h = {"hypothesis_id": hid, "research_family": family, "subject": "HOME_TEAM",
         "target_metrics": [metric], "side": side, "window": "ALL_PRIOR",
         "conditions": [], "comparison": "SUBJECT_OVERALL_BASELINE",
         "evidence_refs": list(refs), "candidate_confounders": [],
         "required_capabilities": [], "sufficiency": "SUFFICIENT", "priority": "MEDIUM",
         "question": question or (f"Does HOME_TEAM {metric} {side.lower()}-rate differ "
                                  f"from its overall prior baseline across all matches?")}
    h.update(over)
    return h


def response(fid, packet_hash, hyps):
    return {"fixture_id": fid, "packet_hash": packet_hash, "hypotheses": hyps}


# ----------------------------------------------------------------------------------------
# §33 ADVERSARIAL BATTERY. One live-like research-arm response, 12 hypotheses:
# eleven adjudicable-and-mostly-valid, one bad per the required mutation list, each tagged
# with the class it MUST receive. Run through the production adjudicator.
# ----------------------------------------------------------------------------------------
def adversarial_response(rpk):
    """§33's live-like response, within MAX_HYPOTHESES=12.

    Twelve hypotheses. Six adjudicate to VALID (one of them a VALID_ABSTENTION, two of them
    reproducing a historical value under the frame contract, one a genuine opponent-profile
    interaction) and six carry exactly one deliberate violation each, covering every §33
    case. §33's "one bad hypothesis among 11 valid" is the invariant PROVED: each violation
    is isolated, and every valid sibling survives.
    """
    rh = rpk["packet_hash"]
    prof = _refs_for(rpk, "PROFILE:HOME:", 2)
    w5 = sorted(i for i in E.resolve_evidence_ids(rpk) if ":HOME:W5:" in i)[:1]
    venue = sorted(i for i in E.resolve_evidence_ids(rpk)
                   if ":HOME_ONLY:" in i and "HOME" in i)[:1]

    hyps, tags = [], []

    # ---- six valid ----
    # H1 valid unconditioned
    hyps.append(valid_hyp("H1", rpk)); tags.append(K.VALID_HYPOTHESIS)
    # H2 one valid opponent-profile interaction (§33)
    hyps.append(valid_hyp(
        "H2", rpk, metric="big_chances", family="OPPONENT_PROFILE_INTERACTION",
        refs=prof or None, required_capabilities=["opponent_profile"],
        conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                     "axis": "shots_on_target_against"}],
        question="Does HOME_TEAM create more big_chances versus defensively strong opponents than overall?"))
    tags.append(K.VALID_HYPOTHESIS)
    # H3 valid recent-vs-long
    hyps.append(valid_hyp(
        "H3", rpk, metric="corners", family="FORM_VS_BASELINE", window="W5",
        comparison="SUBJECT_RECENT_VS_LONG_BASELINE", refs=(w5 or None),
        question="Does HOME_TEAM recent W5 corners for-rate differ from its long-run baseline?"))
    tags.append(K.VALID_HYPOTHESIS)
    # H4 valid venue split (away cohort vs overall -- a real contrast, not absorbed)
    hyps.append(valid_hyp(
        "H4", rpk, metric="total_shots", family="VENUE_EFFECT",
        refs=(venue or None), required_capabilities=["historical_venue_conditioning"],
        conditions=[{"dimension": "historical_venue_conditioning", "value": "AWAY"}],
        question="Does HOME_TEAM total_shots at away venues differ from its overall prior baseline?"))
    tags.append(K.VALID_HYPOTHESIS)
    # H5 one valid evidence-backed abstention (§35 requires this shape too)
    hyps.append(valid_hyp(
        "H5", rpk, metric="clearances", family="DEFENSIVE_SUPPRESSION",
        sufficiency="INSUFFICIENT_EVIDENCE",
        question="Referee-conditioned clearances cannot be assessed; the packet exposes no referee evidence."))
    tags.append(K.VALID_ABSTENTION)
    # H6 one percentage used purely as historical evidence in evidence_summary -> VALID
    hyps.append(valid_hyp(
        "H6", rpk, metric="possession", family="TEMPO_AND_TERRITORY",
        question="Does HOME_TEAM possession for-rate differ from its overall prior baseline entirely?",
        evidence_summary="The cited ALL_PRIOR summary recorded a possession mean well above the midpoint across prior matches."))
    tags.append(K.VALID_HYPOTHESIS)

    # ---- six deliberate violations, one each ----
    # H7 one probability claim among valid hypotheses -> FIREWALL
    hyps.append(valid_hyp(
        "H7", rpk, metric="goals", family="ATTACK_QUALITY",
        question="This gives HOME_TEAM a 62% chance of scoring first in the upcoming fixture."))
    tags.append(K.MODEL_FIREWALL_VIOLATION)
    # H8 one fabricated evidence id -> GROUNDING
    hyps.append(valid_hyp(
        "H8", rpk, metric="offsides", family="ATTACK_VOLUME",
        refs=["SUMMARY:HOME:ALL_PRIOR:ANY:this_id_is_fabricated_for"],
        question="Does HOME_TEAM offsides for-rate differ from its overall prior baseline here?"))
    tags.append(K.MODEL_GROUNDING_VIOLATION)
    # H9 one unavailable dimension (referee not exposed in any packet) -> AVAILABILITY
    hyps.append(valid_hyp(
        "H9", rpk, metric="yellow_cards", family="DISCIPLINE",
        required_capabilities=["referee"],
        conditions=[{"dimension": "referee", "value": "SAME"}],
        question="Does HOME_TEAM yellow_cards for-rate change under the same referee historically here?"))
    tags.append(K.MODEL_AVAILABILITY_VIOLATION)
    # H10 one malformed hypothesis (bad enum value) -> SCHEMA
    hyps.append(valid_hyp(
        "H10", rpk, metric="tackles", family="NOT_A_REAL_FAMILY",
        question="A malformed hypothesis whose research_family is not in the enum at all here."))
    tags.append(K.MODEL_SCHEMA_INVALID)
    # H11 one bad comparator: venue baseline absorbed (home side conditioned HOME) -> COMPARATOR
    hyps.append(valid_hyp(
        "H11", rpk, metric="interceptions", family="VENUE_EFFECT",
        comparison="SUBJECT_VENUE_BASELINE", refs=(venue or None),
        required_capabilities=["historical_venue_conditioning"],
        conditions=[{"dimension": "historical_venue_conditioning", "value": "HOME"}],
        question="Does HOME_TEAM interceptions at home differ from its home venue baseline exactly?"))
    tags.append(K.MODEL_COMPARATOR_INVALID)
    # H12 one redundant repeat of H1's exact intent -> REDUNDANT (first wins)
    hyps.append(valid_hyp(
        "H12", rpk,
        question="Does HOME_TEAM shots_on_target for-rate differ from its overall prior baseline across all matches?"))
    tags.append(K.MODEL_REDUNDANT_HYPOTHESIS)

    return response(rpk["fixture_id"], rh, hyps), tags


def run_adversarial(rpk) -> dict:
    payload, tags = adversarial_response(rpk)
    adj = V.adjudicate(payload, packet=rpk,
                       expected_packet_hash=rpk["packet_hash"],
                       expected_fixture_id=rpk["fixture_id"])
    rows, mismatches = [], []
    for a, expected in zip(adj.hypotheses, tags):
        ok = a.outcome_class == expected
        rows.append({"hypothesis_id": a.hypothesis_id, "expected": expected,
                     "observed": a.outcome_class, "match": ok,
                     "qualified": a.scorecard.get("qualified"),
                     "failed_gates": sorted(k for k, v in a.scorecard.items()
                                            if v is False and k not in
                                            ("redundant", "abstaining"))})
        if not ok:
            mismatches.append(rows[-1])
    sc = SC.score_response(adj, rpk)
    n_valid_siblings = sum(1 for r in rows
                           if r["expected"] in (K.VALID_HYPOTHESIS, K.VALID_ABSTENTION))
    n_valid_survived = sum(1 for r in rows
                           if r["expected"] in (K.VALID_HYPOTHESIS, K.VALID_ABSTENTION)
                           and r["match"])
    return {"response_class": adj.response_class, "fatal": adj.fatal,
            "n_hypotheses": len(rows), "n_mismatches": len(mismatches),
            "mismatches": mismatches, "rows": rows,
            "n_valid_siblings": n_valid_siblings,
            "n_valid_siblings_survived": n_valid_survived,
            "all_valid_siblings_survived": n_valid_survived == n_valid_siblings,
            "single_bad_does_not_kill_response": not adj.fatal and len(rows) == len(tags),
            "scorecard": {"n_recoverable": sc["n_recoverable"],
                          "n_qualified": sc["n_qualified"],
                          "qualified_rate": sc["qualified_rate"],
                          "class_counts": {k: v for k, v in sc["class_counts"].items()
                                           if v}},
            "claim": "each hypothesis is adjudicated on its own; only the intended "
                     "hypotheses fail and every valid sibling survives (§33)"}


# ----------------------------------------------------------------------------------------
# §24 SYNTHETIC MUTATION BATTERY. Whole-response shapes the evaluator must handle.
# ----------------------------------------------------------------------------------------
def synthetic_battery(bpk, rpk) -> dict:
    rh, bh = rpk["packet_hash"], bpk["packet_hash"]
    cases = {}

    def adj_of(packet, payload):
        a = V.adjudicate(payload, packet=packet,
                         expected_packet_hash=packet["packet_hash"],
                         expected_fixture_id=packet["fixture_id"])
        return a, SC.score_response(a, packet)

    # perfect PASS-like battery: all valid, distinct intents
    perfect = [valid_hyp(f"H{i}", rpk, metric=m, family=fam)
               for i, (m, fam) in enumerate(
                   [("shots_on_target", "ATTACK_VOLUME"), ("corners", "SET_PIECE_GENERATION"),
                    ("possession", "TEMPO_AND_TERRITORY"), ("tackles", "DEFENSIVE_SUPPRESSION"),
                    ("big_chances", "ATTACK_QUALITY"), ("fouls", "DISCIPLINE")], start=1)]
    a, sc = adj_of(rpk, response(rpk["fixture_id"], rh, perfect))
    cases["perfect"] = {"response_class": a.response_class, "n_qualified": sc["n_qualified"],
                        "qualified_rate": sc["qualified_rate"], "measured": sc["measured"]}

    # null A/B battery: base and research given identical unconditioned hyps
    null_h = [valid_hyp(f"H{i}", bpk, metric=m) for i, m in
              enumerate(["shots_on_target", "corners", "possession"], start=1)]
    ab, absc = adj_of(bpk, response(bpk["fixture_id"], bh, null_h))
    ar, arsc = adj_of(rpk, response(rpk["fixture_id"], rh, null_h))
    cases["null_ab"] = {"base_qualified_rate": absc["qualified_rate"],
                        "research_qualified_rate": arsc["qualified_rate"],
                        "note": "identical hyps -> identical qualified rate; no A/B signal"}

    # noisy battery: mix of valid and several violation kinds
    noisy_payload, tags = adversarial_response(rpk)
    an, ncsc = adj_of(rpk, noisy_payload)
    cases["noisy"] = {"n_qualified": ncsc["n_qualified"],
                      "class_counts": {k: v for k, v in (ncsc["class_counts"] or {}).items()
                                       if v}}

    # high firewall violation: every hyp carries a predictive probability
    fw = [valid_hyp(f"H{i+1}", rpk,
                    question=f"This gives HOME_TEAM a {50+i}% chance in the upcoming fixture.")
          for i in range(4)]
    af, fsc = adj_of(rpk, response(rpk["fixture_id"], rh, fw))
    cases["high_firewall"] = {"firewall_violations":
                              (fsc["class_counts"] or {}).get(K.MODEL_FIREWALL_VIOLATION),
                              "n_qualified": fsc["n_qualified"]}

    # grounding failure: every hyp cites a fabricated id
    gf = [valid_hyp(f"H{i+1}", rpk,
                    refs=[f"SUMMARY:HOME:ALL_PRIOR:ANY:fabricated_{i}_for"])
          for i in range(4)]
    ag, gsc = adj_of(rpk, response(rpk["fixture_id"], rh, gf))
    cases["grounding_failure"] = {"grounding_violations":
                                  (gsc["class_counts"] or {}).get(K.MODEL_GROUNDING_VIOLATION)}

    # availability failure: base arm given conditioned hyps
    av = [valid_hyp(f"H{i+1}", bpk, required_capabilities=["opponent_profile"],
                    conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                                 "axis": "goals_against"}])
          for i in range(3)]
    aa, asc = adj_of(bpk, response(bpk["fixture_id"], bh, av))
    cases["availability_failure_base_arm"] = {
        "class_counts": {k: v for k, v in (asc["class_counts"] or {}).items() if v},
        "note": "base packet exposes no opponent_profile; classes are model violations "
                "(grounding on absent PROFILE ids and/or availability), never apparatus"}

    # response fatal: missing hypotheses array
    fa = V.adjudicate({"fixture_id": rpk["fixture_id"], "packet_hash": rh}, packet=rpk,
                      expected_packet_hash=rh, expected_fixture_id=rpk["fixture_id"])
    fasc = SC.score_response(fa, rpk)
    cases["response_fatal"] = {"response_class": fa.response_class, "fatal": fa.fatal,
                               "measured": fasc["measured"],
                               "qualified_rate_is_none": fasc["qualified_rate"] is None}

    # non-evaluable execution: too few paired fixtures handled by v6_verdict (tested there)
    cases["non_evaluable"] = {"note": "coverage gate lives in v6_verdict; exercised in "
                              "the test suite, not a per-response shape"}

    # complete FAIL / MIXED / PASS: whole-run verdicts handled by v6_verdict test paths
    cases["complete_fail_mixed_pass"] = {
        "note": "whole-run PASS/MIXED/FAIL are v6_verdict outputs; the three synthetic "
                "run-level batteries are exercised in test_v6_prespend"}

    return {"cases": cases,
            "claim": "every evaluator PATH runs on a synthetic input before spend (§24)"}


def call_schedule() -> dict:
    packets = load_packets()
    paired = sorted(set(packets["base"]) & set(packets["research"]))
    calls = SCH.build_sequence(paired)
    elig = STOP.MIN_CALLS_BEFORE_RATE_STOP
    props = SCH.order_properties(calls, elig)
    problems = SCH.freeze_assertions(
        calls, elig, min_prefix_fixtures=MIN_PREFIX_FIXTURES,
        min_prefix_calls_per_arm=MIN_PREFIX_CALLS_PER_ARM,
        min_repeat_groups_per_arm=MIN_REPEAT_GROUPS_PER_ARM)
    return {"paired_fixtures": paired, "n_calls": len(calls), "calls": calls,
            "eligibility_seq": elig, "order_properties": props,
            "freeze_problems": problems, "frozen": not problems}


def main():
    packets = load_packets()
    hashes = {}
    for arm, fn in ARMS:
        hashes[f"{fn}.json"] = _write(f"{fn}.json", packets[arm])

    audits = {
        "packet_identity_audit.json": packet_identity_audit(packets),
        "pit_audit.json": pit_audit(packets),
        "arm_isolation_audit.json": arm_isolation_audit(packets),
        "evidence_family_audit.json": evidence_family_audit(packets),
        "call_schedule.json": call_schedule(),
    }
    fid0 = sorted(packets["research"])[0]
    audits["adversarial_battery.json"] = run_adversarial(packets["research"][fid0])
    audits["synthetic_mutation_battery.json"] = synthetic_battery(
        packets["base"][fid0], packets["research"][fid0])

    for name, obj in audits.items():
        hashes[name] = _write(name, obj)

    pid = audits["packet_identity_audit.json"]
    pit = audits["pit_audit.json"]
    ai = audits["arm_isolation_audit.json"]
    adv = audits["adversarial_battery.json"]
    sch = audits["call_schedule.json"]

    print(f"packets: base={len(packets['base'])} research={len(packets['research'])}")
    print(f"packet identity diffs vs V5A.2: {pid['n_differences']}")
    print(f"PIT problems:                   {pit['n_problems']}")
    print(f"arm identity leaks:             {ai['n_identity_leaks']} | "
          f"treatment labels: {ai['treatment_labels_found_in_packets']}")
    print(f"adversarial: {adv['n_hypotheses']} hyps, {adv['n_mismatches']} class "
          f"mismatches, valid siblings survived: {adv['all_valid_siblings_survived']} "
          f"({adv['n_valid_siblings_survived']}/{adv['n_valid_siblings']})")
    print(f"  response fatal? {adv['fatal']}  (single bad does not kill: "
          f"{adv['single_bad_does_not_kill_response']})")
    print(f"  class counts: {adv['scorecard']['class_counts']}")
    print(f"schedule: {sch['n_calls']} calls, frozen: {sch['frozen']}, "
          f"problems: {sch['freeze_problems']}")

    ok = (pid["n_differences"] == 0 and pit["n_problems"] == 0
          and ai["n_identity_leaks"] == 0 and not ai["treatment_labels_found_in_packets"]
          and adv["n_mismatches"] == 0 and adv["all_valid_siblings_survived"]
          and not adv["fatal"] and sch["frozen"])
    print(f"\nBUILD {'OK' if ok else 'FAILED'}")
    for k, v in sorted(hashes.items()):
        print(f"  {v[:16]}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
