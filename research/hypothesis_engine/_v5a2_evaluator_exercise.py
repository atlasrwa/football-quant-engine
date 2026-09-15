"""Exercise the FROZEN evaluator end-to-end before it is frozen (task S12). ZERO SPEND.

`v5a1_evaluator` was hashed and preregistered without ever having been run over a full
response set, and the first thing the analysis driver did on real paid data was raise
`KeyError: 'venue_use'` -- because `score_response` returns early on a whole-response
failure and the aggregation layer assumed every key was present. The evaluator was frozen
but not COMPLETE, and the difference only showed up after money had been spent.

So every path is driven here against synthetic responses, before the freeze:

    normal response, both arms          abstention-only response
    whole-response SCHEMA_INVALID       repeat groups with zero variance
    NO_TOOL_USE (raw is None)           an arm with zero valid responses
    apparatus defect (per-hypothesis)   a full paired aggregation -> final_verdict

Synthetic responses are HAND-CONSTRUCTED, not model output. This measures whether the
analysis path executes and produces coherent numbers -- it is not evidence about any model
and no verdict from it is a scientific result.
"""
from __future__ import annotations

import json
import statistics
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_evaluator as EV
from src.research.hypothesis_oos import v5a2_ontology as O

OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"


def _hyp(pk, hid, **kw):
    ids = sorted(E.resolve_evidence_ids(pk))
    ref = next((i for i in ids if i.startswith("SUMMARY:HOME")), ids[0])
    h = {"hypothesis_id": hid, "research_family": "ATTACK_VOLUME", "subject": "HOME_TEAM",
         "question": "Does the subject's shot volume differ from its overall prior "
                     "baseline in the cohort this hypothesis describes?",
         "target_metrics": ["total_shots"], "side": "FOR", "window": "ALL_PRIOR",
         "conditions": [], "comparison": "SUBJECT_OVERALL_BASELINE",
         "evidence_refs": [ref], "candidate_confounders": [],
         "required_capabilities": [], "sufficiency": "SUFFICIENT", "priority": "MEDIUM"}
    h.update(kw)
    return h


def _resp(pk, hyps):
    return {"fixture_id": pk["fixture_id"], "packet_hash": pk["packet_hash"],
            "hypotheses": hyps}


def normal(pk, n, research: bool):
    hyps = [_hyp(pk, f"H{i+1}") for i in range(n)]
    if research:
        ids = sorted(E.resolve_evidence_ids(pk))
        prof = next((i for i in ids if i.startswith("PROFILE:HOME:")), None)
        if prof:
            hyps[0] = _hyp(pk, "H1",
                           conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                                        "axis": "shots_on_target_against"}],
                           required_capabilities=["opponent_profile"],
                           evidence_refs=[prof])
        hyps[1] = _hyp(pk, "H2", window="W5",
                       comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
                       required_capabilities=["recent_window_summaries"])
    return _resp(pk, hyps)


