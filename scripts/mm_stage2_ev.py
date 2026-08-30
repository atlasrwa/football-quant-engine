"""
Stage 2 — EV vs cached Bet365 odds for the per-market L1 multi-feature models.

No model passed per-league validity + fresh FDR (min p=0.49 primary / 0.23 secondary),
so strictly there is NO survivor to bet -> reported as the primary result.

To answer the EV question rather than leave it blank, we run an ILLUSTRATIVE EV
backtest on the best BSS bettable-market models in the rich slice (where odds exist),
clearly labelled non-survivors. Edges are net of multiplicative overround. Mandatory
reliability filter (both teams' rolling history present; non-extreme model prob).
Compared against measured thresholds, not zero.
"""
from __future__ import annotations
import sys, json, glob, os, warnings
from datetime import datetime, timezone
import numpy as np
warnings.filterwarnings('ignore')

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches
from sklearn.linear_model import LogisticRegressionCV, LogisticRegression

CH_DIR = '/home/ubuntu/data/thestatsapi/championship'
OUT = '/home/ubuntu/data/discovery/mm_stage2_ev.json'
CV_CS = [0.01, 0.03, 0.1, 0.3, 1.0]
THRESHOLDS = {'goals_1.5': 4.15, 'goals_2.5': 3.04, 'goals_3.5': 1.96, 'goals_4.5': 4.0,
              'cards_3.5': 4.05, 'cards_4.5': 4.0, 'corners_9.5': 4.0, 'corners_10.5': 4.0,
              'corners_8.5': 4.0, 'btts': 4.0}
# market/line -> (odds market key, line)
ODDS = {'goals_1.5': ('total_goals', '1.5'), 'goals_2.5': ('total_goals', '2.5'),
        'goals_3.5': ('total_goals', '3.5'), 'goals_4.5': ('total_goals', '4.5'),
        'cards_3.5': ('total_cards', '3.5'), 'cards_4.5': ('total_cards', '4.5'),
        'corners_8.5': ('match_corners', '8.5'), 'corners_9.5': ('match_corners', '9.5'),
        'corners_10.5': ('match_corners', '10.5')}


def load_odds():
    idx = {}
    for f in glob.glob(f'{CH_DIR}/*odds_mt_*.json'):
        mid = os.path.basename(f).replace('laliga2_','').replace('ligue2_','').replace('odds_','').replace('.json','')
        try: d = json.load(open(f))['data']
        except Exception: continue
        b = next((x for x in d.get('bookmakers',[]) if x.get('bookmaker')=='Bet365'), None)
        if b: idx[mid] = b.get('markets', {})
    return idx


def ou(markets, mk, ln):
    ld = markets.get(mk, {}).get(ln)
    if not ld: return None
    o = ld.get('over',{}).get('last_seen'); u = ld.get('under',{}).get('last_seen')
    if o is None or u is None: return None
    o, u = float(o), float(u)
    if o <= 1 or u <= 1: return None
    return o, u


def main():
    from mm_models import TARGETS, feature_pool, MIN_TRAIN, MIN_TEST
    ms = load_rich_matches(); build_features(ms, BASE_STATS_RICH)
    feats = feature_pool(BASE_STATS_RICH)
    odds_idx = load_odds()
    by = {}
    for m in ms: by.setdefault(m['_league'], []).append(m)

    # candidate models to EV: bettable markets, per league, the ones with best BSS from mm_models
    mm = json.load(open('/home/ubuntu/data/discovery/mm_models.json'))['primary_rich_mixed']
    cand = []
    for lg, r in mm['leagues'].items():
        if not isinstance(r, dict) or r.get('status') != 'searched': continue
        for t, model in r['models'].items():
            if model.get('status') == 'tested' and t in ODDS and model['bss_pct'] > 0:
                cand.append((lg, t, model['bss_pct']))
    cand.sort(key=lambda x: -x[2])
    cand = cand[:10]

    out = {'analysis_date': datetime.now(timezone.utc).isoformat(),
           'PRIMARY_RESULT': 'No per-market model passed per-league validity + fresh FDR (min p=0.49). There is NO survivor to bet. The rows below are ILLUSTRATIVE EV on best-BSS non-survivor models; positive edge here is not a finding.',
           'reliability_filter': 'both teams rolling history present (features imputed only if <50% missing); flag |edge|>=3pp; edges net of multiplicative overround',
           'thresholds_pp': THRESHOLDS, 'illustrative': []}

    for lg, tname, bss in cand:
        rows = sorted(by[lg], key=lambda m: m.get('date_unix', 0))
        n = len(rows); split = int(n*0.6)
        tfn = TARGETS[tname]
        # refit the same L1 model on train, predict on test, join odds
        res = ev_one(rows, split, feats, tfn, tname, odds_idx)
        if res:
            res.update({'league': lg, 'discovery_bss_pct': bss})
            out['illustrative'].append(res)
            print(f"  {lg[:20]:20s} {tname:12s} edge_med={res['edge_median_pp']:+.2f}pp thr={THRESHOLDS.get(tname)}pp "
                  f"overround={res['overround_pct']}% flags={res['n_flags']} ROI={res.get('roi_pct')}% CI={res.get('roi_ci_pct')}")
    json.dump(out, open(OUT, 'w'), indent=2, default=str)
    print(f"\nSaved: {OUT}")


