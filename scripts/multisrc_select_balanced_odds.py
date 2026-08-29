"""Select a balanced subset of matches (per-team balanced, spread across calendar)
for odds fetching, mirroring the F015 slice approach. Writes an ids JSON per league.
Most recent complete season only (odds are for market-calibration, model-independent)."""
import json, sys
from collections import defaultdict, Counter

CACHE = "/home/ubuntu/data/thestatsapi/championship"

# most recent complete season per league
SEASON = {"ligue2": "sn_3064056", "laliga2": "sn_8437950"}
TARGET_PER_TEAM = {"ligue2": 12, "laliga2": 10}  # ~ balanced; 18*12/2=108, 22*10/2=110


def select(tag):
    sid = SEASON[tag]
    fx = json.load(open(f"{CACHE}/_all_fixtures_{tag}_{sid}.json"))["fixtures"]
    # sort by date to spread across calendar
    fx.sort(key=lambda f: f["utc_date"])
    cap = TARGET_PER_TEAM[tag]
    appear = Counter()
    chosen = []
    # greedy: walk chronologically, take a match if BOTH teams still under cap
    for f in fx:
        h = f["home_team"]["id"]; a = f["away_team"]["id"]
        if appear[h] < cap and appear[a] < cap:
            chosen.append(f["id"]); appear[h] += 1; appear[a] += 1
    vals = sorted(appear.values())
    import statistics
    print(f"{tag} {sid}: selected {len(chosen)} matches; per-team min={min(vals)} "
          f"max={max(vals)} median={statistics.median(vals)} teams={len(vals)}")
    json.dump(chosen, open(f"{CACHE}/_odds_ids_{tag}.json", "w"))
    # also record team balance
    json.dump({"tag": tag, "season": sid, "n": len(chosen),
               "per_team_min": min(vals), "per_team_max": max(vals),
               "per_team_median": statistics.median(vals), "teams": len(vals)},
              open(f"{CACHE}/_odds_selection_{tag}.json", "w"), indent=2)
    return chosen


if __name__ == "__main__":
    for tag in (sys.argv[1:] or ["ligue2", "laliga2"]):
        select(tag)