def main():
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    fids = sorted(packets["research"])
    checks, problems = [], []

    def check(label, fn):
        try:
            val = fn()
            checks.append({"path": label, "ok": True, "detail": val})
        except Exception as exc:
            checks.append({"path": label, "ok": False,
                           "detail": f"{type(exc).__name__}: {exc}"})
            problems.append(f"{label}: {type(exc).__name__}: {exc}")

    pk_b = packets["base"][fids[0]]
    pk_r = packets["research"][fids[0]]

    # ---- per-response paths ----------------------------------------------------------
    check("normal_base", lambda: EV.rates(EV.score_response(normal(pk_b, 6, False), pk_b)))
    check("normal_research",
          lambda: EV.rates(EV.score_response(normal(pk_r, 6, True), pk_r)))
    check("no_tool_use", lambda: EV.rates(EV.score_response(None, pk_r)))
    check("whole_response_schema_invalid",
          lambda: EV.rates(EV.score_response(
              _resp(pk_r, [_hyp(pk_r, "H1", conditions=[
                  {"dimension": "not_a_term", "value": "HOME"}])]), pk_r)))
    check("abstention_only",
          lambda: EV.rates(EV.score_response(
              _resp(pk_r, [_hyp(pk_r, f"H{i+1}", sufficiency="INSUFFICIENT_EVIDENCE")
                           for i in range(3)]), pk_r)))
    check("empty_hypothesis_list",
          lambda: EV.rates(EV.score_response(_resp(pk_r, []), pk_r)))
    check("firewall_blocked",
          lambda: EV.rates(EV.score_response(
              _resp(pk_r, [_hyp(pk_r, "H1",
                                question="There is a 0.62 probability the subject "
                                         "exceeds its baseline shot volume.")]), pk_r)))

    # ---- self-noise, including the zero-variance case --------------------------------
    check("self_noise_zero_variance",
          lambda: EV.self_noise_floor(
              [{"fixture_id": f, "arm": a, "values": [4, 4, 4]}
               for f in fids[:3] for a in ("base", "research")]))
    check("self_noise_no_groups", lambda: EV.self_noise_floor([]))
    check("self_noise_real_spread",
          lambda: EV.self_noise_floor(
              [{"fixture_id": f, "arm": a, "values": [3, 5, 4]}
               for f in fids[:3] for a in ("base", "research")]))

    # ---- evaluability ----------------------------------------------------------------
    check("evaluability_zero_arm", lambda: EV.evaluability(0, 1, 0, 0, 0))
    check("evaluability_full", lambda: EV.evaluability(10, 10, 10, 3, 3))

    # ---- FULL paired aggregation -> final_verdict ------------------------------------
    def full_run():
        per = {}
        for arm, pks in packets.items():
            for fid in fids:
                pk = pks[fid]
                s = EV.score_response(normal(pk, 6, arm == "research"), pk)
                per[(arm, fid)] = s
        paired = [{"fixture_id": f,
                   "diff": (per[("research", f)][EV.PRIMARY_METRIC]
                            - per[("base", f)][EV.PRIMARY_METRIC])}
                  for f in fids]
        rr = [EV.rates(per[("research", f)]) for f in fids]
        bb = [EV.rates(per[("base", f)]) for f in fids]

        def d(key):
            return (statistics.fmean(x[key] for x in rr)
                    - statistics.fmean(x[key] for x in bb))
        disc = {"compilability_delta": d("compilability"),
                "firewall_clean_delta": d("firewall_clean_rate"),
                "fabricated_evidence_delta": d("fabricated_evidence_rate"),
                "unsupported_dimension_delta": d("unsupported_dimension_rate")}
        floor = EV.self_noise_floor(
            [{"fixture_id": f, "arm": a, "values": [per[(a, f)][EV.PRIMARY_METRIC]] * 3}
             for f in fids[:3] for a in ("base", "research")])["floor_used"]
        n_valid = {a: sum(1 for f in fids
                          if per[(a, f)]["whole_response_failure"] is None)
                   for a in ("base", "research")}
        ev = EV.evaluability(len(fids), n_valid["base"], n_valid["research"], 3, 3)
        return EV.final_verdict("COMPLETE", ev, paired, floor, disc)

    check("full_paired_aggregation_to_final_verdict", full_run)

    # ---- the base arm's structurally-zero availability dimensions --------------------
    def base_avail():
        s = EV.score_response(normal(pk_b, 6, False), pk_b)
        return {k: {"available": s[f"{k}_available"], "count": s[k]}
                for k in EV.AVAILABILITY_DIMENSIONS}
    check("base_arm_availability_dimensions", base_avail)

    rep = {"n_paths": len(checks), "n_failed": len(problems),
           "problems": problems, "checks": checks,
           "caveat": "synthetic hand-constructed responses; exercises the analysis path "
                     "only and is not evidence about any model"}
    with open(f"{OUT}/evaluator_exercise.json", "w") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True, default=str)

    for c in checks:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['path']}")
        if not c["ok"]:
            print(f"        {c['detail']}")
    print(f"\npaths exercised: {len(checks)} | failures: {len(problems)}")
    fv = next((c for c in checks
               if c["path"] == "full_paired_aggregation_to_final_verdict"), None)
    if fv and fv["ok"]:
        d = fv["detail"]
        print(f"full-run final_verdict: execution={d['execution_status']} "
              f"scientific={d['scientific_status']} verdict={d['scientific_verdict']}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
