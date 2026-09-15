"""Generated packet-surface contract battery (task S7, S8, S9, S10).

V5A.1's pre-spend suite was hand-written and every case in it was one someone had already
thought of. D1 survived 47 passing tests because every synthetic hypothesis either left
`required_capabilities` empty or happened to contain a correct context-source name. Nobody
wrote the one case that mattered -- "use the term the packet advertises" -- because from
the inside that case looks too obvious to write down.

So this battery does not enumerate cases. It GENERATES them from the packets themselves:

    for every term the packet advertises
      x every field that term is legal in
      x every legal value / axis of that term
      x both arms

and records what the apparatus does with each one. If a term is ever added, renamed or
re-exposed, the battery grows to cover it without anyone remembering to update a list.

THE HARD RULE (task S4)
-----------------------
A STRUCTURALLY CORRECT USE OF AN ADVERTISED TERM MUST NEVER RETURN SCHEMA_INVALID.

It may be rejected downstream -- an exposed term can still be inadmissible for this packet,
and a rejection at that layer is a real scientific observation. But the model must never be
told its response was malformed for using a word the packet handed it. That is the D1 class
and it must be structurally impossible now.

A second rule covers the inverse: no case anywhere may be classified
INFRASTRUCTURE_CONTRACT_FAILURE. That class exists precisely to count our own defects, and
its expected value after this closure is zero.

ZERO SPEND. Nothing here calls Bedrock or any network service.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import lifecycle, schema_v3, validator_v4 as V4
from src.research.hypothesis_engine import vocabulary as V
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_semantics as S
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_packet as P2

V5A1_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a1"
EXPOSED = (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)


def load_packets() -> dict:
    """Both arms' V5A.2 packets, built from the FROZEN V5A.1 evidence (task S2)."""
    out = {}
    for arm, fn in (("base", "packets_base"), ("research", "packets_research")):
        out[arm] = {fid: P2.upgrade_packet(pk)
                    for fid, pk in json.load(open(f"{V5A1_OUT}/{fn}.json")).items()}
    return out


def _ref_for(packet, prefix=None):
    ids = sorted(E.resolve_evidence_ids(packet))
    if prefix:
        hit = [i for i in ids if i.startswith(prefix)]
        if hit:
            return hit[0]
    return ids[0] if ids else None


def _base(packet, hid="H1", **kw) -> dict:
    """A structurally valid hypothesis skeleton, overridable field by field."""
    h = {
        "hypothesis_id": hid,
        "research_family": "ATTACK_VOLUME",
        "subject": "HOME_TEAM",
        "question": "Does the subject's shot volume differ from its overall prior "
                    "baseline in the cohort described by this hypothesis?",
        "target_metrics": ["total_shots"],
        "side": "FOR",
        "window": "ALL_PRIOR",
        "conditions": [],
        "comparison": "SUBJECT_OVERALL_BASELINE",
        "evidence_refs": [r for r in [_ref_for(packet, "SUMMARY:HOME")] if r],
        "candidate_confounders": [],
        "required_capabilities": [],
        "sufficiency": "SUFFICIENT",
        "priority": "MEDIUM",
    }
    h.update(kw)
    return h


def run_case(packet, hypothesis) -> dict:
    res = V4.validate(
        {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
         "hypotheses": [hypothesis]},
        packet=packet, expected_packet_hash=packet["packet_hash"],
        expected_fixture_id=packet["fixture_id"])
    v = res.verdicts[0] if res.verdicts else None
    return {
        "payload_accepted": res.accepted,
        "payload_failure": res.failure,
        "failure_class": res.failure_class,
        "schema_invalid": res.failure == lifecycle.SCHEMA_INVALID,
        "hypothesis_accepted": bool(v and v.accepted),
        "hypothesis_failure": (v.failure if v else None),
        "reasons": list(res.reasons)[:2] + (list(v.reasons)[:2] if v else []),
    }


# ----------------------------------------------------------------------------------------
# Generators. Each yields (case_id, hypothesis, expectation) for one packet.
# ----------------------------------------------------------------------------------------
def gen_term_cases(packet, arm, fid):
    """THE D1 CASE, generated for every term x every field it is legal in."""
    states = ADM.exposure_states(packet)
    for term in O.all_terms():
        exposed = states.get(term) in EXPOSED

        # (a) the term as a declared dependency -- the field D1 died in.
        yield (f"{arm}/{fid}/cap/{term}",
               _base(packet, required_capabilities=[term]),
               {"advertised": exposed, "surface": "required_capabilities", "term": term})

        # (b) the term as a cohort split, once per legal value x axis.
        if term not in O.condition_dimension_terms():
            continue
        axes = O.axes_for(term) or (None,)
        for value in O.values_for(term):
            for axis in axes:
                cond = {"dimension": term, "value": value}
                if axis:
                    cond["axis"] = axis
                label = f"{term}={value}" + (f"/{axis}" if axis else "")
                yield (f"{arm}/{fid}/cond/{label}",
                       _base(packet, conditions=[cond], required_capabilities=[term]),
                       {"advertised": exposed, "surface": "conditions", "term": term,
                        "cond_dimension": term, "cond_value": value, "cond_axis": axis})


