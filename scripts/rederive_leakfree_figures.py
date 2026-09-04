"""
FIX 2 re-derivation — honest, leak-free corners/cards figures.

Runs the SAME CountRegressionModel math (unchanged; audit found it sound), but fed by
the STRICTLY-PRIOR feature builder (src.research.models.prior_only_features) instead
of the leaking same-match default. Walk-forward, per league-season, on the cached
FootyStats corpus. Zero API (network hard-blocked). Scores with the shipped metrics.

The anti-leakage guard runs on EVERY league-season's features before any fit, so a
regression of this bug class is impossible to score silently.

Reports BSS-vs-naive (both sample-base and expanding-train-base) + ECE per market,
per league-season, plus a pooled 95% bootstrap CI. Per the audit's detection floor
(median CI half-width ~1.89%), a true ~1% edge will read as 'CI spans 0'. That is the
honest result and is reported as such.
"""
import os, sys, glob, re, json
import numpy as np

sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")

import src.research.footystats.client as fsclient
def _blocked(self, endpoint, params=None, **kw):
    rp = dict(params or {}); rp.setdefault("key", "BLOCKED")
    c = self._cache_get(self._cache_key(endpoint, rp))
    if c is not None:
        return c
    raise RuntimeError(f"ZERO-API GUARD blocked: {endpoint}")
fsclient.FootyStatsResearchClient._request = _blocked

from src.research.models.count_regression import create_corners_model, create_cards_model
from src.research.models.prior_only_features import (
    build_prior_only_features, assert_no_same_match_leakage,
)
from src.research.prediction_engine.calibration_metrics import brier_skill_score
from src.research.calibration import CalibrationEvaluator

CACHE = "/home/ubuntu/.cache/footystats_research"
MIN_TRAIN = 100
REFIT = 50


def cached_season_ids():
    ids = []
    for p in glob.glob(f"{CACHE}/league-matches_*season_id:_*.json"):
        m = re.search(r"season_id:_(\d+)", p)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def load_raw_matches(client, season_id):
    raw = client.fetch_season_matches(season_id)
    if not raw:
        return []
    ms = [m for m in raw if m.get("status") == "complete"
          and m.get("homeID") is not None and m.get("awayID") is not None
          and m.get("date_unix") is not None]
    ms.sort(key=lambda m: m["date_unix"])
    return ms


def walk_forward(matches, market):
    """Leak-free walk-forward for one market on one league-season."""
    if market == "corners":
        target, line, make = "total_corners", 9.5, create_corners_model
    else:
        target, line, make = "total_cards", 3.5, create_cards_model

    feats = build_prior_only_features(matches, target_field=target)
    # STRUCTURAL guard: prove no same-match leakage before any modelling.
    assert_no_same_match_leakage(matches, feats)

    n = len(feats)
    if n < MIN_TRAIN + 30:
        return None
    preds, actuals, naive = [], [], []
    model = None
    for i in range(MIN_TRAIN, n):
        train = feats[:i]
        if (i - MIN_TRAIN) % REFIT == 0:
            model = make(line=line)
            model.fit(train, [(_t(f, target) or 0) > line for f in train])
        y = _t(feats[i], target)
        if y is None:
            continue
        p = model.predict(feats[i]).p_over
        base = sum(1 for f in train if (_t(f, target) or -1) > line and _t(f, target) is not None) / \
               max(1, sum(1 for f in train if _t(f, target) is not None))
        preds.append(float(p)); actuals.append(1.0 if y > line else 0.0); naive.append(base)
    if len(preds) < 30:
        return None
    preds = np.array(preds); actuals = np.array(actuals); naive = np.array(naive)
    r = brier_skill_score(preds, [bool(a) for a in actuals])
    bm = np.mean((preds - actuals) ** 2); bn = np.mean((naive - actuals) ** 2)
    bss_train = (bn - bm) / bn * 100 if bn > 0 else None
    ce = CalibrationEvaluator(n_bins=10, min_samples=30).evaluate(list(preds), [bool(a) for a in actuals])
    return {"n": len(preds),
            "bss_vs_sample_base_pct": (r.bss * 100 if r.bss is not None else None),
            "bss_vs_train_naive_pct": bss_train,
            "ece": ce.ece, "brier": ce.brier_score,
            "preds": preds, "actuals": actuals}


def _t(feat, target):
    v = feat.get(target)
    return None if v is None else float(v)


def pooled_bootstrap_ci(all_preds, all_actuals, n_boot=10000, seed=20260902):
    p = np.concatenate(all_preds); a = np.concatenate(all_actuals)
    rng = np.random.default_rng(seed); n = len(p); boots = []
    for _ in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        bn = np.mean((a[idx].mean() - a[idx]) ** 2)
        bm = np.mean((p[idx] - a[idx]) ** 2)
        if bn > 0:
            boots.append((1 - bm / bn) * 100)
    boots = np.sort(boots)
    return {"n": n, "bss_pct": round(float(np.mean(boots)), 3),
            "ci95_pct": [round(float(boots[int(0.025*len(boots))]), 3),
                          round(float(boots[int(0.975*len(boots))]), 3)]}


