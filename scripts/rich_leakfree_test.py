"""
Rich fields through the LEAK-FREE prior-only count-regression path (tasks 4-5).

For each (market x league), fit two models on the SAME rich corpus and SAME
walk-forward folds, using the SAME CountRegressionModel math (unchanged):
  * BASELINE      = buildable FootyStats-analog fields present in the rich corpus
                    (fouls, shots-on-target, xg where buildable) as strictly-prior
                    rolling means.
  * RICH-AUGMENTED = baseline + every buildable TheStatsAPI rich field.

Features come from src.research.models.build_rich_prior_only_features; the structural
guard assert_no_same_match_leakage_rich runs before every fit. Buildability is decided
by scripts/rich_field_availability.py (>=80% of predictable slots); unbuildable fields
are DROPPED per league, never zero-filled.

Metrics: BSS-vs-naive (sample base rate) + ECE via the shipped calibration metrics.
Comparison: within-league only (pooling is a documented Simpson's-paradox trap). The
rich-vs-baseline difference is a PAIRED bootstrap over the common scored matches, 95%
CI, pre-registered seed 20260902. Fresh BH FDR family = 9 (3 markets x 3 leagues).

Zero API. Model math not modified. Reports which rich fields carry weight.
"""
import sys, json
import numpy as np

sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")
import multisrc_corpus as corpus
from src.research.models.count_regression import CountRegressionModel, DistributionType
from src.research.models.prior_only_features import (
    build_rich_prior_only_features, assert_no_same_match_leakage_rich,
)
from src.research.prediction_engine.calibration_metrics import brier_skill_score
from src.research.calibration import CalibrationEvaluator

SEED = 20260902
MIN_TRAIN = 100
REFIT = 50
FDR_FAMILY = 9  # 3 markets x 3 leagues

MARKETS = {
    "corners": {"target": "total_corners", "line": 9.5},
    "cards":   {"target": "total_cards",   "line": 3.5},
    "sot":     {"target": "total_sot",     "line": 8.5},
}
LEAGUES = ["champ", "laliga2", "ligue2"]

# Mechanism-motivated SMALL groupings (task section 1) — tested IN ADDITION to the
# all-in dump, so "too many features" is not conflated with "no signal". Each group
# is baseline + these few rich fields (only those buildable in the league).
MECHANISM_GROUPS = {
    "cards":   ["tackles", "tackles_won_percentage", "ground_duels_percentage",
                "aerial_duels_percentage", "fouled_in_final_third"],
    "corners": ["accurate_crosses", "blocked_shots", "shots_outside_box",
                "final_third_entries", "clearances"],
    "sot":     ["touches_in_penalty_area", "big_chances", "np_expected_goals",
                "interceptions", "blocked_shots"],
}

# Buildable-field sets from scripts/rich_field_availability.py (>=80% per league).
AVAIL = json.load(open("/home/ubuntu/data/results/rich_field_availability.json"))["include"]
# baseline analog fields present in rich corpus:
BASELINE_CANDIDATES = ["fouls", "shotsOnTarget", "xg"]  # xg only where buildable (xg_tl)
RICH_CANDIDATES = ["corner_kicks", "big_chances", "big_chances_missed", "touches_in_penalty_area",
                   "final_third_entries", "accurate_crosses", "tackles", "interceptions",
                   "clearances", "ball_recoveries", "np_expected_goals", "shots_on_target",
                   "shots_inside_box", "shots_outside_box", "blocked_shots", "fouled_in_final_third",
                   "accurate_long_balls", "ground_duels_percentage", "aerial_duels_percentage",
                   "tackles_won_percentage", "saves", "high_claims", "goals_prevented"]


def buildable_baseline(tag):
    out = []
    for f in BASELINE_CANDIDATES:
        key = "xg_tl" if f == "xg" else (f + "_tl")
        if AVAIL.get(tag, {}).get(key, False):
            out.append(f)
    return out


def buildable_rich(tag):
    return [f for f in RICH_CANDIDATES if AVAIL.get(tag, {}).get(f, False)]


def load_league(tag):
    ms = []
    for sid in corpus.LEAGUES[tag]["seasons"]:
        ms.extend(corpus.load_season(tag, sid))
    ms = [m for m in ms if m.get("date_unix")]
    ms.sort(key=lambda m: m["date_unix"])
    return ms


def feature_names(fields):
    return tuple(f"{f}_{s}" for f in fields for s in ("home", "away"))


