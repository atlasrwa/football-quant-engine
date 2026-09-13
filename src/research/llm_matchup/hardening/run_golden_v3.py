"""V3 patch SS40: run a small stratified live smoke batch through the identity-neutral
pipeline (neutralize_v3 -> adapter_v4) BEFORE running the larger identity-control battery.

Writes: out/hardening_v3/golden_v3_states.jsonl, out/hardening_v3/golden_v3_summary.json

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_golden_v3 [N]
"""
from __future__ import annotations
import os, sys, json, time

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import audit_request as AR
from src.research.llm_matchup.hardening import versions_v3 as V3

OUT = "/home/ubuntu/research/llm_matchup/out/hardening_v3"


def run(n: int = 15, use_cache: bool = True):
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=n, max_scan=200)
    print(f"golden_v3 smoke: {len(picks)} fixtures")

    rows, states_out = [], []
    total_cost = 0.0
    for pi, p in enumerate(picks):
        cand = p.candidate
        source_packet = ctx.build_packet(cand, include_formation=True, projected=True)
        neutral = NZ3.neutralize_for_llm_v2(source_packet)

        audit = AR.audit_serialized_request(neutral, source_packet)
        result = A4.analyze_matchup_v4(neutral, use_cache=use_cache)
        cost = A4.estimate_cost_usd(result.manifest.get("input_tokens"),
                                    result.manifest.get("output_tokens"))
        total_cost += cost

        n_a = n_b = n_m = 0
        n_unknown = n_conflicted = 0
        if result.status == "OK":
            n_a, n_b, n_m = (len(result.state.get("team_a_states", [])),
                             len(result.state.get("team_b_states", [])),
                             len(result.state.get("matchup_states", [])))
            for coll in ("team_a_states", "team_b_states"):
                for it in result.state.get(coll, []):
                    if it.get("level") == "UNKNOWN":
                        n_unknown += 1
            for it in result.state.get("matchup_states", []):
                if it.get("assessment") == "CONFLICTED":
                    n_conflicted += 1

        row = {
            "fixture_id": p.fixture_id, "competition": p.competition,
            "status": result.status, "reject_field": result.manifest.get("reject_field"),
            "reject_reason": result.manifest.get("reject_reason"),
            "n_team_a_states": n_a, "n_team_b_states": n_b, "n_matchup_states": n_m,
            "n_unknown": n_unknown, "n_conflicted": n_m and n_conflicted,
            "request_audit_clean": audit == [], "request_audit_leaks": audit,
            "cost_usd": cost, "cache_hit": result.manifest.get("cache_hit"),
        }
        rows.append(row)
        states_out.append({"study": "golden_v3", "fixture_id": p.fixture_id,
                           "status": result.status, "state": result.state,
                           "manifest": result.manifest})
        print(f"  [{pi+1}/{len(picks)}] {p.fixture_id} status={result.status} "
              f"a/b/m={n_a}/{n_b}/{n_m} unknown={n_unknown} conflicted={n_conflicted} "
              f"audit_clean={audit == []} cost=${cost:.3f}")

    with open(os.path.join(OUT, "golden_v3_states.jsonl"), "w") as f:
        for s in states_out:
            f.write(json.dumps(s, default=str) + "\n")

    n_ok = sum(1 for r in rows if r["status"] == "OK")
    summary = {
        "study": "golden_v3_smoke", "generation_id": V3.GENERATION_ID,
        "n_fixtures": len(rows), "n_ok": n_ok,
        "n_rejected": sum(1 for r in rows if r["status"] == "LLM_STATE_REJECTED"),
        "n_unavailable": sum(1 for r in rows if r["status"] == "LLM_STATE_UNAVAILABLE"),
        "all_requests_audit_clean": all(r["request_audit_clean"] for r in rows),
        "total_unknown": sum(r["n_unknown"] for r in rows),
        "total_conflicted": sum(r["n_conflicted"] for r in rows if isinstance(r["n_conflicted"], int)),
        "cost_usd": round(total_cost, 4),
        "created_unix": int(time.time()),
        "rows": rows,
    }
    json.dump(summary, open(os.path.join(OUT, "golden_v3_summary.json"), "w"),
              indent=2, default=str)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    run(n=n)
