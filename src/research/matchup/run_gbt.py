"""PHASE G: limited nonlinear challenger (gradient-boosted trees) on the matchup
feature set, vs champion-parity linear, for goals_2.5 and corners_9.5.

Interpretability is not the optimization target; this only tests whether nonlinearity
buys anything the linear/count models miss. Chronological OOS, train-only fit.
"""
from __future__ import annotations
import os, sys, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu")
from sklearn.ensemble import HistGradientBoostingClassifier
from src.research.matchup.corpus import load_corpus
from src.research.matchup.design import DesignBuilder, outcome
from src.research.matchup import harness as H

OUT = "/home/ubuntu/research/contextual_matchup/out"


def main():
    recs = load_corpus(); db = DesignBuilder(recs)
    for s in ["xg", "corner_kicks"]: db.ratings(s)
    FAMS = ["champ", "matchup", "league_env", "home_away", "rich"]
    fam_fns = {"champ": db.f_champ, "matchup": db.f_matchup, "league_env": db.f_league_env,
               "home_away": db.f_home_away, "rich": db.f_rich}
    rows = []
    for market, line in [("goals", 2.5), ("corners", 9.5), ("cards", 4.5)]:
        data = {f: [] for f in FAMS}; y = []; comps = []
        for rec in recs:
            o = outcome(rec, market, line)
            if o is None: continue
            y.append(o); comps.append(rec.competition)
            for f in FAMS: data[f].append(fam_fns[f](rec, market))
        y = np.array(y)
        cols = [(f, k) for f in FAMS for k in sorted({k for d in data[f] for k in d})]
        M = np.full((len(y), len(cols)), np.nan)
        for c, (f, k) in enumerate(cols):
            for i, d in enumerate(data[f]):
                v = d.get(k)
                if v is not None: M[i, c] = v
        # GBT handles NaN natively; walk-forward
        n = len(y); bounds = np.linspace(0, n, 5, dtype=int)
        P = []; Y = []
        for fi in range(2, 5):
            tr_hi = bounds[fi - 1]; te_lo, te_hi = bounds[fi - 1], bounds[fi]
            if tr_hi < 400: continue
            clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                 max_iter=200, l2_regularization=1.0,
                                                 min_samples_leaf=50, random_state=0)
            clf.fit(M[:tr_hi], y[:tr_hi])
            p = np.clip(clf.predict_proba(M[te_lo:te_hi])[:, 1], 0.01, 0.99)
            P.append(p); Y.append(y[te_lo:te_hi])
        P = np.concatenate(P); Y = np.concatenate(Y)
        s = H.summarize(Y, P)
        rows.append({"cell": f"{market}_{line}", "model": "gbt_matchup", **s})
        print(f"{market}_{line} GBT: LL={s['logloss']} Brier={s['brier']} AUC={s['auc']} p_std={s['p_std']} calib={s['calib_slope']}")
    import csv, json
    json.dump(rows, open(f"{OUT}/GBT.json", "w"), indent=2, default=str)
    print("wrote GBT.json")


if __name__ == "__main__":
    main()
