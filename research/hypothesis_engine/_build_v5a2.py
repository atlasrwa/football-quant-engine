"""Build the V5A.2 packets and every machine-readable audit. ZERO SPEND.

The evidence is NOT rebuilt from the corpus. It is taken from the FROZEN V5A.1 packets and
re-surfaced (task S2), so "the evidence is identical" is a provable byte-level claim rather
than a promise: `evidence_identity_audit.json` compares every non-availability section of
every packet in both arms and must find zero differences.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_packet as P2
from src.research.hypothesis_oos import v5a2_prompt as PR
from src.research.hypothesis_oos import v5a2_translate as TR

V5A1_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a1"
OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"
ARMS = (("base", "packets_base"), ("research", "packets_research"))


def _sha_obj(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _write(name, obj) -> str:
    path = f"{OUT}/{name}"
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _sections_except_availability(pk) -> list:
    return [s for s in pk.get("sections") or []
            if s.get("section_type") != "AVAILABILITY_MAP"]


def build():
    v1 = {arm: json.load(open(f"{V5A1_OUT}/{fn}.json")) for arm, fn in ARMS}
    v2 = {arm: {fid: P2.upgrade_packet(pk) for fid, pk in v1[arm].items()}
          for arm, _ in ARMS}
    return v1, v2


def evidence_identity_audit(v1, v2) -> dict:
    """Task S2 -- prove the evidence is byte-identical to V5A.1's."""
    diffs = []
    for arm, _ in ARMS:
        for fid in sorted(v1[arm]):
            a = _sha_obj(_sections_except_availability(v1[arm][fid]))
            b = _sha_obj(_sections_except_availability(v2[arm][fid]))
            if a != b:
                diffs.append({"arm": arm, "fixture_id": fid,
                              "v5a1_sha": a, "v5a2_sha": b})
    return {"n_packets": sum(len(v1[a]) for a, _ in ARMS),
            "n_evidence_differences": len(diffs),
            "differences": diffs,
            "claim": "every section except AVAILABILITY_MAP is byte-identical to the "
                     "frozen V5A.1 packet it was derived from"}


def roundtrip_audit(v2) -> dict:
    """Task S4 -- every model-visible term survives packet -> schema -> translation."""
    rows = []
    for term in O.all_terms():
        spec = O.term(term)
        rows.append({
            "term": term,
            "role": spec["role"],
            "in_condition_enum": term in O.condition_dimension_terms(),
            "in_capability_enum": term in O.capability_terms(),
            "declared_in_every_packet": all(
                term in ADM.exposure_states(pk)
                for arm, _ in ARMS for pk in v2[arm].values()),
            "internal_dimension": O.to_internal_dimension(term),
            "internal_context_source": O.to_internal_context_source(term),
            "dimension_round_trips": (TR.round_trip_dimension(term)
                                      if term in O.condition_dimension_terms() else None),
        })
    broken = [r for r in rows
              if not r["in_capability_enum"] or not r["declared_in_every_packet"]
              or (r["in_condition_enum"] and not r["dimension_round_trips"])]
    return {"n_terms": len(rows), "n_broken": len(broken), "broken": broken,
            "terms": rows,
            "invariant": "every term the packet advertises is legal in the schema fields "
                         "its role permits, and translates deterministically to the "
                         "internal namespace"}


def availability_audit(v2) -> dict:
    per = {}
    for arm, _ in ARMS:
        states = {}
        for fid, pk in sorted(v2[arm].items()):
            states[fid] = ADM.exposure_states(pk)
        per[arm] = states
    terms = O.all_terms()
    summary = {}
    for term in terms:
        summary[term] = {
            arm: sorted({per[arm][f].get(term) for f in per[arm]})
            for arm, _ in ARMS}
    return {"n_terms": len(terms), "per_term_states_by_arm": summary,
            "venue_distinction": {
                "target_fixture_venue_context": summary[O.TARGET_FIXTURE_VENUE_CONTEXT],
                "historical_venue_conditioning": summary[O.HISTORICAL_VENUE_CONDITIONING],
                "note": "task S6: the base arm knows which side is at home and does NOT "
                        "carry venue-split history. Those are now two terms, so the "
                        "base arm's venue rejections measure restraint rather than "
                        "ambiguity."}}


