"""
Coverage Matrix Audit — bounded LIVE probe for the questions cache cannot answer:
  1. Do paddy-power and betmgm-uk price per-side markets? (never probed)
  2. Does per-side coverage exist in EPL as well as Championship?

Cache-first via thestatsapi_client (cma_odds_{mid}_{book}); pre-spend cap gate.
Writes data/coverage_audit/live_probe.json.
"""
from __future__ import annotations
import json, sys
sys.path.insert(0, "/home/ubuntu/scripts")
sys.path.insert(0, "/home/ubuntu")
import thestatsapi_client as api
import coverage_audit_common as cac
import coverage_audit_markets as mk

FIXTURE_LIST = "/home/ubuntu/data/thestatsapi/championship/_pilotC_fixture_list.json"
COMPS = {"comp_8321": "Championship", "comp_3039": "EPL"}
# The two never-probed books, plus bet365 to confirm per-side in EPL.
PROBE = {
    "Championship": {"books": ["paddy-power", "betmgm-uk"], "n": 10},
    "EPL": {"books": ["paddy-power", "betmgm-uk", "bet365"], "n": 10},
}


def select_fixtures():
    fx = json.load(open(FIXTURE_LIST))
    meta = fx["meta"]
    out = {}
    for comp, league in COMPS.items():
        ids = [mid for mid, mm in meta.items()
               if mm.get("comp") == comp and mm.get("status") in ("scheduled", "live")]
        out[league] = ids
    return out


def plan_calls(fixtures):
    plan = []
    for league, cfg in PROBE.items():
        ids = fixtures.get(league, [])[: cfg["n"]]
        for mid in ids:
            for book in cfg["books"]:
                ck = f"cma_odds_{mid}_{book}"
                if not api.is_cached(ck):
                    plan.append((mid, book, league, ck))
    return plan


def run():
    cac.snapshot_budget("live_probe_before")
    fixtures = select_fixtures()
    plan = plan_calls(fixtures)
    print(f"planned live calls: {len(plan)}")
    cap = int(__import__("os").environ.get("THESTATS_MAX_REQUESTS", "425"))
    already = api.live_requests_made()
    if len(plan) > cap:
        print(f"FLAG: planned {len(plan)} exceeds cap {cap}. Raise THESTATS_MAX_REQUESTS "
              f"or split. Aborting before spend.")
        return
    results = {"probe_config": PROBE, "by_league_book": {}, "capped": False}
    tally = {}  # (league,book) -> {"n":0, "per_side_present":0, "markets":set()}
    for mid, book, league, ck in plan:
        try:
            data, m = api.get_json(f"/football/matches/{mid}/odds",
                                   params={"bookmaker": book}, cache_key=ck,
                                   allow_status=(200, 404, 422))
        except SystemExit:
            print("cap reached mid-run; writing partial.")
            results["capped"] = True
            break
        key = (league, book)
        t = tally.setdefault(key, {"n": 0, "per_side_present": 0, "markets": set(),
                                    "per_side_markets": set()})
        t["n"] += 1
        bks = (data or {}).get("data", {}).get("bookmakers", []) if data else []
        for b in bks:
            markets = b.get("markets", {})
            if not isinstance(markets, dict):
                continue
            has_ps = False
            for name, body in markets.items():
                t["markets"].add(name)
                kind = mk.classify_market(name, body)
                if kind == "per_side_stat" or any(h in name for h in mk.PER_SIDE_STAT_HINTS):
                    t["per_side_markets"].add(name); has_ps = True
            if has_ps:
                t["per_side_present"] += 1
    for (league, book), t in tally.items():
        results["by_league_book"].setdefault(league, {})[book] = {
            "fixtures_probed": t["n"],
            "per_side_coverage": cac.rate(t["per_side_present"], t["n"]),
            "per_side_markets": sorted(t["per_side_markets"]),
            "all_markets": sorted(t["markets"]),
        }
    cac.write_artifact("live_probe.json", results)
    print(json.dumps({lg: {bk: {"n": v["fixtures_probed"],
                                "per_side": v["per_side_markets"]}
                           for bk, v in books.items()}
                      for lg, books in results["by_league_book"].items()}, indent=2))
    cac.snapshot_budget("live_probe_after")
    print("live requests made this run:", api.live_requests_made())


if __name__ == "__main__":
    run()
