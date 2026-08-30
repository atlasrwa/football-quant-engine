"""
In-play reconstruction — Step 1: inventory cached data (ZERO requests).

Determines, without any API call:
  - which matches have /stats cached (reconciliation input ready)
  - which have timeline / shotmap cached (reconstruction input ready)
  - counts by league and season
  - resulting cost to reconstruct each match: 0/1/2/3 additional requests

Cache locations inspected (read-only):
  data/thestatsapi/championship/  -> 3 seasons Championship + LaLiga2 + Ligue2 stats
  data/thestatsapi/inplay/        -> feasibility-check timeline/shotmap/stats
"""
import json
import glob
import os
import re
from collections import defaultdict

CH = "/home/ubuntu/data/thestatsapi/championship"
IP = "/home/ubuntu/data/thestatsapi/inplay"
OUT = "/home/ubuntu/data/thestatsapi/inplay/_recon_inventory.json"

# Map stats-file prefixes to leagues
PREFIX_LEAGUE = {"stats_mt": "Championship", "laliga2_stats": "LaLiga2", "ligue2_stats": "Ligue2"}


def mid_from(fn, prefix):
    m = re.search(r"(mt_\d+)", fn)
    return m.group(1) if m else None


def load_fixtures():
    """Load fixture lists to map match_id -> (league, season) and team ids for balance."""
    fx = {}
    # championship fixtures_sn_*, laliga2/ligue2 *_matches_sn_*
    for f in glob.glob(f"{CH}/fixtures_sn_*_p*.json") + glob.glob(f"{CH}/*_matches_sn_*_p*.json"):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        rows = d.get("data", d) if isinstance(d, dict) else d
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        for m in (rows or []):
            if not isinstance(m, dict) or "id" not in m:
                continue
            fx[m["id"]] = {
                "season_id": m.get("season_id"),
                "competition_id": m.get("competition_id"),
                "home_id": (m.get("home_team") or {}).get("id"),
                "away_id": (m.get("away_team") or {}).get("id"),
                "utc_date": m.get("utc_date"),
                "status": m.get("status"),
            }
    return fx


def main():
    # 1. stats cached
    stats_ids = defaultdict(set)  # league -> set(mid)
    for prefix, league in PREFIX_LEAGUE.items():
        for f in glob.glob(f"{CH}/{prefix}_mt_*.json") if prefix != "stats_mt" else glob.glob(f"{CH}/stats_mt_*.json"):
            mid = mid_from(os.path.basename(f), prefix)
            if mid:
                stats_ids[league].add(mid)

    # 2. timeline / shotmap cached (only inplay dir has them)
    tl_ids, sm_ids = set(), set()
    for f in glob.glob(f"{IP}/*timeline*mt_*.json"):
        mid = mid_from(os.path.basename(f), "")
        if mid:
            tl_ids.add(mid)
    for f in glob.glob(f"{IP}/*shotmap*mt_*.json"):
        mid = mid_from(os.path.basename(f), "")
        if mid:
            sm_ids.add(mid)

    fx = load_fixtures()

    report = {"by_league": {}, "totals": {}}
    all_stats = set()
    for league, ids in stats_ids.items():
        all_stats |= ids
        # season breakdown via fixtures
        by_season = defaultdict(int)
        for mid in ids:
            s = (fx.get(mid) or {}).get("season_id", "unknown")
            by_season[s] += 1
        report["by_league"][league] = {
            "matches_with_stats": len(ids),
            "by_season": dict(by_season),
            "with_timeline_cached": len(ids & tl_ids),
            "with_shotmap_cached": len(ids & sm_ids),
        }

    # cost to reconstruct each match with stats: needs timeline(+shotmap) if missing
    cost0 = cost1 = cost2 = 0
    for mid in all_stats:
        need = 0
        if mid not in tl_ids:
            need += 1
        if mid not in sm_ids:
            need += 1
        if need == 0:
            cost0 += 1
        elif need == 1:
            cost1 += 1
        else:
            cost2 += 1

    report["totals"] = {
        "distinct_matches_with_stats": len(all_stats),
        "with_timeline_cached": len(all_stats & tl_ids),
        "with_shotmap_cached": len(all_stats & sm_ids),
        "reconstructable_zero_additional_requests": cost0,
        "need_1_additional_request": cost1,
        "need_2_additional_requests (timeline+shotmap)": cost2,
        "note": "stats already cached for all these; /stats reconciliation input is free. "
                "timeline+shotmap are NOT cached for the corpus (only ~feasibility matches).",
        "fixtures_indexed": len(fx),
    }
    json.dump(report, open(OUT, "w"), indent=2)

    print("=" * 70)
    print("STEP 1 — RECONSTRUCTION INVENTORY (zero requests)")
    print("=" * 70)
    for league, r in report["by_league"].items():
        print(f"\n{league}: {r['matches_with_stats']} matches with /stats")
        print(f"   by season: {r['by_season']}")
        print(f"   timeline cached: {r['with_timeline_cached']}  shotmap cached: {r['with_shotmap_cached']}")
    print("\nTOTALS:")
    for k, v in report["totals"].items():
        print(f"  {k}: {v}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
