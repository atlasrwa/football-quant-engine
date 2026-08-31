"""
Step 2 — cache stats + odds for the balanced 200-match Championship slice.
2 requests/match (stats + bet365 odds). All raw, cache-first (re-runs cost 0).
Also computes the FootyStats crosswalk join rate (offline, no API) for reporting.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

SEASON = "sn_3064530"
CACHE = api.CACHE_DIR


def main():
    sel = json.load(open(f"{CACHE}/_selected_balanced_{SEASON}.json"))
    ids = sel["selected_match_ids"]
    print(f"caching stats+odds for {len(ids)} matches ...")

    n_stats, n_odds, n_b365 = 0, 0, 0
    missing_stats, missing_odds = [], []
    for i, mid in enumerate(ids):
        sd, _ = api.get_json(f"/football/matches/{mid}/stats",
                             cache_key=f"stats_{mid}", allow_status=(200, 404))
        if sd is not None:
            n_stats += 1
        else:
            missing_stats.append(mid)
        od, _ = api.get_json(f"/football/matches/{mid}/odds",
                             params={"bookmaker": "bet365"},
                             cache_key=f"odds_{mid}", allow_status=(200, 404))
        if od is not None:
            n_odds += 1
            books = od.get("data", {}).get("bookmakers", [])
            if any(str(b.get("bookmaker","")).lower().startswith("bet365") for b in books):
                n_b365 += 1
            else:
                missing_odds.append(mid)
        else:
            missing_odds.append(mid)
        if (i + 1) % 40 == 0:
            snap = api.budget_snapshot()
            print(f"  {i+1}/{len(ids)} done | cumulative live req={snap['total_live_requests']} "
                  f"| monthly_remaining={snap['last_monthly_remaining']}")

    snap = api.budget_snapshot()
    print(f"\nDONE. stats ok={n_stats}/{len(ids)}  odds ok={n_odds}/{len(ids)}  "
          f"bet365 present={n_b365}/{len(ids)}")
    print(f"live requests this run={api.live_requests_made()}  cumulative={snap['total_live_requests']}  "
          f"monthly_remaining={snap['last_monthly_remaining']}")
    if missing_stats:
        print(f"missing stats ({len(missing_stats)}): {missing_stats[:10]}")
    if missing_odds:
        print(f"missing/other odds ({len(missing_odds)}): {missing_odds[:10]}")

    out = {"n_selected": len(ids), "n_stats": n_stats, "n_odds": n_odds,
           "n_bet365": n_b365, "missing_stats": missing_stats, "missing_odds": missing_odds,
           "cumulative_live_requests": snap["total_live_requests"],
           "monthly_remaining": snap["last_monthly_remaining"]}
    with open(f"{CACHE}/_step2_cache_summary.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
