"""
Rich-field BUILDABILITY audit (task 2) — zero API, rich corpus.

'Populated' is not enough: to build a strictly-prior rolling mean a team needs
>= MIN_PRIOR prior matches with the field present. This reports, per league, the
fraction of (match, team-side) slots for which each rich field is BUILDABLE, and
recommends inclusion/exclusion. Fields that can't be built are EXCLUDED (never
zero-filled).

A field is buildable-for-a-slot if, at the fixture date, that team has >= MIN_PRIOR
earlier matches in which the field was non-null. We report the fraction of the
league's predictable slots (both teams have >= MIN_PRIOR prior games with SOME data)
for which the field specifically is buildable.
"""
import sys, json
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")
import multisrc_corpus as corpus

MIN_PRIOR = 3
WINDOW = 10
LEAGUES = ["champ", "laliga2", "ligue2"]

# rich fields (from _rich) + baseline top-level fields we can also roll
RICH_FIELDS = ["corner_kicks", "big_chances", "big_chances_missed", "touches_in_penalty_area",
               "final_third_entries", "accurate_crosses", "tackles", "interceptions",
               "clearances", "ball_recoveries", "np_expected_goals", "shots_on_target",
               "shots_inside_box", "shots_outside_box", "blocked_shots", "fouled_in_final_third",
               "accurate_long_balls", "ground_duels_percentage", "aerial_duels_percentage",
               "tackles_won_percentage", "saves", "high_claims", "goals_prevented"]
# baseline top-level per-team fields (present in rich corpus), used for the baseline model
BASELINE_TOPLEVEL = ["fouls_tl", "shotsOnTarget_tl", "xg_tl"]  # from team_a_fouls etc.

BUILDABLE_THRESHOLD = 0.80  # >=80% of predictable slots buildable to include a field


def load_league(tag):
    ms = []
    for sid in corpus.LEAGUES[tag]["seasons"]:
        ms.extend(corpus.load_season(tag, sid))
    ms = [m for m in ms if m.get("date_unix")]
    ms.sort(key=lambda m: m["date_unix"])
    return ms


def rich_val(m, field, side):
    pair = m["_rich"].get(field)
    if pair is None:
        return None
    v = pair[0] if side == "home" else pair[1]
    return None if v is None else float(v)


def toplevel_val(m, field, side):
    key = ("team_a_" if side == "home" else "team_b_") + field
    v = m.get(key)
    return None if v is None else float(v)


def analyze(tag):
    ms = load_league(tag)
    # per team, chronological history of which fields were present
    hist_rich = defaultdict(lambda: defaultdict(int))   # team -> field -> count of prior non-null
    hist_base = defaultdict(lambda: defaultdict(int))
    # count buildable slots
    rich_buildable = defaultdict(int); base_buildable = defaultdict(int)
    predictable_slots = 0
    for m in ms:
        for side in ("home", "away"):
            tid = m["home_id"] if side == "home" else m["away_id"]
            # a "predictable slot" = team has >=MIN_PRIOR prior matches with ANY corner data
            # (use corner_kicks presence as the anchor of having played rich-covered games)
            anchor = hist_rich[tid]["corner_kicks"]
            if anchor >= MIN_PRIOR:
                predictable_slots += 1
                for f in RICH_FIELDS:
                    if hist_rich[tid][f] >= MIN_PRIOR:
                        rich_buildable[f] += 1
                for f in BASELINE_TOPLEVEL:
                    base = f.replace("_tl", "")
                    if hist_base[tid][base] >= MIN_PRIOR:
                        base_buildable[f] += 1
        # fold current match in AFTER
        for side in ("home", "away"):
            tid = m["home_id"] if side == "home" else m["away_id"]
            for f in RICH_FIELDS:
                if rich_val(m, f, side) is not None:
                    hist_rich[tid][f] += 1
            for f in ("fouls", "shotsOnTarget", "xg"):
                if toplevel_val(m, f, side) is not None:
                    hist_base[tid][f] += 1
    return {"n_matches": len(ms), "predictable_slots": predictable_slots,
            "rich_buildable_pct": {f: (100.0 * rich_buildable[f] / predictable_slots
                                       if predictable_slots else 0.0) for f in RICH_FIELDS},
            "base_buildable_pct": {f: (100.0 * base_buildable[f] / predictable_slots
                                       if predictable_slots else 0.0) for f in BASELINE_TOPLEVEL}}


def main():
    print("RICH-FIELD BUILDABILITY (zero API). A field is buildable for a slot if the team has")
    print(f">= MIN_PRIOR={MIN_PRIOR} EARLIER matches with the field present. Threshold to INCLUDE")
    print(f"= {BUILDABLE_THRESHOLD:.0%} of predictable slots. Excluded fields are NEVER zero-filled.\n")
    report = {}
    include = defaultdict(dict)
    for tag in LEAGUES:
        r = analyze(tag)
        report[tag] = r
        disp = corpus.LEAGUES[tag]["display"]
        print(f"=== {disp} (n={r['n_matches']}, predictable slots={r['predictable_slots']}) ===")
        print("  BASELINE (top-level):")
        for f, pct in r["base_buildable_pct"].items():
            inc = pct >= BUILDABLE_THRESHOLD * 100
            include[tag][f] = inc
            print(f"    {f:26s} {pct:5.1f}%  {'INCLUDE' if inc else 'EXCLUDE'}")
        print("  RICH:")
        for f in RICH_FIELDS:
            pct = r["rich_buildable_pct"][f]
            inc = pct >= BUILDABLE_THRESHOLD * 100
            include[tag][f] = inc
            print(f"    {f:26s} {pct:5.1f}%  {'INCLUDE' if inc else 'EXCLUDE'}")
        print()
    # summary: which fields are buildable in ALL three leagues vs some
    all_fields = BASELINE_TOPLEVEL + RICH_FIELDS
    print("=" * 70)
    print("INCLUSION SUMMARY (buildable >=80% in league)")
    print("=" * 70)
    for f in all_fields:
        flags = {tag: include[tag].get(f, False) for tag in LEAGUES}
        n_in = sum(flags.values())
        detail = ", ".join(f"{t}=" + ("Y" if flags[t] else "n") for t in LEAGUES)
        print(f"  {f:26s} in {n_in}/3 leagues: " + detail)
    json.dump({"report": report, "include": {t: dict(include[t]) for t in include}},
              open("/home/ubuntu/data/results/rich_field_availability.json", "w"), indent=2)
    print("\nsaved: data/results/rich_field_availability.json")


if __name__ == "__main__":
    main()
