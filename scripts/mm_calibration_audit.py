"""
Calibration audit — MEASUREMENT ONLY. No refit-with-different-settings, no retune,
no post-hoc calibration. Reproduces the EXACT mm_models.py walk-forward fit path
(same feature pool, >=50% train-coverage filter, train-median imputation, train
standardization, L1 LogisticRegressionCV over the same C grid) and reads out, per
(market, line, league) model:

  - out-of-sample reliability curve: 10 uniform predicted-prob buckets vs realized
    outcome rate, with bucket counts and Wilson 95% CIs; flag buckets whose realized
    rate falls outside the predicted-rate CI
  - in-sample vs out-of-sample Brier (the direct overfitting gap)
  - selected-feature count (L1 sparsity), effective sample per selected parameter
  - the fitted L1 C (= the only 'shrinkage' these models have; no team-level layer)
  - per-bucket over/under-confidence classification (tail focus)

The fit is byte-for-byte the same estimator mm_models.py used, so numbers match that
run up to the known liblinear-CV jitter; we run each model twice with the identical
protocol and report whether the calibration verdict is invariant to that jitter.
"""
from __future__ import annotations
import sys, json, time, warnings
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
warnings.filterwarnings('ignore')

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_BROAD, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches
from src.discovery.corpus import load_discovery_set
from mm_models import TARGETS, feature_pool, fit_eval, MIN_TRAIN, MIN_TEST, CV_CS
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV

N_BINS = 10  # same uniform binning as mm_models.py ECE