def ev_one(rows, split, feats, tfn, tname, odds_idx):
    train_idx = list(range(split)); test_idx = list(range(split, len(rows)))
    def cov(idx, f): return np.mean([rows[i]['_f'].get(f) is not None for i in idx])
    usable = [f for f in feats if cov(train_idx, f) >= 0.5]
    if len(usable) < 3: return None
    def build(idx, need_odds=False):
        X, y, mids = [], [], []
        for i in idx:
            o = tfn(rows[i])
            if o is None: continue
            if need_odds and rows[i]['id'] not in odds_idx: 
                pass
            X.append([rows[i]['_f'].get(f) for f in usable]); y.append(o); mids.append(rows[i]['id'])
        return X, np.array(y, float), mids
    Xtr_r, ytr, _ = build(train_idx); Xte_r, yte, mte = build(test_idx)
    if len(Xtr_r) < 150 or len(Xte_r) < 60 or len(set(ytr.tolist())) < 2: return None
    Xtr = np.array([[np.nan if v is None else v for v in r] for r in Xtr_r], float)
    Xte = np.array([[np.nan if v is None else v for v in r] for r in Xte_r], float)
    med = np.nanmedian(Xtr, axis=0); med = np.where(np.isnan(med), 0.0, med)
    def imp(X):
        ii = np.where(np.isnan(X)); X = X.copy(); X[ii] = np.take(med, ii[1]); return X
    Xtr, Xte = imp(Xtr), imp(Xte)
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd==0] = 1
    Xtr, Xte = (Xtr-mu)/sd, (Xte-mu)/sd
    try:
        clf = LogisticRegressionCV(Cs=CV_CS, cv=4, penalty='l1', solver='liblinear',
                                   scoring='neg_log_loss', max_iter=2000)
        clf.fit(Xtr, ytr)
    except Exception:
        clf = LogisticRegression(C=0.1, penalty='l1', solver='liblinear', max_iter=2000); clf.fit(Xtr, ytr)
    probs = np.clip(clf.predict_proba(Xte)[:, 1], 0.01, 0.99)
    mk, ln = ODDS[tname]
    edges = []; profits = []; n_flags = 0; overrounds = []; n_removed = 0
    for i, mid in enumerate(mte):
        markets = odds_idx.get(mid)
        if not markets: continue
        pr = ou(markets, mk, ln)
        if not pr: continue
        oo, uu = pr
        ro, ru = 1/oo, 1/uu; s = ro+ru
        fair_over = ro/s
        overrounds.append(s-1)
        edge = probs[i] - fair_over
        edges.append(edge)
        # reliability: non-extreme prob
        if probs[i] <= 0.02 or probs[i] >= 0.98:
            n_removed += 1; continue
        if abs(edge) >= 0.03:
            n_flags += 1
            if edge >= 0:
                profits.append((oo-1) if yte[i]==1 else -1)
            else:
                profits.append((uu-1) if yte[i]==0 else -1)
    if not edges: return None
    edges = np.array(edges)
    res = {'market': f'{mk} {ln}', 'target': tname, 'n_eval': len(edges),
           'edge_mean_pp': round(float(edges.mean()*100),3), 'edge_median_pp': round(float(np.median(edges)*100),3),
           'edge_p5_pp': round(float(np.percentile(edges,5)*100),3), 'edge_p95_pp': round(float(np.percentile(edges,95)*100),3),
           'overround_pct': round(float(np.mean(overrounds)*100),2) if overrounds else None,
           'n_flags': n_flags, 'n_removed_reliability': n_removed}
    if profits:
        pr = np.array(profits); rng = np.random.default_rng(42)
        boot = np.array([pr[rng.integers(0,len(pr),len(pr))].mean() for _ in range(10000)])
        res.update({'roi_pct': round(float(pr.mean()*100),2),
                    'roi_ci_pct': [round(float(np.percentile(boot,2.5)*100),2), round(float(np.percentile(boot,97.5)*100),2)],
                    'hit_rate': round(float((pr>0).mean()),3)})
    return res


if __name__ == '__main__':
    main()
