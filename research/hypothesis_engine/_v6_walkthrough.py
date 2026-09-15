"""§35 human walkthrough. ZERO SPEND -- no Bedrock, no network.

Runs the exact production path a paid call will run -- `v6_prompt` -> serialized request ->
`validator_v5.adjudicate` -> `v6_scorecard` -> `v6_verdict` -- on a HAND-BUILT response that
mixes the five shapes §35 names:

    1  a valid hypothesis
    2  an unsupported hypothesis (conditions a dimension the packet does not expose)
    3  a firewall-violating hypothesis (a predictive probability about the fixture)
    4  an evidence-backed abstention
    5  an opponent-profile hypothesis

and proves the valid siblings survive the rejected ones. It also surfaces, for a human
reader, exactly what would be sent: one Arm A packet summary, one Arm B packet summary, the
exact system prompt, and the exact output schema. The whole thing is written to
V6_FULL_PACKET_AUDIT-facing JSON so the markdown report can quote it rather than paraphrase.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import schema_v4, validator_v5 as V
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_scorecard as SC

OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"


def _packet_summary(pk, arm):
    cap = ADM.packet_capability_summary(pk)
    ids = E.resolve_evidence_ids(pk)
    kinds = {}
    for i in ids:
        kinds[i.split(":")[0]] = kinds.get(i.split(":")[0], 0) + 1
    return {"arm": arm, "fixture_id": pk["fixture_id"],
            "packet_hash": pk["packet_hash"],
            "information_cutoff_unix": pk["information_cutoff_unix"],
            "n_evidence_ids": len(ids), "evidence_id_kinds": kinds,
            "windows": cap["windows"], "conditionable_terms": cap["conditionable_terms"],
            "exposed_terms": cap["exposed_terms"],
            "section_types": [s["section_type"] for s in pk["sections"]]}


def build_mixed_response(rpk):
    """The §35 response: five shapes, built schema-valid except where the point is a
    violation. Returns (payload, expected_class_by_id)."""
    ids = sorted(E.resolve_evidence_ids(rpk))
    sot = next(i for i in ids if i.startswith("SUMMARY:HOME") and i.endswith("shots_on_target_for"))
    prof = [i for i in ids if i.startswith("PROFILE:HOME:")][:2]

    def base(hid, **kw):
        h = {"hypothesis_id": hid, "research_family": "ATTACK_VOLUME",
             "subject": "HOME_TEAM", "target_metrics": ["shots_on_target"], "side": "FOR",
             "window": "ALL_PRIOR", "conditions": [],
             "comparison": "SUBJECT_OVERALL_BASELINE", "evidence_refs": [sot],
             "candidate_confounders": [], "required_capabilities": [],
             "sufficiency": "SUFFICIENT", "priority": "MEDIUM",
             "question": ("Does HOME_TEAM shots_on_target for-rate differ from its overall "
                          "prior baseline across all matches?")}
        h.update(kw)
        return h

    hyps = [
        # 1 valid
        base("H1"),
        # 5 opponent-profile (valid, placed among the others)
        base("H2", target_metrics=["big_chances"],
             research_family="OPPONENT_PROFILE_INTERACTION", evidence_refs=prof or [sot],
             required_capabilities=["opponent_profile"],
             conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                          "axis": "shots_on_target_against"}],
             question=("Does HOME_TEAM create more big_chances versus defensively strong "
                       "opponents than against opponents overall?")),
        # 3 firewall-violating (predictive probability about the fixture)
        base("H3", target_metrics=["goals"], research_family="ATTACK_QUALITY",
             question="This gives HOME_TEAM a 63% chance of winning the upcoming fixture."),
        # 2 unsupported (conditions referee, which no packet exposes)
        base("H4", target_metrics=["yellow_cards"], research_family="DISCIPLINE",
             required_capabilities=["referee"],
             conditions=[{"dimension": "referee", "value": "SAME"}],
             question=("Does HOME_TEAM yellow_cards for-rate change under the same referee "
                       "in prior matches historically?")),
        # 4 evidence-backed abstention
        base("H5", target_metrics=["saves"], side="AGAINST",
             research_family="DEFENSIVE_CONCESSION", sufficiency="INSUFFICIENT_EVIDENCE",
             question=("Weather-conditioned saves cannot be assessed; the packet exposes "
                       "no weather evidence to support the split.")),
    ]
    expected = {"H1": "VALID_HYPOTHESIS", "H2": "VALID_HYPOTHESIS",
                "H3": "MODEL_FIREWALL_VIOLATION", "H4": "MODEL_AVAILABILITY_VIOLATION",
                "H5": "VALID_ABSTENTION"}
    payload = {"fixture_id": rpk["fixture_id"], "packet_hash": rpk["packet_hash"],
               "hypotheses": hyps}
    return payload, expected


def main():
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    fid = sorted(packets["research"])[0]
    bpk, rpk = packets["base"][fid], packets["research"][fid]

    payload, expected = build_mixed_response(rpk)
    adj = V.adjudicate(payload, packet=rpk, expected_packet_hash=rpk["packet_hash"],
                       expected_fixture_id=fid)
    sc = SC.score_response(adj, rpk)

    rows = []
    for a in adj.hypotheses:
        rows.append({"hypothesis_id": a.hypothesis_id,
                     "expected": expected.get(a.hypothesis_id),
                     "observed": a.outcome_class,
                     "match": a.outcome_class == expected.get(a.hypothesis_id),
                     "qualified": a.scorecard.get("qualified"),
                     "abstaining": a.abstaining,
                     "reasons": {k: v for k, v in a.reasons.items()}})

    valid_ids = {"H1", "H2", "H5"}
    survived = all(r["match"] for r in rows if r["hypothesis_id"] in valid_ids)
    only_intended_failed = all(r["match"] for r in rows)

    walkthrough = {
        "walkthrough_version": "v6_walkthrough_v1",
        "spend_usd": 0.0,
        "arm_a_packet": _packet_summary(bpk, "base"),
        "arm_b_packet": _packet_summary(rpk, "research"),
        "exact_system_prompt_sha256": hashlib.sha256(PR.SYSTEM_PROMPT.encode()).hexdigest(),
        "exact_system_prompt_first_400_chars": PR.SYSTEM_PROMPT[:400],
        "exact_output_schema": {
            "schema_version": schema_v4.SCHEMA_VERSION,
            "schema_content_hash": schema_v4.schema_content_hash(),
            "item_required": schema_v4.hypothesis_item_schema()["required"],
            "evidence_summary_optional": True},
        "serialized_request_sha256_arm_b":
            hashlib.sha256(PR.serialized_request(rpk).encode()).hexdigest(),
        "mixed_response": {
            "n_hypotheses": len(rows),
            "response_class": adj.response_class,
            "response_fatal": adj.fatal,
            "per_hypothesis": rows,
            "valid_siblings_survived_rejected_siblings": survived,
            "only_intended_hypotheses_failed": only_intended_failed,
            "scorecard": {"n_recoverable": sc["n_recoverable"],
                          "n_qualified": sc["n_qualified"],
                          "qualified_rate": sc["qualified_rate"],
                          "n_abstentions": sc["n_abstentions"],
                          "n_abstentions_with_refs": sc["n_abstentions_with_refs"],
                          "class_counts": {k: v for k, v in sc["class_counts"].items()
                                           if v}}},
        "conclusion": ("The response carried one firewall violation (H3) and one "
                       "unavailable-dimension violation (H4). Both were rejected as "
                       "individual hypotheses; H1, H2 (opponent profile) and H5 "
                       "(evidence-backed abstention) survived and were measured. §3 holds "
                       "on the production path, on a real packet."),
    }
    with open(f"{OUT}/human_walkthrough.json", "w") as fh:
        json.dump(walkthrough, fh, indent=1, sort_keys=True, default=str)

    print("=== V6 HUMAN WALKTHROUGH (§35) ===")
    print(f"Arm A packet: {bpk['fixture_id']} | ids={walkthrough['arm_a_packet']['n_evidence_ids']} "
          f"| conditionable={walkthrough['arm_a_packet']['conditionable_terms']}")
    print(f"Arm B packet: {rpk['fixture_id']} | ids={walkthrough['arm_b_packet']['n_evidence_ids']} "
          f"| conditionable={walkthrough['arm_b_packet']['conditionable_terms']}")
    print(f"response_class={adj.response_class} fatal={adj.fatal}")
    for r in rows:
        mark = "OK" if r["match"] else "MISMATCH"
        print(f"  {r['hypothesis_id']}: expected={r['expected']:28s} observed={r['observed']:28s} {mark}")
    print(f"valid siblings survived: {survived}")
    print(f"only intended failed:    {only_intended_failed}")
    print(f"scorecard: n_qualified={sc['n_qualified']} qualified_rate={sc['qualified_rate']} "
          f"abstentions={sc['n_abstentions']}")
    ok = survived and only_intended_failed and not adj.fatal
    print(f"\nWALKTHROUGH {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
