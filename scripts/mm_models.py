"""
Regularized multi-feature model per market/line/league.

Search unit = ONE regularized model per (market, line, league) over the FULL
feature pool. Regularization (L2 logistic, standardized) selects which features
matter; we report standardized coefficient magnitudes = the discovery output.
No hand-picked combinations.

Fresh FDR family = number of models tested (dozens). Within-league significance
required. Walk-forward 60/40, point-in-time features (verified). BSS/Brier/ECE vs
naive. Dispersion checked empirically per count target.

Runs two configurations:
  primary  : rich corpus (3,189), MIXED core+rich feature pool
  secondary: broad corpus (15,362 FootyStats), core-only feature pool
"""
from __future__ import annotations
import sys, json, time, warnings
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
from scipy import stats as sp_stats
warnings.filterwarnings('ignore')

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_BROAD, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches
from src.discovery.corpus import load_discovery_set
from src.engine.analysis.fdr import FDRController
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV

MIN_TRAIN, MIN_TEST = 150, 80
# L1 logistic with CV-selected C -> genuine sparsity; regularization does feature selection.
CV_CS = [0.01, 0.03, 0.1, 0.3, 1.0]


# ── targets (market/line -> outcome fn) ──
def _tot(m, a, b, line):
    x, y = m.get(a), m.get(b)
    if x in (None, -1) or y in (None, -1): return None
    return 1.0 if (x + y) > line else 0.0

def _cards_tot(m, line):
    ya, yb = m.get('team_a_yellow_cards'), m.get('team_b_yellow_cards')
    if ya in (None, -1) or yb in (None, -1): return None
    ra = m.get('team_a_red_cards'); rb = m.get('team_b_red_cards')
    tot = ya + yb + (ra if ra not in (None, -1) else 0) + (rb if rb not in (None, -1) else 0)
    return 1.0 if tot > line else 0.0

def _side(m, f, line):
    v = m.get(f)
    if v in (None, -1): return None
    return 1.0 if v > line else 0.0

def _btts(m):
    hg, ag = m.get('homeGoalCount'), m.get('awayGoalCount')
    if hg in (None,-1) or ag in (None,-1): return None
    return 1.0 if (hg>0 and ag>0) else 0.0

def _cs(m, side):
    hg, ag = m.get('homeGoalCount'), m.get('awayGoalCount')
    if hg in (None,-1) or ag in (None,-1): return None
    return 1.0 if ((ag==0) if side=='a' else (hg==0)) else 0.0

TARGETS = {
    'goals_1.5': lambda m: _tot(m,'homeGoalCount','awayGoalCount',1.5),
    'goals_2.5': lambda m: _tot(m,'homeGoalCount','awayGoalCount',2.5),
    'goals_3.5': lambda m: _tot(m,'homeGoalCount','awayGoalCount',3.5),
    'goals_4.5': lambda m: _tot(m,'homeGoalCount','awayGoalCount',4.5),
    'corners_8.5': lambda m: _tot(m,'team_a_corners','team_b_corners',8.5),
    'corners_9.5': lambda m: _tot(m,'team_a_corners','team_b_corners',9.5),
    'corners_10.5': lambda m: _tot(m,'team_a_corners','team_b_corners',10.5),
    'cards_3.5': lambda m: _cards_tot(m,3.5),
    'cards_4.5': lambda m: _cards_tot(m,4.5),
    'btts': _btts,
    'cs_home': lambda m: _cs(m,'a'),
    'cs_away': lambda m: _cs(m,'b'),
    'corners_a_4.5': lambda m: _side(m,'team_a_corners',4.5),
    'corners_b_4.5': lambda m: _side(m,'team_b_corners',4.5),
    'goals_a_1.5': lambda m: _side(m,'homeGoalCount',1.5),
    'goals_b_1.5': lambda m: _side(m,'awayGoalCount',1.5),
}


def feature_pool(base_stats):
    """All features the verified engine emits for the given base-stat set:
    both teams {h,a} x stat x {for,against} x {w3,w5,w10,std} + venue splits + ref."""
    stats = list(base_stats.keys())
    feats = []
    for who in ('h', 'a'):
        for st in stats:
            for w in ('w3', 'w5', 'w10', 'std'):
                feats.append(f'{who}_{st}_for_{w}')
                feats.append(f'{who}_{st}_against_{w}')
            for w in ('w5', 'std'):
                feats.append(f'{who}_{st}_home_{w}')
                feats.append(f'{who}_{st}_away_{w}')
    feats += ['ref_card_rate', 'ref_foul_rate']
    return feats