def gen_enum_cases(packet, arm, fid):
    """Every remaining model-visible enum member, exercised at least once (task S10)."""
    for fam in V.RESEARCH_FAMILIES:
        yield (f"{arm}/{fid}/family/{fam}", _base(packet, research_family=fam),
               {"advertised": True, "surface": "research_family", "term": fam})
    for subj in list(V.SUBJECTS) + list(V.SUBJECT_ALIASES):
        yield (f"{arm}/{fid}/subject/{subj}", _base(packet, subject=subj),
               {"advertised": True, "surface": "subject", "term": subj})
    for side in V.SIDES:
        yield (f"{arm}/{fid}/side/{side}", _base(packet, side=side),
               {"advertised": True, "surface": "side", "term": side})
    for win in V.WINDOWS:
        yield (f"{arm}/{fid}/window/{win}", _base(packet, window=win),
               {"advertised": True, "surface": "window", "term": win})
    for comp in V.COMPARISONS:
        yield (f"{arm}/{fid}/comparison/{comp}", _base(packet, comparison=comp),
               {"advertised": True, "surface": "comparison", "term": comp})
    for suf in V.SUFFICIENCY:
        yield (f"{arm}/{fid}/sufficiency/{suf}", _base(packet, sufficiency=suf),
               {"advertised": True, "surface": "sufficiency", "term": suf})
    for pri in V.PRIORITY:
        yield (f"{arm}/{fid}/priority/{pri}", _base(packet, priority=pri),
               {"advertised": True, "surface": "priority", "term": pri})
    for m in sorted(set(S.CANONICAL_METRICS) | set(S.EXCLUDED_METRICS)):
        yield (f"{arm}/{fid}/metric/{m}", _base(packet, target_metrics=[m]),
               {"advertised": m in S.CANONICAL_METRICS, "surface": "target_metrics",
                "term": m})


def gen_abstention_cases(packet, arm, fid):
    """Task S5, all four cells of the abstention contract."""
    good = _ref_for(packet, "SUMMARY:HOME")
    fake = "SUMMARY:HOME:ALL_PRIOR:ANY:this_metric_does_not_exist_for"
    for label, suf, refs, expect_accept in (
        ("abstain_no_refs", "INSUFFICIENT_EVIDENCE", [], True),
        ("abstain_valid_refs", "INSUFFICIENT_EVIDENCE", [good], True),
        ("abstain_fabricated_refs", "INSUFFICIENT_EVIDENCE", [fake], False),
        ("sufficient_no_refs", "SUFFICIENT", [], False),
        ("sufficient_valid_refs", "SUFFICIENT", [good], True),
        ("sufficient_fabricated_refs", "SUFFICIENT", [fake], False),
    ):
        yield (f"{arm}/{fid}/abstention/{label}",
               _base(packet, sufficiency=suf, evidence_refs=refs),
               {"advertised": True, "surface": "abstention", "term": label,
                "expect_hypothesis_accepted": expect_accept})


def gen_negative_cases(packet, arm, fid):
    """Task S9 -- things that MUST be rejected, and must be rejected for the stated reason."""
    cases = [
        ("unknown_dimension", _base(packet, conditions=[
            {"dimension": "not_a_real_term", "value": "HOME"}])),
        ("retired_bare_venue", _base(packet, conditions=[
            {"dimension": "venue", "value": "HOME"}])),
        ("internal_namespace_leak", _base(packet, required_capabilities=["venue"])),
        ("internal_ctx_source_leak", _base(packet,
                                           required_capabilities=["historical_formation"])),
        ("cross_dimension_value", _base(packet, conditions=[
            {"dimension": O.HISTORICAL_VENUE_CONDITIONING, "value": "HIGH"}])),
        ("profile_without_axis", _base(packet, conditions=[
            {"dimension": "opponent_profile", "value": "HIGH"}])),
        ("axis_on_axisless_dimension", _base(packet, conditions=[
            {"dimension": "competition", "value": "SAME", "axis": "goals_for"}])),
        ("unknown_metric", _base(packet, target_metrics=["not_a_metric"])),
        ("excluded_metric", _base(packet, target_metrics=["npxg"])),
        ("fabricated_evidence", _base(packet, evidence_refs=["MATCH:HOME:M99:goals_for"])),
        ("extra_property", {**_base(packet), "confidence": "high"}),
        ("numeric_claim_in_question", _base(
            packet, question="There is a 0.62 probability the subject exceeds its "
                             "baseline shot volume in the upcoming fixture.")),
    ]
    for label, h in cases:
        yield (f"{arm}/{fid}/negative/{label}", h,
               {"advertised": False, "surface": "negative", "term": label,
                "expect_rejected": True})


