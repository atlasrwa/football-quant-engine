"""
Field-population audit across leagues + seasons for the metric-discovery task.

For every league season we measure, per candidate field, the fraction of matches
whose `all`-period cell is non-null for BOTH home AND away.  This tells the
orchestrator which of the ~24 new TheStatsAPI fields (plus the 5 shared baseline
fields) are populated densely enough to be worth mining for new metrics in each
data source.

Definitions:
  * "present" for a field in a match == the field's `all` period has non-null
    home AND away (mirrors championship_adapter._rich_fields' grab() rule).
  * population % == present / total, where total is the number of matches for
    which a stats file exists (NOT the fixture count).  We also report how many
    stats files were found vs how many fixtures exist, so partial fetches are
    obvious.

Reads stats files directly by globbing <tag>_stats_*.json (or stats_*.json for
Championship) and intersecting the parsed match ids with each season's fixture
ids, so a shared cache directory is partitioned correctly per season.

Gracefully handles partially-complete data: seasons with zero stats files report
0/0 and are flagged; the script never requires the full dataset.

Output:
  * data/thestatsapi/championship/_field_population.json
  * a readable per-league table to stdout
py_compile only for now; run later once fetching completes.
"""
import os
import sys
import json
import glob

sys.path.insert(0, os.path.dirname(__file__))
import multisrc_corpus as corpus
import championship_adapter as adapt  # reuse _cell for consistent cell access

CACHE = corpus.CACHE
OUT_PATH = f"{CACHE}/_field_population.json"

# Field -> group mapping. np_expected_goals is a top-level node (group == name,
# stat ignored by adapt._cell for that special case).
FIELD_GROUPS = {
    # --- new candidate fields (~24) ---
    "blocked_shots": "shots",
    "shots_inside_box": "shots",
    "shots_outside_box": "shots",
    "hit_woodwork": "shots",
    "big_chances": "overview",
    "big_chances_missed": "attack",
    "touches_in_penalty_area": "attack",
    "fouled_in_final_third": "attack",
    "accurate_crosses": "passes",
    "accurate_long_balls": "passes",
    "final_third_entries": "passes",
    "duels_won_percentage": "duels",
    "dispossessed": "duels",
    "dribbles_percentage": "duels",
    "ground_duels_percentage": "duels",
    "aerial_duels_percentage": "duels",
    "tackles": "defending",
    "tackles_won_percentage": "defending",
    "interceptions": "defending",
    "clearances": "defending",
    "ball_recoveries": "defending",
    "saves": "goalkeeping",
    "goal_kicks": "goalkeeping",
    "goals_prevented": "goalkeeping",
    "high_claims": "goalkeeping",
    "np_expected_goals": "np_expected_goals",  # top-level node
    # --- baseline shared fields (5) ---
    "corner_kicks": "overview",
    "yellow_cards": "overview",
    "fouls": "overview",
    "shots_on_target": "overview",
    "expected_goals": "overview",
}

NEW_FIELDS = [
    "blocked_shots", "shots_inside_box", "shots_outside_box", "hit_woodwork",
    "big_chances", "big_chances_missed", "touches_in_penalty_area",
    "fouled_in_final_third", "accurate_crosses", "accurate_long_balls",
    "final_third_entries", "duels_won_percentage", "dispossessed",
    "dribbles_percentage", "ground_duels_percentage", "aerial_duels_percentage",
    "tackles", "tackles_won_percentage", "interceptions", "clearances",
    "ball_recoveries", "saves", "goal_kicks", "goals_prevented", "high_claims",
    "np_expected_goals",
]
BASELINE_FIELDS = ["corner_kicks", "yellow_cards", "fouls", "shots_on_target",
                   "expected_goals"]
ALL_FIELDS = NEW_FIELDS + BASELINE_FIELDS


def stats_glob(tag):
    """Glob pattern for a league's stats files (tagged vs untagged)."""
    prefix = corpus.LEAGUES[tag]["fixture_prefix"]
    if prefix:
        return f"{CACHE}/{prefix}_stats_*.json"
    # Championship: untagged files. Exclude the tagged leagues' files, which also
    # end in _stats_*.json, by requiring the basename to start with "stats_".
    return f"{CACHE}/stats_*.json"


