"""Cache /stats for ALL 552 season fixtures (odds NOT fetched here — odds remain
only on the balanced 200). Gives the model full per-team history for point-in-time
rolling windows. Cache-first; only uncached matches cost budget."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

SEASON = "sn_3064530"
CACHE = api.CACHE_DIR


def main():
    fx = json.load(open(f"{CACHE}/_all_fixtures_{SEASON}.json"))["fixtures"]
    ids = [m["id"] for m in fx]
    already = sum(1 for mid in ids if os.path.exists(f"{CACHE}/stats_{mid}.json"))
    print(f"{len(ids)} fixtures; stats already cached for {already}; fetching remainder ...")
    n_ok = 0
    missing = []
    for i, mid in enumerate(ids):
        sd, _ = api.get_json(f"/football/matches/{mid}/stats",
                             cache_key=f"stats_{mid}", allow_status=(200, 404))
        if sd is not None:
            n_ok += 1
        else:
            missing.append(mid)
        if (i + 1) % 50 == 0:
            snap = api.budget_snapshot()
            print(f"  {i+1}/{len(ids)} | cumulative live req={snap['total_live_requests']} "
                  f"| monthly_remaining={snap['last_monthly_remaining']}")
    snap = api.budget_snapshot()
    print(f"\nDONE. stats ok={n_ok}/{len(ids)}  missing={len(missing)}")
    print(f"cumulative live req={snap['total_live_requests']}  monthly_remaining={snap['last_monthly_remaining']}")
    if missing:
        print("missing:", missing[:15])
    json.dump({"n": len(ids), "n_ok": n_ok, "missing": missing,
               "cumulative_live_requests": snap["total_live_requests"],
               "monthly_remaining": snap["last_monthly_remaining"]},
              open(f"{CACHE}/_all_stats_summary.json", "w"), indent=2)


if __name__ == "__main__":
    main()
