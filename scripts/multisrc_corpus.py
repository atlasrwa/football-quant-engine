"""
Reusable multi-league corpus loader for the metric-discovery task.

Loads adapted match dicts for Championship, Ligue 2, and La Liga 2 from cached
TheStatsAPI fixture + per-match /stats files, reusing the EXACT same adapter logic
as championship_adapter.adapt_match (imported, not re-implemented) so every league
produces the identical FootyStats-schema match dict the model pipeline consumes.

Data-source differences handled here:
  * Championship fixture files have NO tag prefix (_all_fixtures_<season>.json) and
    untagged stats files (stats_<mid>.json).
  * Ligue 2 / La Liga 2 fixture files ARE tag-prefixed
    (_all_fixtures_<tag>_<season>.json) and use tagged stats files
    (<tag>_stats_<mid>.json).

The adapter expects a fixture dict shaped {id,date,home,away,home_id,away_id,
score_home,score_away}; we build that shape here from each TheStatsAPI fixture
(date=utc_date, home=home_team.name, home_id=home_team.id, score_home=score.home,
etc.).

NOTE: the full loader reads one /stats file per match. Data is still being fetched,
so load_season() must NOT be run against incomplete data by the orchestrator until
all stats land. The __main__ balance report deliberately needs ONLY the fixture
files (team appearances are derivable from fixtures alone), so it is safe to run now.
"""
import os
import sys
import json
import glob
import statistics
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import championship_adapter as adapt  # reuse adapt_match / _cell / _rich_fields

CACHE = "/home/ubuntu/data/thestatsapi/championship"

# ---------------------------------------------------------------------------
# League registry.
#
# fixture_prefix is the token inserted between "_all_fixtures_" and the season id
# in the fixture filename, AND used as the stats-file tag prefix.  Championship
# uses an empty prefix for both its fixture files (_all_fixtures_<season>.json)
# and its stats files (stats_<mid>.json).  Ligue 2 / La Liga 2 use their tag.
# ---------------------------------------------------------------------------
LEAGUES = {
    "champ": {
        "display": "Championship",
        "comp": "championship",
        "seasons": ["sn_3064530", "sn_2930227", "sn_343481"],  # 25/26, 24/25, 23/24
        "fixture_prefix": "",
    },
    "ligue2": {
        "display": "Ligue 2",
        "comp": "ligue2",
        "seasons": ["sn_3064056", "sn_3057202"],  # 25/26, 24/25
        "fixture_prefix": "ligue2",
    },
    "laliga2": {
        "display": "La Liga 2",
        "comp": "laliga2",
        "seasons": ["sn_8437950", "sn_8425423"],  # 25/26, 24/25
        "fixture_prefix": "laliga2",
    },
}


def fixture_path(tag, season_id):
    """Path to the season's _all_fixtures_*.json, respecting the tag/no-tag rule."""
    prefix = LEAGUES[tag]["fixture_prefix"]
    if prefix:
        return f"{CACHE}/_all_fixtures_{prefix}_{season_id}.json"
    return f"{CACHE}/_all_fixtures_{season_id}.json"


def stats_path(tag, mid):
    """Path to a per-match stats file, respecting the tag/no-tag rule.

    Championship stats are untagged (stats_<mid>.json); the other leagues are
    tagged (<tag>_stats_<mid>.json).  We also fall back to the untagged name so
    partially-migrated caches still resolve.
    """
    prefix = LEAGUES[tag]["fixture_prefix"]
    if prefix:
        tagged = f"{CACHE}/{prefix}_stats_{mid}.json"
        if os.path.exists(tagged):
            return tagged
        # graceful fallback: some caches may store untagged even for tagged leagues
        untagged = f"{CACHE}/stats_{mid}.json"
        return tagged if not os.path.exists(untagged) else untagged
    return f"{CACHE}/stats_{mid}.json"


def load_fixtures(tag, season_id):
    """Return the raw TheStatsAPI fixture list for a league season."""
    path = fixture_path(tag, season_id)
    with open(path) as fh:
        return json.load(fh)["fixtures"]


def _to_adapter_shape(fx):
    """Map a TheStatsAPI fixture -> the {id,date,home,...} shape adapt_match wants."""
    score = fx.get("score") or {}
    return {
        "id": fx["id"],
        "date": fx["utc_date"],
        "home": fx["home_team"]["name"],
        "home_id": fx["home_team"]["id"],
        "away": fx["away_team"]["name"],
        "away_id": fx["away_team"]["id"],
        "score_home": score.get("home"),
        "score_away": score.get("away"),
    }


def load_season(tag, season_id):
    """Load all matches of one league season as adapted FootyStats-schema dicts,
    sorted by date_unix.

    Reuses championship_adapter.adapt_match for every league so the produced dicts
    are byte-for-byte identical in schema to the Championship slice.  Missing stats
    files are passed through as None (adapt_match yields null stat cells, which the
    downstream rolling helpers already drop).
    """
    fixtures = load_fixtures(tag, season_id)
    out = []
    for fx in fixtures:
        shape = _to_adapter_shape(fx)
        spath = stats_path(tag, fx["id"])
        sj = None
        if os.path.exists(spath):
            with open(spath) as fh:
                sj = json.load(fh)
        out.append(adapt.adapt_match(shape, sj))
    out.sort(key=lambda m: m["date_unix"])
    return out


# ---------------------------------------------------------------------------
# Balance reporting (fixtures-only; safe to run against incomplete stats caches).
# ---------------------------------------------------------------------------
def team_appearance_counts(fixtures):
    """Count home+away appearances per team id from fixtures alone."""
    counts = {}
    for fx in fixtures:
        for side in ("home_team", "away_team"):
            tid = fx[side]["id"]
            counts[tid] = counts.get(tid, 0) + 1
    return counts


def balance_report(tag):
    """Build a per-season balance report for one league using ONLY fixture files.

    Returns a dict: {season_id: {n_matches, n_teams, min, max, median}}.
    """
    report = {}
    for season_id in LEAGUES[tag]["seasons"]:
        path = fixture_path(tag, season_id)
        if not os.path.exists(path):
            report[season_id] = {"error": f"fixtures not found: {path}"}
            continue
        fixtures = load_fixtures(tag, season_id)
        counts = team_appearance_counts(fixtures)
        vals = sorted(counts.values())
        report[season_id] = {
            "n_matches": len(fixtures),
            "n_teams": len(counts),
            "min_apps": min(vals) if vals else 0,
            "max_apps": max(vals) if vals else 0,
            "median_apps": statistics.median(vals) if vals else 0,
        }
    return report


def _print_balance(tag):
    league = LEAGUES[tag]
    print("=" * 72)
    print(f"{league['display']}  (tag={tag}, comp={league['comp']})")
    print("=" * 72)
    report = balance_report(tag)
    for season_id, r in report.items():
        if "error" in r:
            print(f"  {season_id}: {r['error']}")
            continue
        print(
            f"  {season_id}: matches={r['n_matches']:4d}  teams={r['n_teams']:3d}  "
            f"apps min/median/max = {r['min_apps']}/{r['median_apps']}/{r['max_apps']}"
        )


if __name__ == "__main__":
    # Usage: python3 multisrc_corpus.py [tag]
    #   tag defaults to all leagues. Balance report uses fixtures only, so it is
    #   safe to run before all /stats files have been fetched.
    requested = sys.argv[1:] if len(sys.argv) > 1 else list(LEAGUES.keys())
    for t in requested:
        if t not in LEAGUES:
            print(f"unknown tag: {t} (known: {', '.join(LEAGUES)})")
            continue
        _print_balance(t)
