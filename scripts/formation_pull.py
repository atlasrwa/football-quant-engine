"""
FORMATION PULL (Step 2) — balanced sample of ~1000 lineups from the cached corpus.

Discipline (carried forward from prior runs):
  * BALANCED ACROSS LEAGUES — per-league quota, reported.
  * BALANCED PER TEAM — within a league, matches are chosen by round-robin over
    teams so every team appears a comparable number of times. Report min/max/median.
    (Unbalanced sampling produced a confound once in this project.)
  * SPREAD ACROSS THE SEASON CALENDAR — the candidate pool per team is ordered by
    date and we stride through it, so picks are not clustered in one part of a season.
  * CACHE RAW — every response saved unmodified via thestatsapi_client (cache-first);
    all later analysis re-runs offline with zero API calls.

Sampling is DETERMINISTIC given the seed (SEED=20260902), so the exact set of matches
is reproducible and the pull can resume idempotently (cached matches cost nothing).

The candidate pool for each league is its cached fixtures that ALSO have cached
/stats (we need outcomes for the analysis). Selection is done OFFLINE first (no API),
then the chosen match ids are fetched one lineups request each.

Budget rail: THESTATS_MAX_REQUESTS caps live requests; monthly quota is shared with
the Pilot C loop, so the target is ~1000 and the cap is set with a margin.
"""
import sys, os, json, math, random
from collections import defaultdict, OrderedDict

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as api
import multisrc_corpus as corpus

SEED = 20260902
TARGET_TOTAL = 1000

# Per-league quota. Weighted toward the three PRIMARY analysis leagues
# (Championship, La Liga 2, Ligue 2 — the leagues the leak-free baseline is measured
# in) while keeping the three top flights represented. Sums to 1000.
LEAGUE_QUOTA = OrderedDict([
    ("champ",   250),
    ("laliga2", 200),
    ("ligue2",  170),
    ("epl",     140),
    ("laliga",  140),
    ("ligue1",  100),
])

SELECTION_OUT = "/home/ubuntu/data/results/formation_selection.json"


def candidate_pool(tag):
    """Fixtures for a league that have cached /stats, as (match_id, date_unix,
    home_id, away_id, season_id). Sorted by date."""
    pool = []
    for sid in corpus.LEAGUES[tag]["seasons"]:
        try:
            fx = corpus.load_fixtures(tag, sid)
        except FileNotFoundError:
            continue
        for m in fx:
            sp = corpus.stats_path(tag, m["id"])
            if not os.path.exists(sp):
                continue
            score = m.get("score") or {}
            # need a finished match with team ids
            hid = m["home_team"]["id"]; aid = m["away_team"]["id"]
            # date
            from datetime import datetime
            try:
                du = int(datetime.fromisoformat(m["utc_date"].replace("Z", "+00:00")).timestamp())
            except Exception:
                du = 0
            pool.append({"match_id": m["id"], "date_unix": du,
                         "home_id": hid, "away_id": aid, "season_id": sid})
    pool.sort(key=lambda r: r["date_unix"])
    return pool


def balanced_team_select(pool, quota, rng):
    """Select `quota` matches from `pool` (already date-sorted) balancing per-team
    appearances and spreading across the calendar.

    Method: build per-team candidate lists (date-ordered). Repeatedly round-robin
    over teams (in a fixed shuffled order), each time taking that team's next
    not-yet-selected candidate whose pick advances calendar spread (we walk each
    team's list with a stride pointer). Stop at quota or exhaustion.
    """
    if quota >= len(pool):
        return list(pool)  # take all

    # per-team date-ordered candidate indices into pool
    by_team = defaultdict(list)
    for idx, r in enumerate(pool):
        by_team[r["home_id"]].append(idx)
        by_team[r["away_id"]].append(idx)

    teams = list(by_team.keys())
    rng.shuffle(teams)
    # stride pointer per team so we spread across each team's season, not front-load
    ptr = {t: 0 for t in teams}
    selected = set()
    # to spread across calendar per team, choose from evenly spaced positions
    order_within = {}
    for t in teams:
        lst = by_team[t]
        # evenly spaced traversal order (stride) over the team's date-ordered matches
        n = len(lst)
        stride_order = []
        # interleave: 0, n/2, n/4, 3n/4, ... via bit-reversal-ish spread
        step = max(1, n)
        # simple spread: take indices in an order that jumps around the calendar
        idxs = list(range(n))
        # reorder by a low-discrepancy-ish sequence: sort by fractional van der Corput
        def vdc(i, base=2):
            f, r, x = 1.0, 0.0, i
            while x > 0:
                f /= base; r += f * (x % base); x //= base
            return r
        idxs.sort(key=lambda i: vdc(i + 1))
        order_within[t] = [lst[i] for i in idxs]

    progressed = True
    while len(selected) < quota and progressed:
        progressed = False
        for t in teams:
            if len(selected) >= quota:
                break
            lst = order_within[t]
            while ptr[t] < len(lst):
                cand = lst[ptr[t]]
                ptr[t] += 1
                if cand not in selected:
                    selected.add(cand)
                    progressed = True
                    break
    return [pool[i] for i in sorted(selected, key=lambda i: pool[i]["date_unix"])]