def main():
    print("FIX 2 RE-DERIVATION — leak-free corners/cards (strictly-prior features), zero API")
    print("Model math UNCHANGED (CountRegressionModel); features from prior_only_features.")
    print("Anti-leakage guard runs before every fit.\n")
    client = fsclient.FootyStatsResearchClient(api_key="BLOCKED", cache_dir=__import__("pathlib").Path(CACHE))
    sids = cached_season_ids()

    out = {"corners": {"rows": [], "preds": [], "actuals": []},
           "cards": {"rows": [], "preds": [], "actuals": []}}
    done = 0
    for sid in sids:
        if done >= 12:
            break
        ms = load_raw_matches(client, sid)
        if len(ms) < MIN_TRAIN + 30:
            continue
        line_printed = False
        for market in ("corners", "cards"):
            try:
                r = walk_forward(ms, market)
            except AssertionError as e:
                print(f"  season {sid} {market}: LEAKAGE GUARD FIRED -> {str(e)[:80]}")
                r = None
            if r is None:
                continue
            out[market]["rows"].append({"season_id": sid, "n": r["n"],
                                        "bss_sample_pct": r["bss_vs_sample_base_pct"],
                                        "bss_train_pct": r["bss_vs_train_naive_pct"],
                                        "ece": r["ece"]})
            out[market]["preds"].append(r["preds"]); out[market]["actuals"].append(r["actuals"])
            print(f"  season {sid:6d} {market:7s}: n={r['n']:4d}  BSS(sample)={_p(r['bss_vs_sample_base_pct'])}  "
                  f"BSS(train)={_p(r['bss_vs_train_naive_pct'])}  ECE={r['ece']:.4f}")
            line_printed = True
        if line_printed:
            done += 1

    print("\n" + "=" * 78)
    print("HONEST LEAK-FREE FIGURES — WITHIN-LEAGUE (never pooled: pooling mixes")
    print("league base rates and produces a Simpson's-paradox false positive, a")
    print("confound already documented in this project).")
    print("=" * 78)
    summary = {}
    for market in ("corners", "cards"):
        rows = out[market]["rows"]
        if not rows:
            print(f"  {market}: no usable league-seasons"); continue
        samp = np.array([r["bss_sample_pct"] for r in rows if r["bss_sample_pct"] is not None])
        eces = [r["ece"] for r in rows if r["ece"] is not None]
        n_pos = int(np.sum(samp > 0)); n_cells = len(samp)
        # within-league mean BSS with a bootstrap CI OVER CELLS (each cell = one
        # league-season's within-league BSS). This respects the within-league unit.
        rng = np.random.default_rng(20260902)
        cell_means = [float(np.mean(samp[rng.choice(n_cells, n_cells, replace=True)]))
                      for _ in range(10000)]
        cell_means.sort()
        ci = [round(cell_means[250], 3), round(cell_means[9750], 3)]
        # POOLED figure computed too, but explicitly flagged as a confounded strawman.
        pooled = pooled_bootstrap_ci(out[market]["preds"], out[market]["actuals"])
        summary[market] = {
            "n_cells": n_cells,
            "within_league_mean_bss_pct": round(float(np.mean(samp)), 3),
            "within_league_median_bss_pct": round(float(np.median(samp)), 3),
            "within_league_bss_ci95_over_cells_pct": ci,
            "cells_positive": f"{n_pos}/{n_cells}",
            "mean_ece": round(float(np.mean(eces)), 4),
            "pooled_bss_pct_CONFOUNDED": pooled["bss_pct"],
            "pooled_note": ("pooled BSS is CONFOUNDED by between-league base-rate "
                            "variation (Simpson); NOT a within-league skill figure"),
        }
        spans0 = ci[0] <= 0 <= ci[1]
        print(f"  {market:7s}: cells={n_cells}  within-league mean BSS={np.mean(samp):+.2f}%  "
              f"median={np.median(samp):+.2f}%  positive={n_pos}/{n_cells}  mean ECE={np.mean(eces):.4f}")
        print(f"           within-league mean BSS 95% CI (over cells) [{ci[0]:+.2f}, {ci[1]:+.2f}]  "
              f"-> {'CI spans 0: NO within-league skill (honest null)' if spans0 else 'CI excludes 0'}")
        print(f"           [pooled BSS {pooled['bss_pct']:+.2f}% is CONFOUNDED (Simpson) — NOT reported as skill]")

    json.dump(summary, open("/home/ubuntu/data/results/leakfree_rederivation.json", "w"), indent=2)
    print("\nCONTRAST: the WITHDRAWN leaked figures were corners ~+6.8/+9.6%, cards ~+6.1/+9.0%.")
    print("These leak-free numbers are the honest re-derivation. Do NOT present the")
    print("counterfactual zeroing numbers (~+1%) as validated; these bootstrap CIs are the result.")
    print("saved: /home/ubuntu/data/results/leakfree_rederivation.json")


def _p(x):
    return "N/A" if x is None else f"{x:+.2f}%"


if __name__ == "__main__":
    main()
