"""
Raw-feature correlation replication (F016 method) across Championship seasons + corpus.

MODEL-FREE. No GLM, no metric definitions, no fitting. For each season we build team
histories from ALL that season's cached /stats (full season = perfectly balanced,
every team 46 apps), then for each match with computable point-in-time rolling-w5
features we correlate:
    feature (home_w5 + away_w5 of stat X)  vs  realized match outcome Y   [Spearman]

Exactly mirrors the F016 decisive test:
  * rolling window w5 via ev.get_team_rolling_stat (point-in-time: only prior matches,
    requires a full window of >=5 prior matches)
  * feature = home-team rolling + away-team rolling
  * cards outcome = team_a_yellow + team_b_yellow + team_a_red + team_b_red
  * fouls predictor uses the SAME rolling helper on 'fouls'
Adds corners + goals predictors (same mechanism, same helper) for breadth.

Reports PER SEASON, never pooled.
"""
import os, sys, json, glob
import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import championship_adapter as adapt

CACHE = "/home/ubuntu/data/thestatsapi/championship"


def load_season_adapted(season_id):
    """All fixtures in a season -> adapted FootyStats-schema dicts (same adapter as
    the Championship slice). Uses fixture score for goals, cached /stats for the rest."""
    allfx = json.load(open(f"{CACHE}/_all_fixtures_{season_id}.json"))["fixtures"]
    out = []
    for fx in allfx:
        mid = fx["id"]
        spath = f"{CACHE}/stats_{mid}.json"
        sj = json.load(open(spath)) if os.path.exists(spath) else None
        sel_shape = {
            "id": mid, "date": fx["utc_date"],
            "home": fx["home_team"]["name"], "home_id": fx["home_team"]["id"],
            "away": fx["away_team"]["name"], "away_id": fx["away_team"]["id"],
            "score_home": fx.get("score", {}).get("home"),
            "score_away": fx.get("score", {}).get("away"),
        }
        out.append(adapt.adapt_match(sel_shape, sj))
    out.sort(key=lambda m: m["date_unix"])
    return out


def total_cards(m):
    if m["team_a_yellow_cards"] is None or m["team_b_yellow_cards"] is None:
        return None
    return ((m["team_a_yellow_cards"] or 0) + (m["team_b_yellow_cards"] or 0)
            + (m["team_a_red_cards"] or 0) + (m["team_b_red_cards"] or 0))


def total_corners(m):
    pair = m["_rich"].get("corner_kicks")
    return None if pair is None else (pair[0] + pair[1])


def total_goals(m):
    return m["overallGoalCount"]


def rolling_rich(matches_by_team, tid, field, w, before):
    """rolling mean of a _rich (home,away) field for a team, prior matches only."""
    hist = matches_by_team.get(tid, [])
    prior = [(d, m, role) for (d, m, role) in hist if d < before][-w:]
    if len(prior) < w:
        return None
    vals = []
    for _, m, role in prior:
        pair = m["_rich"].get(field)
        if pair is None:
            return None
        vals.append(pair[0] if role == "home" else pair[1])
    return float(np.mean(vals))


def build_rich_idx(matches):
    from collections import defaultdict
    idx = defaultdict(list)
    for m in matches:
        idx[m["home_id"]].append((m["date_unix"], m, "home"))
        idx[m["away_id"]].append((m["date_unix"], m, "away"))
    for k in idx:
        idx[k].sort(key=lambda x: x[0])
    return idx


def corr_named_stat(matches, team_hist, stat, outcome_fn, w=5):
    """cards/fouls path: uses ev.get_team_rolling_stat (name-keyed, extract_stat)."""
    f, o = [], []
    for m in matches:
        hv = ev.get_team_rolling_stat(team_hist, m["home_name"], stat, w, m["date_unix"])
        av = ev.get_team_rolling_stat(team_hist, m["away_name"], stat, w, m["date_unix"])
        if hv is None or av is None:
            continue
        y = outcome_fn(m)
        if y is None:
            continue
        f.append(hv + av); o.append(y)
    if len(f) < 10:
        return None, None, len(f)
    rho, p = spearmanr(f, o)
    return float(rho), float(p), len(f)


