"""
Multi-league fetcher for the multi-source discovery task (COMMITTED, parameterized).

Fetches fixtures + per-match /stats for a competition/season from TheStatsAPI, via
the cache-first client (scripts/thestatsapi_client.py). No odds here (Step 5 pulls
odds separately, and only where a market exists). Raw responses cached UNMODIFIED.

Usage:
  python scripts/multisrc_fetch.py seasons  <comp_id>
  python scripts/multisrc_fetch.py fixtures <comp_id> <season_id> <league_tag>
  python scripts/multisrc_fetch.py stats    <comp_id> <season_id> <league_tag> [limit]

league_tag namespaces cache keys (e.g. ligue2, laliga2) so multiple leagues coexist
in the single client CACHE_DIR. All analysis reads these cached files offline.

Budget rails come from the client (THESTATS_MAX_REQUESTS local cap, THESTATS_MIN_INTERVAL
pacing for the 12 req/min burst limit). Cache-first => re-runs cost zero.
"""
import sys, json, os
import thestatsapi_client as api

CACHE = api.CACHE_DIR


def fetch_seasons(comp):
    data, meta = api.get_json(f"/football/competitions/{comp}/seasons",
                              cache_key=f"seasons_{comp}")
    seasons = data.get("data", data) if isinstance(data, dict) else data
    print(f"[{comp}] seasons (from_cache={meta.get('from_cache')}):")
    for s in seasons:
        print(f"  {s.get('id')}  {s.get('name')}  year={s.get('year')} "
              f"start={s.get('start_year')} end={s.get('end_year')} "
              f"current={s.get('is_current')}")
    return seasons


def fetch_fixtures(comp, season, tag):
    """Paginate finished regular-stage fixtures; write _all_fixtures_<tag>_<season>.json."""
    all_fx = {}
    page = 1
    while True:
        data, meta = api.get_json(
            "/football/matches",
            params={"competition_id": comp, "season_id": season,
                    "stage": "regular", "status": "finished",
                    "per_page": 100, "page": page},
            cache_key=f"{tag}_matches_{season}_p{page}")
        fx = (data or {}).get("data", []) or []
        for f in fx:
            all_fx[f["id"]] = f
        meta_pg = (data or {}).get("metadata", {}) or (data or {}).get("meta", {}) or {}
        total_pages = meta_pg.get("total_pages") or meta_pg.get("last_page") or 1
        print(f"[{tag} {season}] page {page}/{total_pages}: +{len(fx)} (total {len(all_fx)})"
              f" from_cache={meta.get('from_cache')}")
        if page >= int(total_pages) or not fx:
            break
        page += 1
    out = {"comp": comp, "season_id": season, "tag": tag,
           "n": len(all_fx), "fixtures": list(all_fx.values())}
    path = f"{CACHE}/_all_fixtures_{tag}_{season}.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"[{tag} {season}] wrote {len(all_fx)} fixtures -> {path}")
    return out


def fetch_stats(comp, season, tag, limit=None):
    fx = json.load(open(f"{CACHE}/_all_fixtures_{tag}_{season}.json"))["fixtures"]
    if limit:
        fx = fx[:int(limit)]
    got = 0; cached = 0
    for i, f in enumerate(fx):
        mid = f["id"]
        ck = f"{tag}_stats_{mid}"
        was_cached = api.is_cached(ck)
        data, meta = api.get_json(f"/football/matches/{mid}/stats", cache_key=ck,
                                  allow_status=(200, 404))
        if meta.get("from_cache"):
            cached += 1
        else:
            got += 1
        if (i + 1) % 25 == 0:
            print(f"[{tag} {season}] {i+1}/{len(fx)} stats (live={got} cached={cached}) "
                  f"budget_remaining={api.budget_snapshot().get('last_monthly_remaining')}")
    print(f"[{tag} {season}] stats done: live={got} cached={cached} total={len(fx)}")
    return got, cached


def fetch_odds(comp, season, tag, match_ids):
    """Fetch Bet365 odds for a specific list of match ids (balanced selection).
    Cache key <tag>_odds_<mid>. Cache-first. Reports coverage."""
    got = 0; cached = 0; missing = 0
    for i, mid in enumerate(match_ids):
        ck = f"{tag}_odds_{mid}"
        data, meta = api.get_json(f"/football/matches/{mid}/odds",
                                  params={"bookmaker": "bet365"},
                                  cache_key=ck, allow_status=(200, 404))
        if meta.get("http_status") == 404 or data is None:
            missing += 1
        elif meta.get("from_cache"):
            cached += 1
        else:
            got += 1
        if (i + 1) % 25 == 0:
            print(f"[{tag} {season}] {i+1}/{len(match_ids)} odds (live={got} cached={cached} "
                  f"missing={missing}) remaining={api.budget_snapshot().get('last_monthly_remaining')}")
    print(f"[{tag} {season}] odds done: live={got} cached={cached} missing={missing} "
          f"total={len(match_ids)}")
    return got, cached, missing


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "seasons":
        fetch_seasons(sys.argv[2])
    elif cmd == "fixtures":
        fetch_fixtures(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "stats":
        limit = sys.argv[5] if len(sys.argv) > 5 else None
        fetch_stats(sys.argv[2], sys.argv[3], sys.argv[4], limit)
    elif cmd == "odds":
        # odds <comp> <season> <tag> <ids_json_file>
        ids = json.load(open(sys.argv[5]))
        fetch_odds(sys.argv[2], sys.argv[3], sys.argv[4], ids)
    else:
        print("unknown command", cmd); sys.exit(1)
    print("budget:", api.budget_snapshot())
