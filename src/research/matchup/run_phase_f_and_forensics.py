"""PHASE F (count models) + uncertainty (bootstrap CIs) + per-competition stability
+ overdispersion diagnostics + line coherence + confidence ladder.

Reuses the cached feature families implicitly by rebuilding once per market family.
Deterministic. Writes research/contextual_matchup/out/ tables.
"""
from __future__ import annotations
import os, sys, json, time, warnings
from collections import defaultdict
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu")

from src.research.matchup.corpus import load_corpus
from src.research.matchup.design import DesignBuilder, outcome
from src.research.matchup import harness as H
from src.research.matchup import count_models as CM

OUT = "/home/ubuntu/research/contextual_matchup/out"
os.makedirs(OUT, exist_ok=True)
RNG = np.random.default_rng(12345)


def block_bootstrap_dll(y, p_a, p_b, comps, n_boot=400):
    """Paired bootstrap of LogLoss difference (p_b - p_a) over competition blocks.
    Returns (mean_diff, ci_lo, ci_hi, p_b_better_frac)."""
    y = np.asarray(y); p_a = np.clip(p_a, 1e-6, 1 - 1e-6); p_b = np.clip(p_b, 1e-6, 1 - 1e-6)
    ll_a = -(y * np.log(p_a) + (1 - y) * np.log(1 - p_a))
    ll_b = -(y * np.log(p_b) + (1 - y) * np.log(1 - p_b))
    diff = ll_b - ll_a  # negative => B better
    # blocks by competition
    blocks = defaultdict(list)
    for i, c in enumerate(comps):
        blocks[c].append(i)
    keys = list(blocks.keys())
    obs = float(diff.mean())
    boots = []
    for _ in range(n_boot):
        idx = []
        for k in RNG.choice(keys, size=len(keys), replace=True):
            idx.extend(blocks[k])
        boots.append(float(diff[idx].mean()))
    boots = np.array(boots)
    return obs, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)), float((boots < 0).mean())


def build_market(recs, db, market, lineval, fams):
    fam_fns = {"champ": db.f_champ, "matchup": db.f_matchup, "league_env": db.f_league_env,
               "home_away": db.f_home_away, "rich": db.f_rich, "oppquality": db.f_oppquality,
               "direct": db.f_direct}
    data = {f: [] for f in fams}; y = []; comps = []; gh = []; ga = []; ck = []
    for rec in recs:
        o = outcome(rec, market, lineval)
        if o is None:
            continue
        y.append(o); comps.append(rec.competition)
        gh.append(rec.base.get("homeGoalCount")); ga.append(rec.base.get("awayGoalCount"))
        pair = rec.rich.get("corner_kicks")
        ck.append(pair if pair else (None, None))
        for f in fams:
            data[f].append(fam_fns[f](rec, market))
    y = np.array(y)
    names = {}
    for f in fams:
        ks = set()
        for d in data[f]:
            ks.update(d.keys())
        names[f] = sorted(ks)

    def matrix(fam_list):
        cols = [(f, k) for f in fam_list for k in names[f]]
        M = np.full((len(y), len(cols)), np.nan)
        for c, (f, k) in enumerate(cols):
            for i, d in enumerate(data[f]):
                v = d.get(k)
                if v is not None:
                    M[i, c] = v
        return M
    return y, comps, gh, ga, ck, matrix


