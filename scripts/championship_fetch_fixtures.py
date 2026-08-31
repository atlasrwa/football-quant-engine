"""Fetch all fixture pages for the chosen Championship season (regular, finished).
Pages 1..N cached raw. Page 1 already cached by Step 1 (costs 0 to re-read)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

COMP = "comp_8321"
SEASON = "sn_3064530"

def main():
    page1, _ = api.get_json("/football/matches",
        params={"competition_id": COMP, "season_id": SEASON, "stage": "regular",
                "status": "finished", "per_page": 100, "page": 1},
        cache_key=f"fixtures_{SEASON}_regular_finished_p1")
    total_pages = page1.get("meta", {}).get("total_pages", 1)
    all_fx = list(page1.get("data", []))
    for p in range(2, total_pages + 1):
        pg, _ = api.get_json("/football/matches",
            params={"competition_id": COMP, "season_id": SEASON, "stage": "regular",
                    "status": "finished", "per_page": 100, "page": p},
            cache_key=f"fixtures_{SEASON}_regular_finished_p{p}")
        all_fx.extend(pg.get("data", []))
    # de-dup by id
    seen = {}
    for m in all_fx:
        seen[m["id"]] = m
    fx = list(seen.values())
    print(f"total fixtures fetched: {len(fx)} (pages={total_pages})")
    print(f"live requests this run: {api.live_requests_made()}  cumulative: {api.budget_snapshot()['total_live_requests']}")
    # save consolidated list for offline selection
    with open(f"{api.CACHE_DIR}/_all_fixtures_{SEASON}.json", "w") as f:
        json.dump({"season_id": SEASON, "n": len(fx), "fixtures": fx}, f, indent=2)
    print(f"saved consolidated fixture list: _all_fixtures_{SEASON}.json")

if __name__ == "__main__":
    main()
