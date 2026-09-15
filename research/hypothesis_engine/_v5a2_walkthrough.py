"""Human model walkthrough (task S11): seven hypothesis types x both arms.

The generated battery proves no ADVERTISED term is ever malformed. It does not prove the
apparatus behaves SENSIBLY -- that a question a competent researcher would ask is accepted
where the evidence supports it and refused, for a legible reason, where it does not. That
judgement needs hand-written hypotheses a person can read, which is what this produces.

ZERO SPEND. The hypotheses are written by hand here; no model is called.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import validator_v4 as V4
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_ontology as O

OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"
FIXTURE = "mt_010243515"


def _ids(pk, prefix):
    return [i for i in sorted(E.resolve_evidence_ids(pk)) if i.startswith(prefix)]


def _first(pk, *prefixes):
    for p in prefixes:
        hit = _ids(pk, p)
        if hit:
            return hit[0]
    return sorted(E.resolve_evidence_ids(pk))[0]


def types(pk) -> list:
    summ = _first(pk, "SUMMARY:HOME")
    prof = _ids(pk, "PROFILE:HOME:")
    form = _ids(pk, "FORMATION:")
    match = _ids(pk, "MATCH:HOME:")
    w5 = [i for i in _ids(pk, "SUMMARY:HOME") if ":W5:" in i]
    venue = [i for i in _ids(pk, "SUMMARY:HOME")
             if ":HOME_ONLY:" in i or ":AWAY_ONLY:" in i]

    def h(hid, question, **kw):
        base = {"hypothesis_id": hid, "research_family": "ATTACK_VOLUME",
                "subject": "HOME_TEAM", "question": question,
                "target_metrics": ["total_shots"], "side": "FOR", "window": "ALL_PRIOR",
                "conditions": [], "comparison": "SUBJECT_OVERALL_BASELINE",
                "evidence_refs": [summ], "candidate_confounders": [],
                "required_capabilities": [], "sufficiency": "SUFFICIENT",
                "priority": "MEDIUM"}
        base.update(kw)
        return base

    return [
        ("1_unconditioned_volume",
         h("H1", "Does HOME_TEAM's shot volume differ from a typical side's, measured "
                 "against its own long-run prior baseline?")),
        ("2_historical_venue_split",
         h("H2", "Does HOME_TEAM generate more shots in prior matches played at home than "
                 "in its overall prior baseline?",
           research_family="VENUE_EFFECT",
           conditions=[{"dimension": O.HISTORICAL_VENUE_CONDITIONING, "value": "HOME"}],
           comparison="SUBJECT_VENUE_BASELINE",
           required_capabilities=[O.HISTORICAL_VENUE_CONDITIONING],
           evidence_refs=[venue[0]] if venue else [summ])),
        ("3_recent_vs_long",
         h("H3", "Does HOME_TEAM's shot volume over its five most recent prior matches "
                 "differ from its full-history prior baseline?",
           research_family="FORM_VS_BASELINE", window="W5",
           comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
           required_capabilities=["recent_window_summaries"],
           evidence_refs=[w5[0]] if w5 else [summ])),
        ("4_opponent_profile",
         h("H4", "Does HOME_TEAM's shot volume differ against opponents in the HIGH band "
                 "for shots on target conceded, relative to its overall prior baseline?",
           research_family="OPPONENT_PROFILE_INTERACTION",
           conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                        "axis": "shots_on_target_against"}],
           required_capabilities=["opponent_profile"],
           evidence_refs=[prof[0]] if prof else [summ])),
        ("5_formation",
         h("H5", "Does HOME_TEAM's shot volume differ in prior matches where it lined up "
                 "in a back-four structure, relative to its overall prior baseline?",
           research_family="FORMATION_INTERACTION",
           conditions=[{"dimension": "own_formation_family", "value": "BACK_FOUR"}],
           required_capabilities=["own_formation_family",
                                  "formation_recorded_history"],
           evidence_refs=[form[0]] if form else [summ])),
        ("6_interaction",
         h("H6", "Does HOME_TEAM's shot volume against HIGH-band opponents differ between "
                 "prior home matches and its overall prior baseline?",
           research_family="OPPONENT_PROFILE_INTERACTION",
           conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                        "axis": "shots_on_target_against"},
                       {"dimension": O.HISTORICAL_VENUE_CONDITIONING, "value": "HOME"}],
           required_capabilities=["opponent_profile",
                                  O.HISTORICAL_VENUE_CONDITIONING],
           evidence_refs=([prof[0]] if prof else [summ])
                         + ([venue[0]] if venue else []))),
        ("7_abstention_citing_the_gap",
         h("H7", "Whether HOME_TEAM's shot volume depends on the opponent's announced "
                 "formation cannot be assessed: this packet exposes no expected formation.",
           research_family="FORMATION_INTERACTION",
           sufficiency="INSUFFICIENT_EVIDENCE",
           evidence_refs=[i for i in [_first(pk, "AVAIL:expected_formation")]
                          if i.startswith("AVAIL:")] or [summ])),
    ]


def run():
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))[FIXTURE]
               for arm in ("base", "research")}
    rows = []
    for arm, pk in packets.items():
        for label, h in types(pk):
            res = V4.validate({"fixture_id": pk["fixture_id"],
                               "packet_hash": pk["packet_hash"], "hypotheses": [h]},
                              packet=pk, expected_packet_hash=pk["packet_hash"],
                              expected_fixture_id=pk["fixture_id"])
            v = res.verdicts[0] if res.verdicts else None
            rows.append({
                "arm": arm, "type": label,
                "payload_failure": res.failure,
                "accepted": bool(v and v.accepted),
                "failure": (v.failure if v else None),
                "reason": ((v.reasons or [""])[-1] if v else (res.reasons or [""])[0]),
                "question": h["question"],
            })
    return {"fixture_id": FIXTURE, "rows": rows}


if __name__ == "__main__":
    rep = run()
    with open(f"{OUT}/walkthrough.json", "w") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    for r in rep["rows"]:
        mark = "ACCEPT" if r["accepted"] else "REJECT"
        print(f"{r['arm']:9s} {r['type']:28s} {mark:6s} {r['failure'] or ''}")
        if not r["accepted"]:
            print(f"                                     -> {r['reason'][:150]}")
    raise SystemExit(0)