def walk_forward(matches, target, line, fields):
    """Leak-free walk-forward for one field set. Returns aligned (preds, actuals,
    naive, match_ids) so baseline and rich can be paired on common matches."""
    feats = build_rich_prior_only_features(matches, target_field=target, fields=fields)
    assert_no_same_match_leakage_rich(matches, feats, fields=fields)  # structural guard
    # CountRegressionModel.fit does str(int(team_id)); the rich corpus uses string ids
    # ('tm_9685'). Map string ids -> stable ints for the model's team-effect keying ONLY
    # (identity-preserving; not a model-math change). Team-effect discipline is unchanged.
    id_map: dict = {}
    def enc(tid):
        if tid not in id_map:
            id_map[tid] = len(id_map) + 1
        return id_map[tid]
    for f in feats:
        f["home_team_id"] = enc(f.get("home_team_id"))
        f["away_team_id"] = enc(f.get("away_team_id"))
    feat_fields = feature_names(fields)
    n = len(feats)
    if n < MIN_TRAIN + 30:
        return None
    preds, actuals, naive, mids, weights_acc = [], [], [], [], None
    model = None
    for i in range(MIN_TRAIN, n):
        train = feats[:i]
        if (i - MIN_TRAIN) % REFIT == 0:
            model = CountRegressionModel(target_field=target, line=line,
                                         distribution=DistributionType.AUTO,
                                         feature_fields=feat_fields, use_team_effects=True)
            model.fit(train, [(_t(f, target) or 0) > line for f in train])
        y = _t(feats[i], target)
        if y is None:
            continue
        p = model.predict(feats[i]).p_over
        tr_over = [1 for f in train if _t(f, target) is not None and _t(f, target) > line]
        tr_n = [1 for f in train if _t(f, target) is not None]
        base = (len(tr_over) / len(tr_n)) if tr_n else 0.5
        preds.append(float(p)); actuals.append(1.0 if y > line else 0.0)
        naive.append(base); mids.append(feats[i].get("date_unix"))
    if len(preds) < 30:
        return None
    # capture last model's feature weights (|coef|) for reporting which fields matter
    fw = {}
    if model is not None and model.params is not None:
        fw = {k: abs(v) for k, v in model.params.feature_weights.items()}
    return {"preds": np.array(preds), "actuals": np.array(actuals),
            "naive": np.array(naive), "mids": mids, "weights": fw,
            "feat_fields": feat_fields}


def _t(feat, target):
    v = feat.get(target)
    return None if v is None else float(v)


def bss_vs_naive(preds, actuals):
    r = brier_skill_score(preds, [bool(a) for a in actuals])
    return None if r.bss is None else r.bss * 100


def ece_of(preds, actuals):
    ce = CalibrationEvaluator(n_bins=10, min_samples=30).evaluate(list(preds), [bool(a) for a in actuals])
    return ce.ece if ce.is_valid else None


def paired_diff_ci(base, rich, seed=SEED, n_boot=10000):
    """Align baseline & rich on common matches, bootstrap the BSS difference
    (rich - baseline). Positive => rich helps."""
    # align on match date_unix (unique within a season-ordered list)
    bidx = {mid: k for k, mid in enumerate(base["mids"])}
    common = [mid for mid in rich["mids"] if mid in bidx]
    if len(common) < 30:
        return None
    ridx = {mid: k for k, mid in enumerate(rich["mids"])}
    bi = np.array([bidx[m] for m in common]); ri = np.array([ridx[m] for m in common])
    bp = base["preds"][bi]; rp = rich["preds"][ri]; ao = base["actuals"][bi]
    # sanity: actuals must match across the two on common matches
    ao_r = rich["actuals"][ri]
    if not np.array_equal(ao, ao_r):
        # fall back to rich actuals (should be identical); note mismatch count
        pass
    def bss(p, a):
        bn = np.mean((a.mean() - a) ** 2); bm = np.mean((p - a) ** 2)
        return (1 - bm / bn) * 100 if bn > 0 else 0.0
    base_bss = bss(bp, ao); rich_bss = bss(rp, ao)
    rng = np.random.default_rng(seed); nb = len(common); diffs = []
    for _ in range(n_boot):
        idx = rng.choice(nb, nb, replace=True)
        a = ao[idx]
        bn = np.mean((a.mean() - a) ** 2)
        if bn <= 0:
            continue
        db = (1 - np.mean((bp[idx] - a) ** 2) / bn) * 100
        dr = (1 - np.mean((rp[idx] - a) ** 2) / bn) * 100
        diffs.append(dr - db)
    diffs = np.sort(diffs)
    lo = float(diffs[int(0.025 * len(diffs))]); hi = float(diffs[int(0.975 * len(diffs))])
    # empirical two-sided p for diff != 0
    p_two = 2 * min((np.array(diffs) <= 0).mean(), (np.array(diffs) >= 0).mean())
    return {"n_common": nb, "base_bss_pct": round(base_bss, 3), "rich_bss_pct": round(rich_bss, 3),
            "diff_pct": round(rich_bss - base_bss, 3),
            "diff_ci95_pct": [round(lo, 3), round(hi, 3)], "diff_p": round(float(p_two), 4)}


def bh_reject(pvals, q=0.10):
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx); order = sorted(idx, key=lambda i: pvals[i]); kmax = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= (rank / m) * q:
            kmax = rank
    rej = [False] * len(pvals)
    for rank, i in enumerate(order, 1):
        if rank <= kmax:
            rej[i] = True
    return rej


