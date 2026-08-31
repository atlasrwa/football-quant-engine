"""Cache /stats for ALL fixtures in Championship 24/25 + 23/24. No odds.
Cache-first; only uncached matches cost budget. Paced by client."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

SEASONS = ["sn_2930227", "sn_343481"]


def main():
    all_ids = []
    for sid in SEASONS:
        fx = json.load(open(f"{api.CACHE_DIR}/_all_fixtures_{sid}.json"))["fixtures"]
        all_ids += [(sid, m["id"]) for m in fx]
    already = sum(1 for _, mid in all_ids if os.path.exists(f"{api.CACHE_DIR}/stats_{mid}.json"))
    print(f"{len(all_ids)} fixtures across 2 seasons; stats already cached for {already}")
    n_ok = 0
    missing = []
    for i, (sid, mid) in enumerate(all_ids):
        sd, _ = api.get_json(f"/football/matches/{mid}/stats",
                             cache_key=f"stats_{mid}", allow_status=(200, 404))
        if sd is not None:
            n_ok += 1
        else:
            missing.append(mid)
        if (i + 1) % 50 == 0:
            snap = api.budget_snapshot()
            print(f"  {i+1}/{len(all_ids)} | cumulative={snap['total_live_requests']} "
                  f"monthly_remaining={snap['last_monthly_remaining']}")
    snap = api.budget_snapshot()
    print(f"\nDONE. stats ok={n_ok}/{len(all_ids)} missing={len(missing)}")
    print(f"cumulative={snap['total_live_requests']} monthly_remaining={snap['last_monthly_remaining']}")
    json.dump({"n": len(all_ids), "n_ok": n_ok, "missing": missing,
               "cumulative_live_requests": snap["total_live_requests"],
               "monthly_remaining": snap["last_monthly_remaining"]},
              open(f"{api.CACHE_DIR}/_seasons_stats_summary.json", "w"), indent=2)


if __name__ == "__main__":
    main()