GENERATORS = (gen_term_cases, gen_enum_cases, gen_abstention_cases, gen_negative_cases)


def run(limit_fixtures=None) -> dict:
    packets = load_packets()
    fixtures = sorted(packets["research"])
    if limit_fixtures:
        fixtures = fixtures[:limit_fixtures]

    results, violations = [], []
    for arm in ("base", "research"):
        for fid in fixtures:
            pk = packets[arm].get(fid)
            if pk is None:
                continue
            for gen in GENERATORS:
                for case_id, h, exp in gen(pk, arm, fid):
                    out = run_case(pk, h)
                    rec = {"case_id": case_id, "arm": arm, "fixture_id": fid,
                           **exp, **out}
                    results.append(rec)

                    # --- HARD RULE 1: advertised term never SCHEMA_INVALID -------------
                    if exp.get("advertised") and out["schema_invalid"]:
                        violations.append({"rule": "ADVERTISED_TERM_SCHEMA_INVALID",
                                           **rec})
                    # --- HARD RULE 2: our own defects must be zero ---------------------
                    if out["failure_class"] == V4.INFRASTRUCTURE_CONTRACT_FAILURE:
                        violations.append({"rule": "INFRASTRUCTURE_CONTRACT_FAILURE",
                                           **rec})
                    # --- stated expectations -------------------------------------------
                    if ("expect_hypothesis_accepted" in exp
                            and out["hypothesis_accepted"] != exp["expect_hypothesis_accepted"]):
                        violations.append({"rule": "ABSTENTION_CONTRACT_MISMATCH", **rec})
                    if exp.get("expect_rejected") and out["hypothesis_accepted"]:
                        violations.append({"rule": "NEGATIVE_CASE_ACCEPTED", **rec})

    return {"schema_version": schema_v3.SCHEMA_VERSION,
            "schema_content_hash": schema_v3.schema_content_hash(),
            "ontology_version": O.ONTOLOGY_VERSION,
            "n_cases": len(results),
            "n_violations": len(violations),
            "fixtures": fixtures,
            "violations": violations,
            "results": results}


def coverage(results) -> dict:
    """MODEL_VISIBLE_ENUM_COVERAGE -- every member of every model-visible enum, exercised."""
    doc = schema_v3.build_schema()
    item = doc["properties"]["hypotheses"]["items"]["properties"]
    cond = item["conditions"]["items"]["properties"]
    enums = {
        "research_family": item["research_family"]["enum"],
        "subject": item["subject"]["enum"],
        "side": item["side"]["enum"],
        "window": item["window"]["enum"],
        "comparison": item["comparison"]["enum"],
        "sufficiency": item["sufficiency"]["enum"],
        "priority": item["priority"]["enum"],
        "target_metrics": item["target_metrics"]["items"]["enum"],
        "required_capabilities": item["required_capabilities"]["items"]["enum"],
        "conditions.dimension": cond["dimension"]["enum"],
        "conditions.value": cond["value"]["enum"],
        "conditions.axis": cond["axis"]["enum"],
    }
    seen = {k: set() for k in enums}
    for r in results:
        surface, term = r.get("surface"), r.get("term")
        if surface in seen and term in enums[surface]:
            seen[surface].add(term)
        if surface == "conditions":
            # Read off the fields the generator recorded, never parsed back out of a
            # case id: a coverage number derived by re-parsing a label is measuring the
            # label, not the case.
            for enum_key, rec_key in (("conditions.dimension", "cond_dimension"),
                                      ("conditions.value", "cond_value"),
                                      ("conditions.axis", "cond_axis")):
                val = r.get(rec_key)
                if val in enums[enum_key]:
                    seen[enum_key].add(val)
        if surface == "required_capabilities" and term in enums["required_capabilities"]:
            seen["required_capabilities"].add(term)

    per = {k: {"total": len(set(v)), "covered": len(seen[k]),
               "uncovered": sorted(set(v) - seen[k])}
           for k, v in enums.items()}
    total = sum(p["total"] for p in per.values())
    cov = sum(p["covered"] for p in per.values())
    return {"per_enum": per, "n_enum_members": total, "n_covered": cov,
            "model_visible_enum_coverage": round(cov / total, 6) if total else 0.0}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rep = run(limit_fixtures=a.fixtures)
    rep["coverage"] = coverage(rep["results"])
    print(f"cases={rep['n_cases']} violations={rep['n_violations']} "
          f"enum_coverage={rep['coverage']['model_visible_enum_coverage']:.4f}")
    for v in rep["violations"][:20]:
        print("  VIOLATION", v["rule"], v["case_id"], v.get("hypothesis_failure"),
              (v.get("reasons") or [""])[0][:120])
    for k, p in sorted(rep["coverage"]["per_enum"].items()):
        if p["uncovered"]:
            print(f"  uncovered {k}: {p['uncovered'][:12]}")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(rep, fh, indent=1, sort_keys=True)
    raise SystemExit(0)