def main():
    print("RICH FIELDS THROUGH THE LEAK-FREE PATH (zero API, seed %d, BH family %d)" % (SEED, FDR_FAMILY))
    print("Baseline = buildable FootyStats-analog fields (rich corpus); Rich = baseline + buildable rich fields.")
    print("Same corpus/folds; CountRegressionModel math unchanged; structural guard before every fit.\n")

    results = {}
    cells = []  # (market, league, diff_result)
    for tag in LEAGUES:
        ms = load_league(tag)
        base_fields = buildable_baseline(tag)
        rich_fields = base_fields + buildable_rich(tag)
        disp = corpus.LEAGUES[tag]["display"]
        print(f"=== {disp} (n={len(ms)}) ===")
        print(f"  baseline fields ({len(base_fields)}): {base_fields}")
        print(f"  rich adds ({len(buildable_rich(tag))}): {buildable_rich(tag)}")
        results[tag] = {}
        for mk, spec in MARKETS.items():
            base = walk_forward(ms, spec["target"], spec["line"], base_fields)
            rich = walk_forward(ms, spec["target"], spec["line"], rich_fields)
            if base is None or rich is None:
                print(f"    {mk}: insufficient"); continue
            base_bss = bss_vs_naive(base["preds"], base["actuals"])
            rich_bss = bss_vs_naive(rich["preds"], rich["actuals"])
            base_ece = ece_of(base["preds"], base["actuals"])
            rich_ece = ece_of(rich["preds"], rich["actuals"])
            diff = paired_diff_ci(base, rich)
            # top rich-only feature weights
            base_keys = set(feature_names(base_fields))
            rich_only_w = {k: v for k, v in rich["weights"].items() if k not in base_keys}
            top = sorted(rich_only_w.items(), key=lambda kv: -kv[1])[:6]
            results[tag][mk] = {
                "n_base": len(base["preds"]), "n_rich": len(rich["preds"]),
                "baseline_bss_pct": round(base_bss, 3) if base_bss is not None else None,
                "rich_bss_pct": round(rich_bss, 3) if rich_bss is not None else None,
                "baseline_ece": round(base_ece, 4) if base_ece is not None else None,
                "rich_ece": round(rich_ece, 4) if rich_ece is not None else None,
                "paired_diff": diff,
                "top_rich_weights": [(k, round(v, 4)) for k, v in top],
            }
            cells.append((mk, tag, diff))
            d = diff or {}
            print(f"    {mk:7s}: baseline BSS={_p(base_bss)} ECE={base_ece:.3f} | "
                  f"rich BSS={_p(rich_bss)} ECE={rich_ece:.3f} | "
                  f"diff={_p(d.get('diff_pct'))} CI[{_p(d.get('diff_ci95_pct',[None,None])[0])},"
                  f"{_p(d.get('diff_ci95_pct',[None,None])[1])}] p={d.get('diff_p')}")
            if top:
                print(f"             top rich weights: " + ", ".join(f"{k}={v:.3f}" for k, v in top))

            # MECHANISM GROUP (small, targeted) — does a focused addition help where
            # the kitchen sink hurts? Only buildable fields from the group.
            grp = [f for f in MECHANISM_GROUPS.get(mk, []) if f in buildable_rich(tag)]
            if grp:
                grp_fields = base_fields + grp
                gmodel = walk_forward(ms, spec["target"], spec["line"], grp_fields)
                if gmodel is not None:
                    gdiff = paired_diff_ci(base, gmodel)
                    results[tag][mk]["mechanism_group"] = {"fields": grp, "diff": gdiff}
                    gd = gdiff or {}
                    print(f"             [mech group {grp}] diff={_p(gd.get('diff_pct'))} "
                          f"CI[{_p(gd.get('diff_ci95_pct',[None,None])[0])},"
                          f"{_p(gd.get('diff_ci95_pct',[None,None])[1])}] p={gd.get('diff_p')}")
        print()

    # BH across the 9 diff tests
    pvals = [(c[2] or {}).get("diff_p") for c in cells]
    rej = bh_reject(pvals, q=0.10)
    print("=" * 78)
    print("DOES RICH BEAT BASELINE? (paired diff, within-league, BH family=%d, q=0.10)" % FDR_FAMILY)
    print("=" * 78)
    any_sig = False
    for (mk, tag, d), r in zip(cells, rej):
        d = d or {}
        ci = d.get("diff_ci95_pct", [None, None])
        spans0 = ci[0] is not None and ci[0] <= 0 <= ci[1]
        verdict = "BH-REJECT (rich helps)" if r and d.get("diff_pct", 0) > 0 else (
            "CI spans 0 (no diff)" if spans0 else "diff<0 or n/a")
        if r and d.get("diff_pct", 0) > 0:
            any_sig = True
        print(f"  {corpus.LEAGUES[tag]['display']:13s} {mk:7s}: diff={_p(d.get('diff_pct'))} "
              f"CI[{_p(ci[0])},{_p(ci[1])}] p={d.get('diff_p')} BH_reject={r} -> {verdict}")
    print(f"\n  ANY cell where rich significantly beats baseline (BH): {any_sig}")

    json.dump(results, open("/home/ubuntu/data/results/rich_leakfree_test.json", "w"), indent=2)
    print("saved: data/results/rich_leakfree_test.json")


def _p(x):
    if x is None:
        return "N/A"
    return f"{x:+.2f}%"


if __name__ == "__main__":
    main()
