"""Counter-evidence golden control runner (patch §13, §14, §15).

Runs each golden case A-F through the hardened call path and scores counter-evidence
DETECTION + CONSTRAINT, without rewarding counter-evidence quantity. Optionally runs k calls
per case and reports the modal / worst-case outcome so a single unlucky call does not decide a
case.

Writes research/llm_matchup/out/hardening/counter_evidence_controls.csv and
counter_evidence_controls.json.

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_counter_golden [K]
"""
from __future__ import annotations
import os, sys, csv, json, time

from src.research.llm_matchup.hardening import counter_golden as CG
from src.research.llm_matchup.hardening import adapter_v3 as A3

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"


def run(k: int = 1, use_cache: bool = True):
    os.makedirs(OUT, exist_ok=True)
    cases = CG.cases()
    rows = []
    call_rows = []
    total_cost = 0.0
    for cid, case in cases.items():
        packet = case["packet"]
        results = A3.analyze_k(packet, k=k, use_cache=use_cache)
        scored_calls = []
        for r in results:
            m = r.manifest
            cost = A3.estimate_cost_usd(m.get("input_tokens"), m.get("output_tokens"))
            total_cost += cost
            call_rows.append({"study": "counter_golden", "case": cid,
                              "call_index": m.get("call_index"), "status": r.status,
                              "cost_usd": cost, "reject": m.get("reject_reason")})
            if r.status == "OK":
                scored_calls.append(CG.score_case(cid, case, r.state))
            else:
                scored_calls.append({"case": cid, "mechanism": case["target_mechanism"],
                                     "mechanism_present": False, "pass": False,
                                     "note": f"{r.status}: {m.get('reject_reason') or m.get('error')}"})

        # aggregate across k calls: a case PASSES the CONSTRAINT contract only if ALL OK calls
        # pass (worst-case; patch §14 wants reliable behavior, not lucky behavior). Explicit
        # recall is reported separately (min across calls) and NOT part of the pass gate.
        oks = [s for s in scored_calls if s.get("mechanism_present")]
        passed = bool(oks) and all(s["pass"] for s in oks)
        recalls = [s["counter_recall"] for s in oks if s.get("counter_recall") is not None]
        row = {
            "case": cid, "target_mechanism": case["target_mechanism"],
            "counter_expected": case["expect"]["counter_expected"], "k_calls": k,
            "n_ok": len(oks),
            "min_explicit_recall": (min(recalls) if recalls else None),
            "mean_explicit_recall": (round(sum(recalls) / len(recalls), 4) if recalls else None),
            "any_false_opposition": any(s.get("false_opposition") for s in oks),
            "all_state_constrained": bool(oks) and all(s.get("state_constrained") for s in oks),
            "all_uncertainty_ok": bool(oks) and all(s.get("uncertainty_ok") for s in oks),
            "all_search_performed": bool(oks) and all(s.get("counter_search_performed") for s in oks),
            "statuses": "|".join(str(s.get("status")) for s in oks),
            "constraint_pass": passed,
        }
        rows.append(row)
        print(f"  case {cid} [{case['target_mechanism']}] constraint_pass={passed} "
              f"explicit_recall={row['min_explicit_recall']} constrained={row['all_state_constrained']} "
              f"false_opp={row['any_false_opposition']} statuses={row['statuses']}")

    _write_csv(os.path.join(OUT, "counter_evidence_controls.csv"), rows)
    n_pass = sum(1 for r in rows if r["constraint_pass"])
    n_explicit = sum(1 for r in rows if (r["min_explicit_recall"] or 0) > 0)
    summary = {"study": "counter_golden", "k_calls": k, "n_cases": len(rows),
               "n_constraint_pass": n_pass,
               "constraint_pass_rate": round(n_pass / max(len(rows), 1), 4),
               "n_explicit_recall_any": n_explicit,
               "cost_usd": round(total_cost, 4), "rows": rows,
               "created_unix": int(time.time())}
    json.dump(summary, open(os.path.join(OUT, "counter_evidence_controls.json"), "w"),
              indent=2, default=str)
    print(json.dumps({"n_cases": len(rows), "n_constraint_pass": n_pass,
                      "constraint_pass_rate": summary["constraint_pass_rate"],
                      "n_explicit_recall_any": n_explicit,
                      "cost_usd": summary["cost_usd"]}, indent=2))
    return summary


def _write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run(k=k)