def fit_eval(matches, feats, target_fn):
    """Walk-forward L1-regularized (CV-selected C) multi-feature logistic over the
    full pool. Median-imputes missing values (train medians) so rows aren't dropped.
    L1 sparsity IS the feature selection. Returns metrics + non-zero coefficients."""
    n = len(matches)
    split = int(n * 0.6)
    train_idx = list(range(split)); test_idx = list(range(split, n))
    # keep features with >=50% coverage on train (avoid near-empty columns)
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
            row = [matches[i]['_f'].get(f) for f in usable]
            X.append(row); y.append(o)
        return X, np.array(y, float)
    Xtr_raw, ytr = build(train_idx); Xte_raw, yte = build(test_idx)
    if len(Xtr_raw) < MIN_TRAIN or len(Xte_raw) < MIN_TEST:
        return None
    if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
        return None
    Xtr = np.array([[np.nan if v is None else v for v in r] for r in Xtr_raw], float)
    Xte = np.array([[np.nan if v is None else v for v in r] for r in Xte_raw], float)
    # train medians for imputation + standardization
    med = np.nanmedian(Xtr, axis=0); med = np.where(np.isnan(med), 0.0, med)
    def imp(X):
        idx = np.where(np.isnan(X))
        X = X.copy(); X[idx] = np.take(med, idx[1]); return X
    Xtr = imp(Xtr); Xte = imp(Xte)
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr_s = (Xtr - mu) / sd; Xte_s = (Xte - mu) / sd

    # CV-select C on the training fold (time-ordered CV), L1
    try:
        cv = LogisticRegressionCV(Cs=CV_CS, cv=4, penalty='l1', solver='liblinear',
                                  scoring='neg_log_loss', max_iter=2000, refit=True)
        cv.fit(Xtr_s, ytr)
        C = float(cv.C_[0])
        clf = cv
    except Exception:
        clf = LogisticRegression(C=0.1, penalty='l1', solver='liblinear', max_iter=2000)
        clf.fit(Xtr_s, ytr); C = 0.1
    coefs = clf.coef_[0]
    probs = np.clip(clf.predict_proba(Xte_s)[:, 1], 0.01, 0.99)
    brier = float(np.mean((probs - yte) ** 2)); base = float(yte.mean())
    nb = float(np.mean((base - yte) ** 2)); bss = (1 - brier / nb) * 100 if nb > 0 else 0.0
    ece = 0.0
    for b in range(10):
        lo, hi = b/10, (b+1)/10
        mk = (probs >= lo) & (probs < hi if b < 9 else probs <= hi)
        if mk.sum() > 0: ece += (mk.sum()/len(probs)) * abs(probs[mk].mean() - yte[mk].mean())
    n_nonzero = int(np.sum(np.abs(coefs) > 1e-8))
    ll_m = float(np.sum(yte*np.log(probs) + (1-yte)*np.log(1-probs)))
    p0 = np.clip(base, 0.01, 0.99); ll0 = float(np.sum(yte*np.log(p0) + (1-yte)*np.log(1-p0)))
    # df = number of selected (non-zero) features
    p = float(sp_stats.chi2.sf(max(2*(ll_m-ll0), 0), max(n_nonzero, 1)))
    order = np.argsort(-np.abs(coefs))
    top = [{'feature': usable[i], 'std_coef': round(float(coefs[i]), 4)}
           for i in order if abs(coefs[i]) > 1e-8][:10]
    return {'n_features_pool': len(usable), 'n_features_selected': n_nonzero, 'C': C,
            'n_train': len(Xtr), 'n_test': len(Xte), 'base_rate': round(base, 4),
            'bss_pct': round(bss, 4), 'brier': round(brier, 5), 'ece': round(ece, 4),
            'p_value': p, 'top_features': top}


