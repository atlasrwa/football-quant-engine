"""
Coverage Matrix Audit — Part 2 FootyStats field population (cache-first).

Reads cached FootyStats league-matches files in .cache/footystats_forward/. Classifies
each field per record as present_and_non_null / present_but_zero_or_sentinel / absent.
FootyStats uses -1 as the sentinel for unplayed/unavailable and refereeID=None when
unassigned. To get a meaningful *population* rate we report over PLAYED matches
(status complete) as well as raw over all matches. Also confirms priced markets.

Zero live calls: FootyStats data is already cached.
"""
from __future__ import annotations
import glob, json, sys
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/scripts")
import coverage_audit_common as cac

CACHE_GLOB = "/home/ubuntu/.cache/footystats_forward/league-matches_*.json"

# FootyStats fields required by the audit (Req 3.4), with per-side variants collapsed.
FIELDS = [
    "homeGoalCount", "awayGoalCount",
    "team_a_corners", "team_b_corners", "team_a_fh_corners", "team_a_2h_corners",
    "team_a_yellow_cards", "team_a_red_cards", "team_a_fh_cards", "team_a_2h_cards",
    "team_a_fouls", "team_a_shots", "team_a_shotsOnTarget", "team_a_shotsOffTarget",
    "team_a_possession", "team_a_offsides", "team_a_attacks", "team_a_dangerous_attacks",
    "team_a_xg", "total_xg_prematch", "team_a_penalties", "team_a_freekicks",
    "team_a_throwins", "team_a_goalkicks", "refereeID", "coach_a_ID",
]

# Odds fields to confirm FootyStats priced markets (Req 1.7)
ODDS_FIELDS_PREFIXES = ("odds_ft_", "odds_btts_", "odds_corners_", "odds_team_",
                        "odds_ou", "odds_1st_half", "odds_doublechance")

SENTINELS = (-1, "-1")


def classify(val):
    if val is None:
        return "absent"
    if val in SENTINELS or val == 0 or val == "":
        return "present_but_zero_or_sentinel"
    return "present_and_non_null"


def is_played(m):
    return m.get("status") == "complete"


def run():
    files = glob.glob(CACHE_GLOB)
    # counts[field] = {bucket: n}; also over played-only
    counts = defaultdict(lambda: defaultdict(int))
    counts_played = defaultdict(lambda: defaultdict(int))
    n_all = 0
    n_played = 0
    odds_keys_seen = set()
    odds_keys_present = defaultdict(int)
    cards_or_offsides_odds = set()

    for f in files:
        d = json.load(open(f))
        data = d.get("data", d) if isinstance(d, dict) else d
        if not isinstance(data, list):
            continue
        for m in data:
            n_all += 1
            played = is_played(m)
            if played:
                n_played += 1
            for field in FIELDS:
                present = field in m
                bucket = classify(m.get(field)) if present else "absent"
                counts[field][bucket] += 1
                if played:
                    counts_played[field][bucket] += 1
            # odds field discovery
            for k, v in m.items():
                if any(k.startswith(p) for p in ODDS_FIELDS_PREFIXES):
                    odds_keys_seen.add(k)
                    if v not in (None, -1, "-1", 0, ""):
                        odds_keys_present[k] += 1
                    if "card" in k.lower() or "offside" in k.lower():
                        cards_or_offsides_odds.add(k)

    out = {"n_files": len(files), "n_matches_all": n_all, "n_matches_played": n_played,
           "fields_all": {}, "fields_played": {},
           "priced_markets": {
               "odds_keys_seen": sorted(odds_keys_seen),
               "odds_keys_with_data": {k: v for k, v in sorted(odds_keys_present.items())},
               "cards_or_offsides_odds_keys": sorted(cards_or_offsides_odds),
           }}
    for field in FIELDS:
        c = counts[field]
        nn = c.get("present_and_non_null", 0)
        out["fields_all"][field] = {
            "present_and_non_null": nn,
            "present_but_zero_or_sentinel": c.get("present_but_zero_or_sentinel", 0),
            "absent": c.get("absent", 0),
            "rate_nonnull": cac.rate(nn, n_all),
        }
        cp = counts_played[field]
        nnp = cp.get("present_and_non_null", 0)
        out["fields_played"][field] = {
            "present_and_non_null": nnp,
            "present_but_zero_or_sentinel": cp.get("present_but_zero_or_sentinel", 0),
            "absent": cp.get("absent", 0),
            "rate_nonnull": cac.rate(nnp, n_played),
        }
    cac.write_artifact("footystats_fields.json", out)
    print(f"files={len(files)} matches_all={n_all} matches_played={n_played}")
    print("\nField population over PLAYED matches:")
    for field in FIELDS:
        r = out["fields_played"][field]["rate_nonnull"]
        print(f"  {field:24s} {r['pct']}% non-null  (sentinel/zero="
              f"{out['fields_played'][field]['present_but_zero_or_sentinel']}, "
              f"absent={out['fields_played'][field]['absent']})")
    print("\nPriced-market odds keys with data:",
          list(out["priced_markets"]["odds_keys_with_data"].keys()))
    print("cards/offsides odds keys:",
          out["priced_markets"]["cards_or_offsides_odds_keys"] or "NONE")


if __name__ == "__main__":
    run()
