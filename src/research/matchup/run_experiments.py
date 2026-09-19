"""Build feature families per fixture, cache them, and run the ablation ladder.

Produces research/contextual_matchup/out/ tables. Deterministic, chronological OOS,
common-support, no odds, no prospective data.
"""
from __future__ import annotations
import os, sys, json, time, warnings
import numpy as np
warnings.filterwarnings("ignore")
from src._repo_paths import ensure_repo_importable
ensure_repo_importable()

from src.research.matchup.corpus import load_corpus
from src.research.matchup.design import DesignBuilder, outcome, POOLS, CHAMP_POOL
from src.research.matchup import harness as H

OUT = "/home/ubuntu/research/contextual_matchup/out"
os.makedirs(OUT, exist_ok=True)

MARKETS = [("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
           ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
           ("cards", 3.5), ("cards", 4.5), ("btts", None)]

FAMILIES = ["champ", "direct", "league_env", "home_away", "matchup", "oppquality", "rich"]


def build_family_matrix(db, recs, market):
    """For each fixture (with a valid outcome for `market`), build every family dict.
    Returns (rows, feat_by_family, y, comps, times) where rows align across families."""
    fam_fns = {
        "champ": db.f_champ, "direct": db.f_direct, "league_env": db.f_league_env,
        "home_away": db.f_home_away, "matchup": db.f_matchup,
        "oppquality": db.f_oppquality, "rich": db.f_rich,
    }
    line = dict(MARKETS)  # not used
    line_val = None
    # collect for this specific (market,line) handled by caller; here market family only
    return fam_fns


def main():
    t0 = time.time()
    recs = load_corpus()
    print(f"[{time.time()-t0:.0f}s] corpus {len(recs)} matches")
    db = DesignBuilder(recs)
    # warm strength ratings for the stats we need
    for s in ["xg", "corner_kicks", "cards"]:
        db.ratings(s)
    print(f"[{time.time()-t0:.0f}s] ratings warmed")

    fam_fns = {
        "champ": db.f_champ, "direct": db.f_direct, "league_env": db.f_league_env,
        "home_away": db.f_home_away, "matchup": db.f_matchup,
        "oppquality": db.f_oppquality, "rich": db.f_rich,
    }

    results = {}
    ablations = []
    dist_rows = []
    for market, lineval in MARKETS:
        cell = f"{market}_{lineval}"
        # build per-fixture family dicts + outcome
        fam_data = {f: [] for f in FAMILIES}
        y = []; comps = []; times = []
        for rec in recs:
            o = outcome(rec, market, lineval)
            if o is None:
                continue
            y.append(o); comps.append(rec.competition); times.append(rec.kickoff_unix)
            for f in FAMILIES:
                fam_data[f].append(fam_fns[f](rec, market))
        y = np.array(y)
        # feature name universe per family (union of keys)
        fam_names = {}
        for f in FAMILIES:
            keys = set()
            for d in fam_data[f]:
                keys.update(d.keys())
            fam_names[f] = sorted(keys)

        def matrix(fam_list):
            names = []
            for f in fam_list:
                names += [f"{f}::{k}" for k in fam_names[f]]
            M = np.full((len(y), len(names)), np.nan)
            col = 0
            for f in fam_list:
                for k in fam_names[f]:
                    for i, d in enumerate(fam_data[f]):
                        v = d.get(k)
                        if v is not None:
                            M[i, col] = v
                    col += 1
            return M, names

        # champion baseline (F0)
        Xc, ncoln = matrix(["champ"])
        base_wf = H.walk_forward(Xc, y, comps, times)
        if base_wf is None:
            print(f"  {cell}: insufficient")
            continue
        base_sum = H.summarize(base_wf["y"], base_wf["p"], base_wf["comp"])
        results[cell] = {"champ": base_sum}
        dist_rows.append({"cell": cell, "model": "champ", **base_sum})

        # ablation ladder: champ + each family individually, and champ+all
        ladder = [("champ", ["champ"])]
        for f in ["direct", "league_env", "home_away", "matchup", "oppquality", "rich"]:
            ladder.append((f"champ+{f}", ["champ", f]))
        ladder.append(("champ+ALL", FAMILIES))
        ladder.append(("matchup_only", ["matchup"]))
        ladder.append(("matchup+leagueenv+homeaway", ["matchup", "league_env", "home_away"]))

        for name, fams in ladder:
            X, names = matrix(fams)
            wf = H.walk_forward(X, y, comps, times)
            if wf is None:
                continue
            s = H.summarize(wf["y"], wf["p"], wf["comp"])
            results[cell][name] = s
            dist_rows.append({"cell": cell, "model": name, **s})
            d_ll = round(s["logloss"] - base_sum["logloss"], 5)
            d_br = round(s["brier"] - base_sum["brier"], 5)
            ablations.append({"cell": cell, "model": name, "n": s["n"],
                              "logloss": s["logloss"], "d_logloss_vs_champ": d_ll,
                              "brier": s["brier"], "d_brier_vs_champ": d_br,
                              "bss_pct": s["bss_pct"], "auc": s["auc"], "ece": s["ece"],
                              "p_std": s["p_std"], "calib_slope": s["calib_slope"]})
        print(f"[{time.time()-t0:.0f}s] {cell}: champ LL={base_sum['logloss']} "
              f"AUC={base_sum['auc']} p_std={base_sum['p_std']} n={base_sum['n']}")

    json.dump(results, open(f"{OUT}/ablation_results.json", "w"), indent=2, default=str)
    # CSV
    import csv
    with open(f"{OUT}/ABLATIONS.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cell", "model", "n", "logloss", "d_logloss_vs_champ",
                                          "brier", "d_brier_vs_champ", "bss_pct", "auc", "ece",
                                          "p_std", "calib_slope"])
        w.writeheader()
        for r in ablations:
            w.writerow(r)
    print(f"[{time.time()-t0:.0f}s] wrote ablation_results.json + ABLATIONS.csv ({len(ablations)} rows)")


if __name__ == "__main__":
    main()