def corr_rich_stat(matches, rich_idx, field, outcome_fn, w=5):
    """corners path: uses _rich rolling (id-keyed). Same window/aggregation."""
    f, o = [], []
    for m in matches:
        hv = rolling_rich(rich_idx, m["home_id"], field, w, m["date_unix"])
        av = rolling_rich(rich_idx, m["away_id"], field, w, m["date_unix"])
        if hv is None or av is None:
            continue
        y = outcome_fn(m)
        if y is None:
            continue
        f.append(hv + av); o.append(y)
    if len(f) < 10:
        return None, None, len(f)
    rho, p = spearmanr(f, o)
    return float(rho), float(p), len(f)


def analyze_matches(matches, source):
    th = ev.build_team_histories(matches)
    rich = build_rich_idx(matches)
    r = {"source": source, "n_matches": len(matches)}
    # cards
    r["cards_from_yellow_rate"] = corr_named_stat(matches, th, "yellow_cards", total_cards)
    r["cards_from_foul_rate"] = corr_named_stat(matches, th, "fouls", total_cards)
    # corners: predictor = team recent corners -> total corners
    r["corners_from_corner_rate"] = corr_rich_stat(matches, rich, "corner_kicks", total_corners)
    # goals: predictor = team recent SOT -> total goals; and recent xg -> goals
    r["goals_from_sot_rate"] = corr_named_stat(matches, th, "shotsOnTarget", total_goals)
    r["goals_from_xg_rate"] = corr_named_stat(matches, th, "xg", total_goals)
    return r


def print_row(label, tup):
    if tup[0] is None:
        print(f"    {label:26s}: n={tup[2]:5d}  (insufficient)")
    else:
        print(f"    {label:26s}: Spearman={tup[0]:+.3f}  p={tup[1]:.3g}  n={tup[2]}")


def main():
    seasons = {"Championship 25/26": "sn_3064530",
               "Championship 24/25": "sn_2930227",
               "Championship 23/24": "sn_343481"}
    results = {}

    # ---- corpus reference (FootyStats) ----
    print("=" * 78)
    print("CORPUS REFERENCE (FootyStats, validated) — model-free raw-feature Spearman")
    print("=" * 78)
    fs = ev.load_footystats_corpus()
    # corpus matches already have team_a_* fields + _rich absent; build a _rich shim
    for m in fs:
        pair_c = None
        ca = m.get("team_a_corners"); cb = m.get("team_b_corners")
        if ca is not None and cb is not None:
            pair_c = (ca, cb)
        m["_rich"] = {"corner_kicks": pair_c}
        m.setdefault("home_id", m.get("home_name"))
        m.setdefault("away_id", m.get("away_name"))
    corpus_res = analyze_matches(fs, "FootyStats corpus")
    results["corpus"] = corpus_res
    for k in ("cards_from_yellow_rate", "cards_from_foul_rate", "corners_from_corner_rate",
              "goals_from_sot_rate", "goals_from_xg_rate"):
        print_row(k, corpus_res[k])

    # ---- each Championship season, PER SEASON never pooled ----
    for label, sid in seasons.items():
        print("\n" + "=" * 78)
        print(f"{label}  ({sid})")
        print("=" * 78)
        stats_present = sum(1 for fx in json.load(open(f"{CACHE}/_all_fixtures_{sid}.json"))["fixtures"]
                            if os.path.exists(f"{CACHE}/stats_{fx['id']}.json"))
        matches = load_season_adapted(sid)
        res = analyze_matches(matches, label)
        res["stats_files_present"] = stats_present
        results[sid] = res
        print(f"  fixtures={len(matches)}  stats cached={stats_present}")
        for k in ("cards_from_yellow_rate", "cards_from_foul_rate", "corners_from_corner_rate",
                  "goals_from_sot_rate", "goals_from_xg_rate"):
            print_row(k, res[k])

    json.dump(results, open(f"{CACHE}/_raw_feature_corr_by_season.json", "w"),
              indent=2, default=str)
    print(f"\nsaved: {CACHE}/_raw_feature_corr_by_season.json")


if __name__ == "__main__":
    main()
