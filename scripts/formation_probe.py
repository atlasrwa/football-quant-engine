"""
FORMATION PROBE (Step 1) — cheap coverage check + single sample lineup.

Gates the bulk pull. Two live requests at most:
  1. GET /coverage/leagues?data_type=lineups   -> per-competition lineup coverage
  2. GET /football/matches/{sample}/lineups     -> confirm the response contract
     (does it actually carry "formation" for both teams?)

Everything is cached via thestatsapi_client (cache-first, quota-tracked). Re-runs
cost zero. Zero analysis here — just contract confirmation and coverage reporting.
"""
import sys, json, os
sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as api
import multisrc_corpus as corpus

# Corpus competition ids we care about, by league tag.
CORPUS_COMPS = {tag: corpus.LEAGUES[tag]["comp"] for tag in corpus.LEAGUES}


def coverage_lineups():
    all_entries = []
    page = 1
    while True:
        data, meta = api.get_json("/coverage/leagues",
                                  params={"data_type": "lineups", "page": page, "per_page": 100},
                                  cache_key=f"coverage_leagues_lineups_p{page}",
                                  allow_status=(200, 404))
        print(f"[coverage] page={page} from_cache={meta.get('from_cache')} status={meta.get('http_status')}")
        if data is None:
            break
        entries = data.get("data", []) if isinstance(data, dict) else data
        all_entries.extend(entries)
        m = data.get("meta", {}) if isinstance(data, dict) else {}
        tp = m.get("total_pages", 1)
        if page >= tp:
            break
        page += 1
    return {"data": all_entries}


def sample_lineup():
    # pick one Championship fixture id from the cached fixtures
    fx = corpus.load_fixtures("champ", corpus.LEAGUES["champ"]["seasons"][1])
    mid = fx[0]["id"]
    data, meta = api.get_json(f"/football/matches/{mid}/lineups",
                              cache_key=f"lineups_{mid}",
                              allow_status=(200, 404))
    print(f"[sample lineup] match={mid} from_cache={meta.get('from_cache')} "
          f"status={meta.get('http_status')}")
    return mid, data


def main():
    print("=" * 78)
    print("FORMATION PROBE — coverage + sample lineup contract (Step 1)")
    print("=" * 78)
    print("corpus competitions:", CORPUS_COMPS)

    cov = coverage_lineups()
    if cov is not None:
        print("\n--- raw coverage payload (top-level shape) ---")
        if isinstance(cov, dict):
            print("keys:", list(cov.keys()))
        # dump for offline inspection
        json.dump(cov, open("/home/ubuntu/data/results/formation_coverage_raw.json", "w"), indent=2)
        print("saved raw coverage -> data/results/formation_coverage_raw.json")

    mid, lu = sample_lineup()
    if lu is not None:
        print("\n--- raw sample lineup (top-level shape) ---")
        if isinstance(lu, dict):
            print("keys:", list(lu.keys()))
            print(json.dumps(lu, indent=2)[:2500])
        json.dump(lu, open("/home/ubuntu/data/results/formation_sample_lineup_raw.json", "w"), indent=2)
        print("\nsaved raw sample -> data/results/formation_sample_lineup_raw.json")

    print("\nlive requests this run:", api.live_requests_made())
    print("budget:", api.budget_snapshot())


if __name__ == "__main__":
    main()