def build_selection():
    rng = random.Random(SEED)
    selection = OrderedDict()
    for tag, quota in LEAGUE_QUOTA.items():
        pool = candidate_pool(tag)
        picked = balanced_team_select(pool, quota, rng)
        selection[tag] = picked
        # team balance report
        tc = defaultdict(int)
        for r in picked:
            tc[r["home_id"]] += 1; tc[r["away_id"]] += 1
        vals = sorted(tc.values())
        med = vals[len(vals)//2] if vals else 0
        print(f"[select] {tag:8s} pool={len(pool):5d} picked={len(picked):4d} "
              f"teams={len(tc):3d} apps min/med/max={min(vals) if vals else 0}/{med}/{max(vals) if vals else 0}")
    json.dump({t: [r["match_id"] for r in rows] for t, rows in selection.items()},
              open(SELECTION_OUT, "w"), indent=2)
    print(f"saved selection -> {SELECTION_OUT}")
    return selection


def pull(selection):
    """Fetch lineups for every selected match (cache-first). Reports 404/empty."""
    stats = defaultdict(lambda: {"requested": 0, "ok": 0, "404": 0, "empty": 0,
                                 "both_formations": 0, "from_cache": 0})
    for tag, rows in selection.items():
        for r in rows:
            mid = r["match_id"]
            data, meta = api.get_json(f"/football/matches/{mid}/lineups",
                                      cache_key=f"lineups_{mid}",
                                      allow_status=(200, 404))
            s = stats[tag]
            s["requested"] += 1
            if meta.get("from_cache"):
                s["from_cache"] += 1
            if meta.get("http_status") == 404 or data is None:
                s["404"] += 1
                continue
            d = data.get("data") if isinstance(data, dict) else None
            if not d:
                s["empty"] += 1
                continue
            hf = (d.get("home") or {}).get("formation")
            af = (d.get("away") or {}).get("formation")
            s["ok"] += 1
            if hf and af:
                s["both_formations"] += 1
    return stats


def main():
    print("=" * 78)
    print(f"FORMATION PULL — balanced ~{TARGET_TOTAL} lineups (seed={SEED})")
    print("=" * 78)
    selection = build_selection()
    total = sum(len(v) for v in selection.values())
    print(f"total selected: {total}")

    stats = pull(selection)

    print("\n" + "=" * 78)
    print("PULL RESULT (usable rate per league)")
    print("=" * 78)
    grand = defaultdict(int)
    for tag, s in stats.items():
        usable = s["both_formations"]
        rate = usable / s["requested"] if s["requested"] else 0.0
        print(f"  {tag:8s} req={s['requested']:4d} cache={s['from_cache']:4d} "
              f"ok={s['ok']:4d} 404={s['404']:3d} empty={s['empty']:3d} "
              f"both_formations={usable:4d} usable_rate={rate:.1%}")
        for k, v in s.items():
            grand[k] += v
    gr = grand["both_formations"] / grand["requested"] if grand["requested"] else 0.0
    print(f"  {'TOTAL':8s} req={grand['requested']:4d} cache={grand['from_cache']:4d} "
          f"ok={grand['ok']:4d} 404={grand['404']:3d} empty={grand['empty']:3d} "
          f"both_formations={grand['both_formations']:4d} usable_rate={gr:.1%}")

    print("\nlive requests this run:", api.live_requests_made())
    print("budget:", json.dumps(api.budget_snapshot(), indent=2))
    json.dump({"stats": {t: dict(s) for t, s in stats.items()},
               "grand": dict(grand), "seed": SEED,
               "budget": api.budget_snapshot()},
              open("/home/ubuntu/data/results/formation_pull_report.json", "w"), indent=2)
    print("saved -> data/results/formation_pull_report.json")


if __name__ == "__main__":
    main()