def _mid_from_stats_filename(path, tag):
    """Recover the match id from a stats filename for either naming scheme."""
    base = os.path.basename(path)
    prefix = corpus.LEAGUES[tag]["fixture_prefix"]
    if prefix:
        # <prefix>_stats_<mid>.json
        head = f"{prefix}_stats_"
    else:
        head = "stats_"
    if not base.startswith(head) or not base.endswith(".json"):
        return None
    return base[len(head):-len(".json")]


def _field_present(sd, field):
    """True iff the field's `all` period has non-null home AND away."""
    group = FIELD_GROUPS[field]
    if group == "np_expected_goals":
        h = adapt._cell(sd, "np_expected_goals", None, "all", "home")
        a = adapt._cell(sd, "np_expected_goals", None, "all", "away")
    else:
        h = adapt._cell(sd, group, field, "all", "home")
        a = adapt._cell(sd, group, field, "all", "away")
    return h is not None and a is not None


def season_population(tag, season_id):
    """Compute field population for one league season.

    Returns a dict with fixture/stats counts and a per-field {present,total,pct}.
    total == number of matches with a stats file that also belong to this season.
    """
    fixture_path = corpus.fixture_path(tag, season_id)
    result = {
        "tag": tag,
        "season_id": season_id,
        "n_fixtures": 0,
        "n_stats_files_matched": 0,
        "fields": {f: {"present": 0, "total": 0, "pct": None} for f in ALL_FIELDS},
    }
    if not os.path.exists(fixture_path):
        result["error"] = f"fixtures not found: {fixture_path}"
        return result

    fixtures = corpus.load_fixtures(tag, season_id)
    fixture_ids = {fx["id"] for fx in fixtures}
    result["n_fixtures"] = len(fixtures)

    # Map available stats files (this league's naming) to match ids.
    available = {}
    for path in glob.glob(stats_glob(tag)):
        mid = _mid_from_stats_filename(path, tag)
        if mid is not None:
            available[mid] = path

    counts = {f: {"present": 0, "total": 0} for f in ALL_FIELDS}
    matched = 0
    for mid in fixture_ids:
        path = available.get(mid)
        if path is None:
            continue  # stats not fetched yet for this match
        matched += 1
        try:
            with open(path) as fh:
                sd = (json.load(fh) or {}).get("data", {})
        except (OSError, ValueError):
            continue  # unreadable/partial file: skip, keep going
        for f in ALL_FIELDS:
            counts[f]["total"] += 1
            if _field_present(sd, f):
                counts[f]["present"] += 1

    result["n_stats_files_matched"] = matched
    for f in ALL_FIELDS:
        pr, to = counts[f]["present"], counts[f]["total"]
        result["fields"][f] = {
            "present": pr,
            "total": to,
            "pct": (round(100.0 * pr / to, 1) if to else None),
        }
    return result


def build_all():
    """Population audit for every league season in the registry."""
    out = {"leagues": {}}
    for tag, league in corpus.LEAGUES.items():
        out["leagues"][tag] = {
            "display": league["display"],
            "comp": league["comp"],
            "seasons": {},
        }
        for season_id in league["seasons"]:
            out["leagues"][tag]["seasons"][season_id] = season_population(tag, season_id)
    return out


def _fmt_pct(cell):
    if cell["total"] == 0:
        return "  --  "
    return f"{cell['pct']:5.1f}%"


def print_table(report):
    for tag, ldata in report["leagues"].items():
        print("=" * 78)
        print(f"{ldata['display']}  (tag={tag})")
        print("=" * 78)
        for season_id, sdata in ldata["seasons"].items():
            if "error" in sdata:
                print(f"  {season_id}: {sdata['error']}")
                continue
            print(
                f"  {season_id}: fixtures={sdata['n_fixtures']}  "
                f"stats_matched={sdata['n_stats_files_matched']}"
            )
            if sdata["n_stats_files_matched"] == 0:
                print("    (no stats files yet - population pending fetch)")
                continue
            print("    NEW FIELDS:")
            for f in NEW_FIELDS:
                c = sdata["fields"][f]
                print(f"      {f:26s} {_fmt_pct(c)}  ({c['present']}/{c['total']})")
            print("    BASELINE FIELDS:")
            for f in BASELINE_FIELDS:
                c = sdata["fields"][f]
                print(f"      {f:26s} {_fmt_pct(c)}  ({c['present']}/{c['total']})")


def main():
    report = build_all()
    with open(OUT_PATH, "w") as fh:
        json.dump(report, fh, indent=2)
    print_table(report)
    print(f"\nsaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