def arm_isolation_audit(v1, v2) -> dict:
    """Task S26 -- the arms differ ONLY in evidence representation."""
    fids = sorted(set(v2["base"]) & set(v2["research"]))
    leaks, shape = [], []
    for fid in fids:
        b, r = v2["base"][fid], v2["research"][fid]
        for key in ("packet_schema_version", "evidence_interface_version",
                    "packet_surface_version", "ontology_version", "fixture_id",
                    "information_cutoff_unix"):
            if b.get(key) != r.get(key):
                leaks.append({"fixture_id": fid, "key": key,
                              "base": b.get(key), "research": r.get(key)})
        shape.append({"fixture_id": fid,
                      "base_sections": [s["section_type"] for s in b["sections"]],
                      "research_sections": [s["section_type"] for s in r["sections"]]})
    blob = json.dumps(v2, sort_keys=True, default=str)
    labels = PR.blinding_violations(blob)
    return {"n_fixtures": len(fids), "n_identity_leaks": len(leaks),
            "identity_leaks": leaks,
            "treatment_labels_found_in_packets": labels,
            "section_shapes": shape,
            "claim": "packet_schema_version and every non-evidence identity field are "
                     "identical across arms; nothing names the experimental condition"}


def pit_audit(v1, v2) -> dict:
    """Task S25 -- no packet mentions its own target fixture or any post-cutoff time."""
    problems = []
    for arm, _ in ARMS:
        for fid, pk in sorted(v2[arm].items()):
            cutoff = pk["information_cutoff_unix"]
            blob = json.dumps(pk, sort_keys=True, default=str)
            if fid in blob.replace(f'"fixture_id": "{fid}"', ""):
                problems.append({"arm": arm, "fixture_id": fid,
                                 "problem": "target fixture id appears outside the "
                                            "declared fixture_id field"})
            for sec in pk["sections"]:
                if sec.get("section_type") != "MATCH_LEVEL_OBSERVATIONS":
                    continue
                for blk in sec.get("blocks") or []:
                    for row in blk.get("rows") or []:
                        ts = row.get("kickoff_unix") or row.get("date_unix")
                        if ts is not None and ts >= cutoff:
                            problems.append({"arm": arm, "fixture_id": fid,
                                             "problem": f"observation at {ts} >= cutoff "
                                                        f"{cutoff}"})
    return {"n_problems": len(problems), "problems": problems,
            "claim": "every observation kicked off strictly before the information cutoff "
                     "and no packet names its own target fixture"}


def main():
    v1, v2 = build()
    hashes = {}
    for arm, fn in ARMS:
        hashes[f"{fn}.json"] = _write(f"{fn}.json", v2[arm])

    hashes["evidence_identity_audit.json"] = _write(
        "evidence_identity_audit.json", evidence_identity_audit(v1, v2))
    hashes["roundtrip_audit.json"] = _write("roundtrip_audit.json", roundtrip_audit(v2))
    hashes["availability_audit.json"] = _write("availability_audit.json",
                                               availability_audit(v2))
    hashes["arm_isolation_audit.json"] = _write("arm_isolation_audit.json",
                                                arm_isolation_audit(v1, v2))
    hashes["pit_audit.json"] = _write("pit_audit.json", pit_audit(v1, v2))
    hashes["ontology_snapshot.json"] = _write("ontology_snapshot.json",
                                              O.ontology_snapshot())

    ev = json.load(open(f"{OUT}/evidence_identity_audit.json"))
    rt = json.load(open(f"{OUT}/roundtrip_audit.json"))
    ai = json.load(open(f"{OUT}/arm_isolation_audit.json"))
    pit = json.load(open(f"{OUT}/pit_audit.json"))
    print(f"packets: base={len(v2['base'])} research={len(v2['research'])}")
    print(f"evidence differences vs V5A.1: {ev['n_evidence_differences']}")
    print(f"round-trip broken terms:       {rt['n_broken']}")
    print(f"arm identity leaks:            {ai['n_identity_leaks']} | "
          f"treatment labels: {ai['treatment_labels_found_in_packets']}")
    print(f"PIT problems:                  {pit['n_problems']}")
    for k, v in sorted(hashes.items()):
        print(f"  {v[:16]}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
