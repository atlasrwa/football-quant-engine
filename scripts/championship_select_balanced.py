"""
Offline balanced-sample selection for the Championship 25/26 slice.

Goal: pick ~TARGET matches so each of the 24 teams appears a comparable number of
times AND matches are spread across the season calendar (not clustered early/late).

Method (deterministic, no API calls):
  * Each match covers 2 teams. With 24 teams, TARGET matches -> 2*TARGET team-slots
    -> TARGET*2/24 appearances per team if perfectly balanced.
  * Greedy with calendar stratification:
      - Split the season into TARGET time-bins (by date order).
      - Iterate bins in order; within each bin pick the one unselected match whose
        two teams currently have the LOWEST combined appearance count (ties -> earliest
        date). This pulls the sample toward balance while walking the calendar.
  * Reports per-team min/max/median and the calendar spread.
No boundary tuning to chase a result — this is pure sampling design run before any
analysis.
"""
import json, os, sys, statistics
from collections import defaultdict

SEASON = "sn_3064530"
CACHE = "/home/ubuntu/data/thestatsapi/championship"
TARGET = int(os.environ.get("CHAMP_TARGET", "200"))


def main():
    d = json.load(open(f"{CACHE}/_all_fixtures_{SEASON}.json"))
    fx = sorted(d["fixtures"], key=lambda m: m["utc_date"])
    n_total = len(fx)
    teams = sorted({t for m in fx for t in (m["home_team"]["id"], m["away_team"]["id"])})
    n_teams = len(teams)
    target = min(TARGET, n_total)

    # calendar bins
    bins = [[] for _ in range(target)]
    for i, m in enumerate(fx):
        b = min(target - 1, i * target // n_total)
        bins[b].append(m)

    appear = defaultdict(int)
    selected = []
    selected_ids = set()

    for b in range(target):
        # candidate matches in this bin not yet selected
        cands = [m for m in bins[b] if m["id"] not in selected_ids]
        if not cands:
            # borrow from nearest non-empty later/earlier bin
            for off in range(1, target):
                for bb in (b + off, b - off):
                    if 0 <= bb < target:
                        cands = [m for m in bins[bb] if m["id"] not in selected_ids]
                        if cands:
                            break
                if cands:
                    break
        if not cands:
            break
        # choose match minimizing combined current appearances of its two teams
        def score(m):
            return (appear[m["home_team"]["id"]] + appear[m["away_team"]["id"]],
                    m["utc_date"])
        pick = min(cands, key=score)
        selected.append(pick)
        selected_ids.add(pick["id"])
        appear[pick["home_team"]["id"]] += 1
        appear[pick["away_team"]["id"]] += 1

    # Balance polish: while max-min appearance gap > 1, try swapping a match that
    # touches an over-represented team for an unselected match touching under-rep teams.
    def gap():
        vals = [appear[t] for t in teams]
        return max(vals) - min(vals), vals
    unselected = [m for m in fx if m["id"] not in selected_ids]
    for _ in range(2000):
        g, vals = gap()
        if g <= 1:
            break
        over = max(teams, key=lambda t: appear[t])
        under = min(teams, key=lambda t: appear[t])
        # find a selected match that includes `over` but not `under`
        rem = None
        for m in selected:
            ids = {m["home_team"]["id"], m["away_team"]["id"]}
            if over in ids and under not in ids:
                rem = m
                break
        # find an unselected match that includes `under` but not `over`
        add = None
        for m in unselected:
            ids = {m["home_team"]["id"], m["away_team"]["id"]}
            if under in ids and over not in ids:
                add = m
                break
        if rem is None or add is None:
            break
        # apply swap
        selected.remove(rem); selected_ids.discard(rem["id"]); unselected.append(rem)
        for t in (rem["home_team"]["id"], rem["away_team"]["id"]):
            appear[t] -= 1
        selected.append(add); selected_ids.add(add["id"]); unselected.remove(add)
        for t in (add["home_team"]["id"], add["away_team"]["id"]):
            appear[t] += 1

    selected.sort(key=lambda m: m["utc_date"])
    counts = {t: appear[t] for t in teams}
    name_by_id = {}
    for m in fx:
        name_by_id[m["home_team"]["id"]] = m["home_team"]["name"]
        name_by_id[m["away_team"]["id"]] = m["away_team"]["name"]

    vals = sorted(counts.values())
    print(f"selected {len(selected)} matches (target {target}) over {n_total} total")
    print(f"team appearances: min={min(vals)} max={max(vals)} "
          f"median={int(statistics.median(vals))} mean={statistics.mean(vals):.1f}")
    print("per-team appearance counts:")
    for t in sorted(counts, key=lambda z: -counts[z]):
        print(f"  {name_by_id[t]:22s} {counts[t]}")
    # calendar spread: matches per month
    bymonth = defaultdict(int)
    for m in selected:
        bymonth[m["utc_date"][:7]] += 1
    print("calendar spread (selected matches per month):")
    for mo in sorted(bymonth):
        print(f"  {mo}: {bymonth[mo]}")

    out = {
        "season_id": SEASON, "target": target, "n_selected": len(selected),
        "team_appearances": {name_by_id[t]: counts[t] for t in counts},
        "appearance_min": min(vals), "appearance_max": max(vals),
        "appearance_median": statistics.median(vals),
        "selected_match_ids": [m["id"] for m in selected],
        "selected": [{"id": m["id"], "date": m["utc_date"],
                      "home_id": m["home_team"]["id"], "home": m["home_team"]["name"],
                      "away_id": m["away_team"]["id"], "away": m["away_team"]["name"],
                      "score_home": m.get("score", {}).get("home"),
                      "score_away": m.get("score", {}).get("away")} for m in selected],
    }
    with open(f"{CACHE}/_selected_balanced_{SEASON}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nsaved selection: _selected_balanced_{SEASON}.json")


if __name__ == "__main__":
    main()