def wilson(k, n, z=1.96):
    """Wilson 95% CI for a binomial rate k/n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (max(0.0, c-h), min(1.0, c+h))


def audit_one(matches, feats, target_fn):
    """Reproduce mm_models.fit_eval's fit EXACTLY, then read out calibration/overfit
    diagnostics. Returns None on the same insufficiency conditions as fit_eval."""
    n = len(matches)
    split = int(n * 0.6)
    train_idx = list(range(split)); test_idx = list(range(split, n))

    def cov(idx, f):
        return np.mean([matches[i]['_f'].get(f) is not None for i in idx])
    usable = [f for f in feats if cov(train_idx, f) >= 0.5]
    if len(usable) < 3:
        return None

    def build(idx):
        X, y = [], []
        for i in idx:
            o = target_fn(matches[i])
            if o is None:
                continue
            X.append([matches[i]['_f'].get(f) for f in usable]); y.append(o)
        return X, np.array(y, float)
    Xtr_raw, ytr = build(train_idx); Xte_raw, yte = build(test_idx)
    if len(Xtr_raw) < MIN_TRAIN or len(Xte_raw) < MIN_TEST:
        return None
    if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
        return None
    Xtr = np.array([[np.nan if v is None else v for v in r] for r in Xtr_raw], float)
    Xte = np.array([[np.nan if v is None else v for v in r] for r in Xte_raw], float)
    med = np.nanmedian(Xtr, axis=0); med = np.where(np.isnan(med), 0.0, med)
    def imp(X):
        idx = np.where(np.isnan(X)); X = X.copy(); X[idx] = np.take(med, idx[1]); return X
    Xtr = imp(Xtr); Xte = imp(Xte)
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr_s = (Xtr - mu) / sd; Xte_s = (Xte - mu) / sd

    try:
        clf = LogisticRegressionCV(Cs=CV_CS, cv=4, penalty='l1', solver='liblinear',
                                   scoring='neg_log_loss', max_iter=2000, refit=True)
        clf.fit(Xtr_s, ytr); C = float(clf.C_[0])
    except Exception:
        clf = LogisticRegression(C=0.1, penalty='l1', solver='liblinear', max_iter=2000)
        clf.fit(Xtr_s, ytr); C = 0.1
    coefs = clf.coef_[0]
    n_sel = int(np.sum(np.abs(coefs) > 1e-8))

    # in-sample vs OOS Brier (overfitting gap)
    p_tr = np.clip(clf.predict_proba(Xtr_s)[:, 1], 0.01, 0.99)
    p_te = np.clip(clf.predict_proba(Xte_s)[:, 1], 0.01, 0.99)
    brier_is = float(np.mean((p_tr - ytr) ** 2))
    brier_oos = float(np.mean((p_te - yte) ** 2))
    base = float(yte.mean()); nb = base*(1-base)
    bss = (1 - brier_oos/nb)*100 if nb > 0 else 0.0

    # reliability curve on OOS, 10 uniform bins
    buckets = []
    ece = 0.0
    over_mass = under_mass = 0.0  # signed mass for over/under-confidence at tails
    for b in range(N_BINS):
        lo, hi = b/N_BINS, (b+1)/N_BINS
        mk = (p_te >= lo) & (p_te < hi if b < N_BINS-1 else p_te <= hi)
        cnt = int(mk.sum())
        if cnt == 0:
            buckets.append({'bin': f'[{lo:.1f},{hi:.1f})', 'n': 0}); continue
        pred = float(p_te[mk].mean()); real = float(yte[mk].mean())
        k = int(yte[mk].sum())
        lo_ci, hi_ci = wilson(k, cnt)
        outside = not (lo_ci <= pred <= hi_ci)  # is predicted rate outside realized-rate CI
        ece += (cnt/len(p_te)) * abs(pred - real)
        # over/under confidence: for prob>0.5 bins, pred>real => overconfident high side
        if pred >= 0.5:
            if pred > real: over_mass += (cnt/len(p_te))*(pred-real)
            else: under_mass += (cnt/len(p_te))*(real-pred)
        else:
            if pred < real: over_mass += (cnt/len(p_te))*(real-pred)  # overconfident low side
            else: under_mass += (cnt/len(p_te))*(pred-real)
        buckets.append({'bin': f'[{lo:.1f},{hi:.1f})', 'n': cnt, 'pred': round(pred,4),
                        'real': round(real,4), 'real_ci': [round(lo_ci,4), round(hi_ci,4)],
                        'pred_outside_ci': bool(outside)})

    n_outside = sum(1 for b in buckets if b.get('pred_outside_ci'))
    n_populated = sum(1 for b in buckets if b.get('n', 0) > 0)
    # calibration label
    if over_mass > under_mass and over_mass > 0.02:
        label = 'overconfident'
    elif under_mass > over_mass and under_mass > 0.02:
        label = 'underconfident'
    else:
        label = 'calibrated'

    return {'C': C, 'n_features_selected': n_sel, 'n_train': len(Xtr), 'n_test': len(Xte),
            'eff_sample_per_param': round(len(Xtr)/max(n_sel,1), 1),
            'brier_is': round(brier_is,5), 'brier_oos': round(brier_oos,5),
            'overfit_gap': round(brier_oos-brier_is,5), 'bss_pct': round(bss,4),
            'ece_oos': round(ece,4), 'base_rate': round(base,4),
            'n_buckets_populated': n_populated, 'n_buckets_pred_outside_ci': n_outside,
            'over_mass': round(over_mass,4), 'under_mass': round(under_mass,4),
            'calibration_label': label, 'reliability_curve': buckets}


def run_config(name, matches, base_stats, seeds=(0, 1)):
    build_features(matches, base_stats)
    feats = feature_pool(base_stats)
    by_league = defaultdict(list)
    for m in matches:
        by_league[m['_league']].append(m)
    models = {}
    for lg in sorted(by_league):
        ms = sorted(by_league[lg], key=lambda m: m.get('date_unix', 0))
        if len(ms) < 260:
            continue
        lgm = {}
        for tname, tfn in TARGETS.items():
            # run twice for jitter-invariance of the calibration LABEL
            r1 = audit_one(ms, feats, tfn)
            if r1 is None:
                continue
            r2 = audit_one(ms, feats, tfn)
            r1['label_invariant'] = (r2 is not None and r2['calibration_label'] == r1['calibration_label'])
            r1['ece_oos_rerun'] = r2['ece_oos'] if r2 else None
            lgm[tname] = r1
        if lgm:
            models[lg] = lgm
    return {'config': name, 'n_feature_pool': len(feats), 'leagues': models}


def summarize(cfg):
    rows = [(lg, t, m) for lg, lm in cfg['leagues'].items() for t, m in lm.items()]
    import statistics as st
    def dist(vals):
        vals = sorted(vals)
        q = lambda p: vals[min(len(vals)-1, int(p*len(vals)))]
        return {'n': len(vals), 'min': round(min(vals),4), 'q1': round(q(.25),4),
                'median': round(st.median(vals),4), 'q3': round(q(.75),4), 'max': round(max(vals),4)}
    labels = defaultdict(int)
    for _,_,m in rows: labels[m['calibration_label']] += 1
    return {'n_models': len(rows),
            'ece_oos_dist': dist([m['ece_oos'] for _,_,m in rows]),
            'overfit_gap_dist': dist([m['overfit_gap'] for _,_,m in rows]),
            'eff_sample_per_param_dist': dist([m['eff_sample_per_param'] for _,_,m in rows]),
            'calibration_labels': dict(labels),
            'n_label_invariant': sum(1 for _,_,m in rows if m['label_invariant'])}


def main():
    t0 = time.time()
    print("PRIMARY (rich, mixed) calibration audit...")
    rich = load_rich_matches()
    primary = run_config('primary_rich_mixed', rich, BASE_STATS_RICH)
    print("  summary:", json.dumps(summarize(primary)))

    print("SECONDARY (broad, core) calibration audit...")
    broad = load_discovery_set()
    secondary = run_config('secondary_broad_core', broad, BASE_STATS_BROAD)
    print("  summary:", json.dumps(summarize(secondary)))

    out = {'analysis_date': datetime.now(timezone.utc).isoformat(),
           'method': 'measurement-only; exact mm_models.py fit path reproduced; 10 uniform bins; '
                     'Wilson 95% CI per bucket; each model fit twice for jitter-invariance of the label; '
                     'no refit-with-different-settings, no post-hoc calibration',
           'primary_summary': summarize(primary), 'secondary_summary': summarize(secondary),
           'primary_rich_mixed': primary, 'secondary_broad_core': secondary,
           'duration_sec': round(time.time()-t0, 1)}
    with open('/home/ubuntu/data/discovery/mm_calibration_audit.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved data/discovery/mm_calibration_audit.json ({out['duration_sec']}s)")
    return out


if __name__ == '__main__':
    main()
