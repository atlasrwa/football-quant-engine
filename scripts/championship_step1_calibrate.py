"""
Step 1 — Championship (comp_8321) calibration pull (~20 requests).

Confirms BEFORE committing bulk budget:
  * Odds coverage: which Bet365 markets/lines exist, coverage rate, overround per market.
  * Field population: which of the ~45 stat fields are populated for Championship.
  * Actual request cost per match.

Aborts (via client) on any API error. Everything cached raw. Re-runs cost 0.
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

COMP = "comp_8321"
N_SAMPLE = 10


def leaf_stat_keys(stats_data):
    """Walk the /stats 'data' tree; return dict group.stat -> populated? (all/1h/2h)."""
    populated = {}
    data = stats_data.get("data", {})
    for group, gval in data.items():
        if group == "match_id":
            continue
        if group == "np_expected_goals":
            # top-level MatchStatItem
            populated["np_expected_goals"] = _item_pop(gval)
            continue
        if not isinstance(gval, dict):
            continue
        for stat, sval in gval.items():
            populated[f"{group}.{stat}"] = _item_pop(sval)
    return populated


def _item_pop(item):
    """A MatchStatItem is populated if its 'all' period has non-null home/away."""
    if not isinstance(item, dict):
        return False
    allv = item.get("all")
    if not isinstance(allv, dict):
        return False
    return allv.get("home") is not None and allv.get("away") is not None


def overround_two_way(over_odds, under_odds):
    return (1.0 / over_odds) + (1.0 / under_odds) - 1.0


def main():
    print("=" * 78)
    print("STEP 1 — Championship calibration (comp_8321)")
    print("=" * 78)

    # 1) health (1 req) — cheap confirmation of auth + connectivity
    health, meta = api.get_json("/health", cache_key="health")
    print(f"health: {health.get('status')}  (from_cache={meta['from_cache']})")
    if not meta["from_cache"]:
        print(f"  quota after health: monthly_remaining={meta['quota']['monthly_remaining']} "
              f"ratelimit_remaining={meta['quota']['ratelimit_remaining']} "
              f"monthly_limit={meta['quota']['monthly_limit']}")

    # 2) seasons for Championship (1 req)
    seasons, meta = api.get_json(f"/football/competitions/{COMP}/seasons",
                                 cache_key="seasons_comp_8321")
    slist = seasons.get("data", [])
    print(f"\nSeasons for {COMP}: {len(slist)}")
    for s in slist[:8]:
        print(f"  {s['id']}  {s['name']}  year={s['year']} current={s.get('is_current')}")

    # Choose most recent COMPLETED season: newest with is_current == False.
    # (Newest-first ordering per docs.)
    chosen = None
    for s in slist:
        if not s.get("is_current"):
            chosen = s
            break
    if chosen is None:
        chosen = slist[0]
    season_id = chosen["id"]
    print(f"\nChosen season (most recent completed): {season_id} {chosen['name']}")

    # 3) fixture list page 1, regular stage, finished (1 req)
    fixtures, meta = api.get_json(
        "/football/matches",
        params={"competition_id": COMP, "season_id": season_id,
                "stage": "regular", "status": "finished",
                "per_page": 100, "page": 1},
        cache_key=f"fixtures_{season_id}_regular_finished_p1")
    fx = fixtures.get("data", [])
    fmeta = fixtures.get("meta", {})
    print(f"Fixtures page1: {len(fx)} of total={fmeta.get('total')} "
          f"(total_pages={fmeta.get('total_pages')})")

    # Sample: spread across the page (every k-th) to avoid clustering in one week.
    finished = [m for m in fx if m.get("status") == "finished"]
    if len(finished) < N_SAMPLE:
        sample = finished
    else:
        step = len(finished) // N_SAMPLE
        sample = [finished[i * step] for i in range(N_SAMPLE)]
    print(f"Sampling {len(sample)} finished matches for calibration.\n")

    # 4) per match: stats + odds (2 req each)
    field_pop_counts = defaultdict(int)   # field -> # matches populated
    n_stats_ok = 0
    odds_market_counts = defaultdict(int)  # market -> # matches Bet365 offers it
    odds_line_overrounds = defaultdict(list)  # (market,line) -> [overround...]
    n_odds_ok = 0
    n_bet365 = 0
    other_bookmakers = defaultdict(int)
    sample_ids = []

    for m in sample:
        mid = m["id"]
        sample_ids.append(mid)
        # stats
        sd, _ = api.get_json(f"/football/matches/{mid}/stats",
                             cache_key=f"stats_{mid}", allow_status=(200, 404))
        if sd is not None:
            n_stats_ok += 1
            pop = leaf_stat_keys(sd)
            for k, v in pop.items():
                if v:
                    field_pop_counts[k] += 1
        # odds (bet365 only to save nothing extra; still 1 request)
        od, _ = api.get_json(f"/football/matches/{mid}/odds",
                            params={"bookmaker": "bet365"},
                            cache_key=f"odds_{mid}", allow_status=(200, 404))
        if od is not None:
            books = od.get("data", {}).get("bookmakers", [])
            b365 = None
            for b in books:
                other_bookmakers[b.get("bookmaker")] += 1
                if str(b.get("bookmaker", "")).lower().startswith("bet365"):
                    b365 = b
            if b365 is not None:
                n_bet365 += 1
                n_odds_ok += 1
                markets = b365.get("markets", {})
                for mkt in ("total_goals", "total_cards", "match_corners", "btts"):
                    if mkt in markets and markets[mkt]:
                        odds_market_counts[mkt] += 1
                # overround for O/U markets
                for mkt in ("total_goals", "total_cards", "match_corners"):
                    lines = markets.get(mkt, {})
                    if isinstance(lines, dict):
                        for line, sides in lines.items():
                            try:
                                o = float(sides["over"]["last_seen"])
                                u = float(sides["under"]["last_seen"])
                                if o > 1 and u > 1:
                                    odds_line_overrounds[(mkt, line)].append(
                                        overround_two_way(o, u))
                            except (KeyError, TypeError, ValueError):
                                continue

    # ---- Report ----
    n = len(sample)
    print("-" * 78)
    print(f"ODDS COVERAGE (Bet365) over {n} sampled matches")
    print(f"  matches with an odds response: {n_odds_ok}/{n}")
    print(f"  matches with Bet365 present:   {n_bet365}/{n}")
    print(f"  bookmakers seen: {dict(other_bookmakers)}")
    print("  market coverage (Bet365 offers it):")
    for mkt in ("total_goals", "total_cards", "match_corners", "btts"):
        print(f"    {mkt:14s}: {odds_market_counts[mkt]}/{n}")
    print("  overround by (market, line)  [mean over sampled matches, n]:")
    for (mkt, line), vals in sorted(odds_line_overrounds.items()):
        import statistics
        print(f"    {mkt:14s} {line:>5}: {statistics.mean(vals)*100:5.2f}%  (n={len(vals)})")

    print("-" * 78)
    print(f"FIELD POPULATION over {n_stats_ok} matches with stats")
    print("  (# matches where field's ALL-period home&away are non-null)")
    for k in sorted(field_pop_counts.keys()):
        print(f"    {k:40s}: {field_pop_counts[k]}/{n_stats_ok}")
    # Explicitly flag the ~24 richer fields the brief cares about
    watch = [
        "shots.blocked_shots", "shots.shots_inside_box", "shots.shots_outside_box",
        "attack.big_chances_missed", "attack.touches_in_penalty_area",
        "attack.fouled_in_final_third", "passes.accurate_crosses",
        "passes.accurate_long_balls", "passes.final_third_entries",
        "duels.duels_won_percentage", "duels.dispossessed", "duels.dribbles_percentage",
        "duels.ground_duels_percentage", "duels.aerial_duels_percentage",
        "defending.tackles", "defending.tackles_won_percentage", "defending.interceptions",
        "defending.clearances", "defending.ball_recoveries",
        "goalkeeping.saves", "goalkeeping.goal_kicks", "goalkeeping.goals_prevented",
        "goalkeeping.high_claims", "np_expected_goals",
        "overview.big_chances",
    ]
    print("\n  RICHER FIELDS (the ~24 not in FootyStats) — populated count:")
    for k in watch:
        print(f"    {k:40s}: {field_pop_counts.get(k,0)}/{n_stats_ok}")

    print("-" * 78)
    snap = api.budget_snapshot()
    print(f"REQUEST COST")
    print(f"  live requests this run: {api.live_requests_made()}")
    print(f"  cumulative live requests (all runs): {snap['total_live_requests']}")
    print(f"  last monthly_remaining seen: {snap['last_monthly_remaining']}")
    print(f"  per-match cost = 2 (1 stats + 1 odds)")

    out = {
        "season_id": season_id, "season_name": chosen["name"],
        "fixtures_total": fmeta.get("total"), "fixtures_total_pages": fmeta.get("total_pages"),
        "sample_ids": sample_ids,
        "n_sample": n, "n_stats_ok": n_stats_ok, "n_bet365": n_bet365,
        "odds_market_counts": dict(odds_market_counts),
        "overround_by_line": {f"{m}@{l}": (sum(v)/len(v)) for (m, l), v in odds_line_overrounds.items()},
        "field_pop_counts": dict(field_pop_counts),
        "live_requests_this_run": api.live_requests_made(),
        "cumulative_live_requests": snap["total_live_requests"],
        "last_monthly_remaining": snap["last_monthly_remaining"],
    }
    with open(f"{api.CACHE_DIR}/_step1_calibration_summary.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved summary: {api.CACHE_DIR}/_step1_calibration_summary.json")


if __name__ == "__main__":
    main()