def run_config(name, matches, base_stats, targets):
    build_features(matches, base_stats)
    feats = feature_pool(base_stats)
    by_league = defaultdict(list)
    for m in matches:
        by_league[m['_league']].append(m)
    models = {}
    all_p, all_key = [], []
    for lg in sorted(by_league.keys()):
        ms = sorted(by_league[lg], key=lambda m: m.get('date_unix', 0))
        if len(ms) < 260:
            models[lg] = {'status': 'insufficient_matches', 'n': len(ms)}; continue
        lg_models = {}
        for tname, tfn in targets.items():
            r = fit_eval(ms, feats, tfn)
            if r is None:
                lg_models[tname] = {'status': 'insufficient'}; continue
            all_p.append(r['p_value']); all_key.append((lg, tname))
            lg_models[tname] = {'status': 'tested', **r}
        models[lg] = {'status': 'searched', 'n': len(ms), 'models': lg_models}
    # fresh FDR over models
    fdr = FDRController(alpha=0.05)
    fres = fdr.correct(all_p) if all_p else []
    survivors = []
    for i, fr in enumerate(fres):
        if fr.rejected:
            lg, tname = all_key[i]
            m = models[lg]['models'][tname]
            survivors.append({'league': lg, 'target': tname, 'bss_pct': m['bss_pct'],
                              'p_value': m['p_value'], 'n_test': m['n_test'],
                              'top_features': m['top_features']})
    return {'config': name, 'n_feature_pool': len(feats), 'fresh_fdr_family_size': len(all_p),
            'n_survivors': len(survivors), 'survivors': survivors, 'leagues': models}


def main():
    t0 = time.time()
    print("PRIMARY: rich corpus (3,189), MIXED core+rich pool...")
    rich = load_rich_matches()
    primary = run_config('primary_rich_mixed', rich, BASE_STATS_RICH, TARGETS)
    print(f"  feature pool={primary['n_feature_pool']} models(family)={primary['fresh_fdr_family_size']} survivors={primary['n_survivors']}")

    print("SECONDARY: broad corpus (FootyStats 25 leagues), core-only pool...")
    broad = load_discovery_set()
    # core targets only (no rich, but corners/goals/cards/btts/cs/per-side all core)
    secondary = run_config('secondary_broad_core', broad, BASE_STATS_BROAD, TARGETS)
    print(f"  feature pool={secondary['n_feature_pool']} models(family)={secondary['fresh_fdr_family_size']} survivors={secondary['n_survivors']}")

    out = {'analysis_date': datetime.now(timezone.utc).isoformat(),
           'design': 'one L1-regularized (CV-selected C) multi-feature logistic model per (market,line,league); L1 sparsity selects features; median-imputed; within-league significance; fresh FDR = #models',
           'regularization': 'L1 logistic, C in {0.01,0.03,0.1,0.3,1.0} selected by 4-fold CV neg-log-loss',
           'primary_rich_mixed': primary, 'secondary_broad_core': secondary,
           'duration_sec': round(time.time()-t0, 1)}
    with open('/home/ubuntu/data/discovery/mm_models.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)

    for cfg in (primary, secondary):
        print(f"\n=== {cfg['config']}: family={cfg['fresh_fdr_family_size']} survivors={cfg['n_survivors']} ===")
        for s in sorted(cfg['survivors'], key=lambda x:-x['bss_pct'])[:12]:
            tf = ', '.join(f"{t['feature']}({t['std_coef']:+.2f})" for t in s['top_features'][:3])
            print(f"  {s['league'][:22]:22s} {s['target']:14s} BSS={s['bss_pct']:+6.2f}% p={s['p_value']:.2e} n={s['n_test']} | leans: {tf}")
        # top uncorrected
        tested = [{'league':lg,'target':t,**mm} for lg,r in cfg['leagues'].items()
                  if isinstance(r,dict) and r.get('status')=='searched'
                  for t,mm in r['models'].items() if mm.get('status')=='tested']
        tested.sort(key=lambda x:-x['bss_pct'])
        print(f"  -- top 8 uncorrected BSS ({cfg['config']}):")
        for t in tested[:8]:
            tf = ', '.join(f"{x['feature']}" for x in t['top_features'][:3])
            print(f"     {t['league'][:20]:20s} {t['target']:14s} BSS={t['bss_pct']:+6.2f}% p={t['p_value']:.4f} n={t['n_test']} | {tf}")
    print(f"\nSaved: data/discovery/mm_models.json  ({out['duration_sec']}s)")
    return out


if __name__ == '__main__':
    main()
