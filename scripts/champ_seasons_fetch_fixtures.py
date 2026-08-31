"""Fetch all fixture pages (regular, finished) for given Championship season IDs.
No odds. Cached raw; page1 etc reused if already cached. Reports per-team balance."""
import os, sys, json, statistics
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

COMP = "comp_8321"
SEASONS = {"24_25": "sn_2930227", "23_24": "sn_343481"}


def fetch_season(season_id):
    page1, _ = api.get_json("/football/matches",
        params={"competition_id": COMP, "season_id": season_id, "stage": "regular",
                "status": "finished", "per_page": 100, "page": 1},
        cache_key=f"fixtures_{season_id}_regular_finished_p1")
    total_pages = page1.get("meta", {}).get("total_pages", 1)
    total = page1.get("meta", {}).get("total")
    fx = list(page1.get("data", []))
    for p in range(2, total_pages + 1):
        pg, _ = api.get_json("/football/matches",
            params={"competition_id": COMP, "season_id": season_id, "stage": "regular",
                    "status": "finished", "per_page": 100, "page": p},
            cache_key=f"fixtures_{season_id}_regular_finished_p{p}")
        fx.extend(pg.get("data", []))
    seen = {m["id"]: m for m in fx}
    fx = list(seen.values())
    # per-team appearance counts (full season = inherently balanced)
    counts = defaultdict(int)
    for m in fx:
        counts[m["home_team"]["name"]] += 1
        counts[m["away_team"]["name"]] += 1
    vals = sorted(counts.values())
    with open(f"{api.CACHE_DIR}/_all_fixtures_{season_id}.json", "w") as f:
        json.dump({"season_id": season_id, "n": len(fx), "fixtures": fx}, f, indent=2)
    return fx, total, total_pages, counts, vals


def main():
    for label, sid in SEASONS.items():
        fx, total, pages, counts, vals = fetch_season(sid)
        print(f"\n{label} ({sid}): fetched {len(fx)} finished regular fixtures "
              f"(meta total={total}, pages={pages})")
        print(f"  teams={len(counts)}  per-team apps: min={min(vals)} max={max(vals)} "
              f"median={int(statistics.median(vals))}")
    snap = api.budget_snapshot()
    print(f"\nlive requests this run={api.live_requests_made()}  cumulative={snap['total_live_requests']}  "
          f"monthly_remaining={snap['last_monthly_remaining']}")


if __name__ == "__main__":
    main()
