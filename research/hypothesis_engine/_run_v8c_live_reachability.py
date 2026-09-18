"""LIVE search-reachability report (P1-C) on the REAL corpus, exposed-50 development fixtures.

Answers: under MAX_SEARCH_CALLS=6 x PAGE_SIZE_CAP=50, is every evaluable candidate addressable
by a legal structural query? Reads no target outcome. No sealed-947 access.
"""
from __future__ import annotations

import json
import sys
import time

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)
OUT = f"{ENG}/V8C_LIVE_SEARCH_REACHABILITY_REPORT.json"

N_FIXTURES = 4


def main():
    from src.research.hypothesis_v8c import blind_index as BI
    from src.research.hypothesis_v8c import harness as H
    from src.research.hypothesis_v8c import historical_pit as HPIT
    from src.research.hypothesis_v8c import live_reachability as LR
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import universe as UNI
    from src.research.hypothesis_v8c import provenance as PROV
    from src.research.hypothesis_v8c import vintage as VIN

    champ = H.assert_champion_unchanged()
    cap, index, _ = H.build(check_champion=False)
    hp = HPIT.HistoricalProfileIndex(index)

    fz = json.load(open(f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"))
    fixtures = fz["pilot_fixture_ids_ordered"][:N_FIXTURES]

    rows, t0 = [], time.time()
    for n, fid in enumerate(fixtures, 1):
        pos = index.pos_of_fixture[fid]
        sealed = BI.TargetBlindIndex(index, [pos])
        ctx = PC.build_pit_context(sealed, pos, historical=hp)
        fu = UNI.build_fixture_universe(sealed, pos, ctx=ctx, capability=cap, fixture_id=fid)
        rep = LR.audit_fixture(fu)
        rep["blind_audit_target_outcomes_viewed"] = \
            sealed.audit_report()["target_outcomes_viewed"]
        rows.append(rep)
        print(f"[live] {n}/{len(fixtures)} {fid} evaluable={rep['n_evaluable']} "
              f"unreachable={rep['n_live_unreachable']} "
              f"worst_set={rep['worst_canonical_result_set']} "
              f"[{time.time()-t0:.0f}s]", flush=True)

    total_unreachable = sum(r["n_live_unreachable"] for r in rows)
    worst = max((r["worst_canonical_result_set"] for r in rows), default=0)
    max_pages = max((r["max_pages_required_for_any_candidate"] for r in rows), default=1)
    failing = {}
    for r in rows:
        for k, v in r["failing_candidate_classes"].items():
            failing.setdefault(k, {"n": 0, "unreachable": 0})
            failing[k]["n"] += v["n"]
            failing[k]["unreachable"] += v["unreachable"]

    report = {
        "report_version": "v8c_live_search_reachability_v1",
        "evidence_class": "DEVELOPMENT_REAL_CORPUS",
        "evidence_note": ("exposed-50 fixtures only, structural/pre-T information only; "
                          "no target outcome read, no sealed-947 access"),
        "definition": rows[0]["definition"] if rows else None,
        "max_search_calls": LR.MAX_SEARCH_CALLS, "page_size_cap": LR.PAGE_SIZE_CAP,
        "call_cap_relaxed": False,
        "n_fixtures": len(rows),
        "n_evaluable_total": sum(r["n_evaluable"] for r in rows),
        "n_live_addressable_total": sum(r["n_live_addressable"] for r in rows),
        "LIVE_UNREACHABLE_CANDIDATES": total_unreachable,
        "worst_canonical_result_set": worst,
        "max_pages_required_for_any_candidate": max_pages,
        "pagination_within_call_budget": max_pages <= LR.MAX_SEARCH_CALLS,
        "failing_candidate_classes": failing,
        "design_conflict": total_unreachable > 0,
        "verdict": ("PASS" if total_unreachable == 0
                    else "DESIGN_CONFLICT_REPORTED_NOT_WEAKENED"),
        "per_fixture": rows,
        "corpus_vintage_full": VIN.corpus_vintage_full(index),
        "capability_hash": VIN.capability_hash(cap),
        "champion_sha256": champ,
        "sealed_947_referenced": False, "new_sonnet_calls": 0,
    }
    # P1-G: the artifact must carry the provenance of the process that produced it, or the
    # freeze gate will (correctly) refuse to let it satisfy any condition.
    report[PROV.PROVENANCE_KEY] = PROV.stamp(
        corpus_hash=report["corpus_vintage_full"],
        capability_hash=report["capability_hash"])
    with open(OUT, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"\n[live] LIVE_UNREACHABLE_CANDIDATES = {total_unreachable}")
    print(f"[live] worst canonical result set   = {worst} (cap {LR.PAGE_SIZE_CAP})")
    print(f"[live] max pages for any candidate  = {max_pages} (cap {LR.MAX_SEARCH_CALLS})")
    print(f"[live] VERDICT = {report['verdict']}")
    print(f"[live] wrote {OUT}")


if __name__ == "__main__":
    main()