def main():
    t0 = time.time()
    recs = load_corpus()
    db = DesignBuilder(recs)
    for s in ["xg", "corner_kicks", "cards"]:
        db.ratings(s)
    print(f"[{time.time()-t0:.0f}s] setup done")

    uncertainty = []   # champion vs best-linear-challenger CI per cell
    countrows = []     # count-model comparison
    dispersion = []
    coherence_rows = []
    confladder = []

    # ---- Linear challenger uncertainty: champ vs champ+matchup+leagueenv+homeaway ----
    LIN_FAMS = ["champ", "matchup", "league_env", "home_away"]
    MARKETS = [("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
               ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
               ("cards", 3.5), ("cards", 4.5), ("btts", None)]
    # store challenger p per (market,line) for coherence + confidence ladder
    chal_p = {}
    for market, lineval in MARKETS:
        cell = f"{market}_{lineval}"
        y, comps, gh, ga, ck, matrix = build_market(recs, db, market, lineval, LIN_FAMS)
        Xc = matrix(["champ"]); Xch = matrix(LIN_FAMS)
        wf_c = H.walk_forward(Xc, y, comps, list(range(len(y))))
        wf_ch = H.walk_forward(Xch, y, comps, list(range(len(y))))
        if wf_c is None or wf_ch is None:
            continue
        # align (same test rows since same y ordering/folds)
        yb, pc, pch, cb = wf_c["y"], wf_c["p"], wf_ch["p"], wf_c["comp"]
        obs, lo, hi, frac = block_bootstrap_dll(yb, pc, pch, cb)
        cls = ("CLEAR" if hi < -0.001 else "PROMISING" if hi < 0 and obs < -0.0005 else
               "MARGINAL" if obs < 0 else "INCONCLUSIVE" if lo < 0 < hi else "NEGATIVE")
        sc = H.summarize(yb, pc); sch = H.summarize(yb, pch)
        uncertainty.append({"cell": cell, "champ_ll": sc["logloss"], "chal_ll": sch["logloss"],
                            "d_ll": round(obs, 5), "ci_lo": round(lo, 5), "ci_hi": round(hi, 5),
                            "p_chal_better": round(frac, 3), "class": cls,
                            "champ_auc": sc["auc"], "chal_auc": sch["auc"],
                            "champ_pstd": sc["p_std"], "chal_pstd": sch["p_std"],
                            "chal_calib_slope": sch["calib_slope"]})
        chal_p[cell] = (yb, pch, cb)
        print(f"[{time.time()-t0:.0f}s] {cell}: dLL={obs:+.5f} CI[{lo:+.5f},{hi:+.5f}] {cls}")

    # ---- Count models: goals & corners ----
    CNT_FAMS = ["matchup", "league_env", "home_away"]
    for market in ["goals", "corners"]:
        y_dummy, comps, gh, ga, ck, matrix = build_market(recs, db, market, 2.5 if market == "goals" else 9.5, CNT_FAMS)
        X = matrix(CNT_FAMS)
        # home/away count targets
        if market == "goals":
            th = np.array([g if g is not None else np.nan for g in gh], float)
            ta = np.array([g if g is not None else np.nan for g in ga], float)
            lines = [1.5, 2.5, 3.5]
        else:
            th = np.array([c[0] if c[0] is not None else np.nan for c in ck], float)
            ta = np.array([c[1] if c[1] is not None else np.nan for c in ck], float)
            lines = [8.5, 9.5, 10.5]
        valid = ~(np.isnan(th) | np.isnan(ta))
        Xv, thv, tav, cv = X[valid], th[valid], ta[valid], [comps[i] for i in range(len(valid)) if valid[i]]
        n = len(thv)
        # overdispersion
        tot = thv + tav
        disp = {"market": market, "mean_total": round(float(tot.mean()), 3),
                "var_total": round(float(tot.var()), 3),
                "overdispersion_ratio": round(float(tot.var() / tot.mean()), 3),
                "home_mean": round(float(thv.mean()), 3), "away_mean": round(float(tav.mean()), 3)}
        dispersion.append(disp)
        # walk-forward count model producing coherent line probs
        bounds = np.linspace(0, n, 5, dtype=int)
        pois = {L: [] for L in lines}; nb = {L: [] for L in lines}; ys = {L: [] for L in lines}
        comp_acc = []
        for fi in range(2, 5):
            tr_hi = bounds[fi - 1]; te_lo, te_hi = bounds[fi - 1], bounds[fi]
            if tr_hi < 400:
                continue
            Xtr, Xte = Xv[:tr_hi], Xv[te_lo:te_hi]
            lh, la = CM.fit_poisson_means(Xtr, thv[:tr_hi], tav[:tr_hi], Xte)
            r_tot = CM.fit_nb_dispersion(thv[:tr_hi] + tav[:tr_hi])
            for i, L in enumerate(lines):
                pp = CM.total_over_prob_poisson(lh, la, L)
                pois[L].append(np.clip(pp, 0.01, 0.99))
                if r_tot:
                    pn = CM.total_over_prob_nb(lh, la, L, r_tot)
                    nb[L].append(np.clip(pn, 0.01, 0.99))
                yl = (thv[te_lo:te_hi] + tav[te_lo:te_hi] > L).astype(float)
                ys[L].append(yl)
            comp_acc.append([cv[i] for i in range(te_lo, te_hi)])
        # summarize count model per line and compare to champion linear on same rows
        for L in lines:
            if not pois[L]:
                continue
            P = np.concatenate(pois[L]); Y = np.concatenate(ys[L])
            s = H.summarize(Y, P)
            # champion linear baseline on the SAME line (recompute champ-only)
            cell = f"{market}_{L}"
            base = None
            # reuse champion metric from uncertainty table
            for u in uncertainty:
                if u["cell"] == cell:
                    base = u["champ_ll"]
            countrows.append({"cell": cell, "model": "poisson_count",
                              "n": s["n"], "logloss": s["logloss"], "brier": s["brier"],
                              "auc": s["auc"], "p_std": s["p_std"], "calib_slope": s["calib_slope"],
                              "champ_ll": base, "d_ll_vs_champ": round(s["logloss"] - base, 5) if base else None})
            if nb[L]:
                PN = np.concatenate(nb[L])
                sn = H.summarize(Y, PN)
                countrows.append({"cell": cell, "model": "nb_count",
                                  "n": sn["n"], "logloss": sn["logloss"], "brier": sn["brier"],
                                  "auc": sn["auc"], "p_std": sn["p_std"], "calib_slope": sn["calib_slope"],
                                  "champ_ll": base, "d_ll_vs_champ": round(sn["logloss"] - base, 5) if base else None})
        print(f"[{time.time()-t0:.0f}s] count {market}: disp={disp['overdispersion_ratio']}")

    # ---- per-competition stability of the linear challenger ----
    comp_stab = []
    for cell, (yb, pch, cb) in chal_p.items():
        # champion p for same rows
        cbase = None
        for u in uncertainty:
            if u["cell"] == cell:
                cbase = u
        by = defaultdict(list)
        for i, c in enumerate(cb):
            by[c].append(i)
        for comp, idxs in by.items():
            if len(idxs) < 150:
                continue
            idxs = np.array(idxs)
            yc = yb[idxs]; pchc = pch[idxs]
            comp_stab.append({"cell": cell, "competition": comp, "n": len(idxs),
                              "chal_ll": round(H.logloss(yc, pchc), 5),
                              "chal_auc": round(H.auc(yc, pchc), 4) if H.auc(yc, pchc) else None,
                              "base_rate": round(float(yc.mean()), 3)})

    # ---- confidence ladder for the linear challenger (pooled) ----
    for cell, (yb, pch, cb) in chal_p.items():
        conf = np.abs(pch - 0.5)
        for lo, hi in [(0, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 1.0)]:
            mk = (conf >= lo) & (conf < hi)
            if mk.sum() < 30:
                continue
            acc = float(((pch[mk] >= 0.5).astype(float) == yb[mk]).mean())
            confladder.append({"cell": cell, "conf_bucket": f"[{lo},{hi})", "n": int(mk.sum()),
                               "dir_acc": round(acc, 4)})

    # ---- line coherence: does the linear challenger violate monotonicity across lines? ----
    for market, ls in [("goals", [1.5, 2.5, 3.5]), ("corners", [8.5, 9.5, 10.5])]:
        cells = [f"{market}_{L}" for L in ls]
        if not all(c in chal_p for c in cells):
            continue
        # need per-row p aligned; chal_p rows are per-cell walk-forward — same ordering/folds -> aligned
        ps = [chal_p[c][1] for c in cells]
        m = min(len(p) for p in ps)
        ps = [p[:m] for p in ps]
        viol = np.mean((ps[0] < ps[1]) | (ps[1] < ps[2]))
        coherence_rows.append({"market": market, "model": "linear_challenger",
                               "monotonicity_violation_rate": round(float(viol), 4), "n": m})

    import csv
    def dump(name, rows, cols):
        with open(f"{OUT}/{name}", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for r in rows:
                w.writerow(r)
    dump("UNCERTAINTY.csv", uncertainty, list(uncertainty[0].keys()))
    dump("COUNT_MODELS.csv", countrows, list(countrows[0].keys()))
    dump("OVERDISPERSION.csv", dispersion, list(dispersion[0].keys()))
    dump("COMPETITION_STABILITY.csv", comp_stab, list(comp_stab[0].keys()))
    dump("CONFIDENCE_LADDER.csv", confladder, list(confladder[0].keys()))
    dump("LINE_COHERENCE.csv", coherence_rows, list(coherence_rows[0].keys()))
    print(f"[{time.time()-t0:.0f}s] wrote UNCERTAINTY/COUNT_MODELS/OVERDISPERSION/COMPETITION_STABILITY/CONFIDENCE_LADDER/LINE_COHERENCE")


if __name__ == "__main__":
    main()
