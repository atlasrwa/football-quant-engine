"""
Pilot C — PER-LEAGUE runner.

Motivation
----------
The existing Pilot C stat-mixer (scripts/pilotC_stat_mixer.py) pools ALL leagues
into one training matrix (n_train ~= 10.7k) and reports ONE BSS/ECE per market.
The only league-*specific* evidence in the repo covers ~4-6 leagues
(Championship / La Liga 2 / Ligue 2 + family_transfer EPL/LaLiga/Ligue1).

We cover 25 leagues with a 2-season corpus (data/discovery/corpus, 15,362
completed matches). This runner evaluates the SAME mechanism-valid raw-stat
methodology INDEPENDENTLY for every league x market so each league gets its own
out-of-sample-in-time BSS/ECE. It is a diagnostic replication of the pooled
pilot—not a pooled-versus-hierarchical comparison. The aligned pooled,
independent, and empirical-Bayes comparison is implemented separately by
``scripts/league_count_evaluation.py``.

Methodology is IDENTICAL to pilotC_stat_mixer.train_eval:
  - PIT team-keyed rolling means over w5/w10/season, both teams, for+against
  - elastic-net logistic, GridSearchCV over C x l1_ratio with TimeSeriesSplit(4)
  - chronological 70/30 outer split; >=60% coverage rule on training rows only
  - median-impute + standardize fit on training only
Difference: rolling HISTORIES are league-internal (a team's form within the
league corpus), and everything is grouped by league.

Nothing in src/ or the existing pilot artifacts is modified. Output is written to
data/results/pilotC_per_league.json.
"""
import sys, json, glob, re, warnings
from collections import defaultdict
import numpy as np

warnings.filterwarnings('ignore')
sys.path.insert(0, '/home/ubuntu')
sys.path.insert(0, '/home/ubuntu/scripts')

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Reuse the EXACT proven feature/outcome construction from the pooled pilot.
from pilotC_stat_mixer import (
    POOLS, WINDOWS, FIELD, build_histories, match_features, outcome, feat_names,
)

CORPUS = '/home/ubuntu/data/discovery/corpus'
MANIFEST = f'{CORPUS}/manifest.json'
OUT = '/home/ubuntu/data/results/pilotC_per_league.json'

TARGETS = [('goals', 1.5), ('goals', 2.5), ('goals', 3.5),
           ('corners', 8.5), ('corners', 9.5), ('corners', 10.5),
           ('cards', 3.5), ('cards', 4.5), ('btts', None)]

MIN_TRAIN_ROWS = 300   # per-league corpora are smaller than the pooled one
RANDOM_STATE = 0


def load_corpus_by_league():
    """Load completed matches, tagged with their league via season_id in filename."""
    man = json.load(open(MANIFEST))
    sid2league = {}
    for lg in man['leagues']:
        for s in lg['seasons']:
            sid2league[int(s['season_id'])] = lg['league']

    by_league = defaultdict(list)
    for f in sorted(glob.glob(f'{CORPUS}/league-matches_*.json')):
        mo = re.search(r'season_id:_(\d+)', f)
        if not mo:
            continue
        lg = sid2league.get(int(mo.group(1)))
        if lg is None:
            continue
        try:
            data = json.load(open(f)).get('data', [])
        except Exception:
            continue
        for m in data:
            if (m.get('date_unix') and m.get('home_name') and m.get('away_name')
                    and str(m.get('status') or '').casefold() == 'complete'):
                by_league[lg].append(m)
    for lg in by_league:
        by_league[lg].sort(key=lambda m: m['date_unix'])
    return by_league


def _design(ms, hist, market, line):
    """Return (X_rows_of_lists, y, names) for a market on a match list + history."""
    names = feat_names(market)
    X, y = [], []
    for m in ms:
        o = outcome(m, market, line)
        if o is None:
            continue
        X.append(match_features(hist, m, market))
        y.append(o)
    return X, np.array(y, float), names


def _fit_eval(Xtr_raw, ytr, Xte_raw, yte, names):
    """Identical pipeline to pilotC_stat_mixer.train_eval, minus corpus loading."""
    if len(ytr) < MIN_TRAIN_ROWS or len(yte) < 60:
        return None, 'insufficient_rows'
    # coverage rule on training rows only
    cov = np.mean([[v is not None for v in r] for r in Xtr_raw], axis=0)
    keep = [i for i in range(len(names)) if cov[i] >= 0.6]
    if len(keep) < 3:
        return None, 'insufficient_feature_coverage'
    kept_names = [names[i] for i in keep]

    def mat(raw):
        return np.array([[(np.nan if r[i] is None else r[i]) for i in keep] for r in raw], float)

    Xtr_m, Xte_m = mat(Xtr_raw), mat(Xte_raw)
    if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
        return None, 'degenerate_labels'

    tuning = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(penalty='elasticnet', solver='saga',
                                     max_iter=4000, random_state=RANDOM_STATE)),
    ])
    try:
        search = GridSearchCV(
            tuning,
            param_grid={'model__C': [0.01, 0.03, 0.1, 0.3, 1.0],
                        'model__l1_ratio': [0.2, 0.5, 0.8]},
            cv=TimeSeriesSplit(n_splits=4), scoring='neg_log_loss', refit=True)
        search.fit(Xtr_m, ytr)
    except Exception as e:
        return None, f'cv_failed:{type(e).__name__}'
    C = float(search.best_params_['model__C'])
    l1 = float(search.best_params_['model__l1_ratio'])

    # refit selected spec on all training rows, evaluate once on held-out 30%
    Xtr, Xte = Xtr_m.copy(), Xte_m.copy()
    med = np.nanmedian(Xtr, 0)
    med = np.where(np.isnan(med), 0, med)
    for A in (Xtr, Xte):
        idx = np.where(np.isnan(A))
        A[idx] = np.take(med, idx[1])
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1
    Xtr, Xte = (Xtr - mu) / sd, (Xte - mu) / sd
    clf = LogisticRegression(penalty='elasticnet', solver='saga', C=C,
                             l1_ratio=l1, max_iter=4000, random_state=RANDOM_STATE)
    clf.fit(Xtr, ytr)
    coefs = clf.coef_[0]
    nsel = int(np.sum(np.abs(coefs) > 1e-8))
    p = np.clip(clf.predict_proba(Xte)[:, 1], 0.01, 0.99)
    base = yte.mean()
    bs_naive = np.mean((base - yte) ** 2)
    bss = (1 - np.mean((p - yte) ** 2) / bs_naive) * 100 if bs_naive > 0 else 0.0
    ece = 0.0
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        mk = (p >= lo) & (p < hi if b < 9 else p <= hi)
        if mk.sum():
            ece += (mk.sum() / len(p)) * abs(p[mk].mean() - yte[mk].mean())
    order = np.argsort(-np.abs(coefs))
    top = [{'feature': kept_names[i], 'coef': round(float(coefs[i]), 3)}
           for i in order if abs(coefs[i]) > 1e-8][:5]
    return {
        'n_train': int(len(ytr)), 'n_test': int(len(yte)),
        'base_rate': round(float(base), 3), 'C': C, 'l1_ratio': l1,
        'n_pool': len(kept_names), 'n_selected': nsel,
        'bss_pct': round(bss, 3), 'ece': round(ece, 4), 'top_features': top,
        'clf': clf, 'keep': keep, 'med': med, 'mu': mu, 'sd': sd,
    }, None


def _bss_ece(p, y):
    p = np.clip(p, 0.01, 0.99)
    base = y.mean()
    bs_naive = np.mean((base - y) ** 2)
    bss = (1 - np.mean((p - y) ** 2) / bs_naive) * 100 if bs_naive > 0 else 0.0
    ece = 0.0
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        mk = (p >= lo) & (p < hi if b < 9 else p <= hi)
        if mk.sum():
            ece += (mk.sum() / len(p)) * abs(p[mk].mean() - y[mk].mean())
    return round(bss, 3), round(ece, 4)


def main():
    by_league = load_corpus_by_league()
    leagues = sorted(by_league, key=lambda k: -len(by_league[k]))
    print(f'loaded {len(leagues)} leagues, '
          f'{sum(len(v) for v in by_league.values())} completed matches\n')

    # Pre-build league-internal histories once.
    hist_by_league = {lg: build_histories(by_league[lg]) for lg in leagues}

    out = {
        'method': 'per-league elastic-net logistic (CV C + l1_ratio) on '
                  'mechanism-valid raw-stat pools, PIT team-keyed, league-internal histories',
        'validation': {
            'scope': 'each league evaluated independently; rolling histories league-internal',
            'outer_split': 'first 70% train / final 30% test, chronological, per league',
            'inner_cv': 'TimeSeriesSplit(n_splits=4)',
            'feature_coverage_selection': '>=60% on outer-training rows only',
            'min_train_rows': MIN_TRAIN_ROWS, 'random_state': RANDOM_STATE,
        },
        'targets': [{'market': m, 'line': l} for m, l in TARGETS],
        'n_leagues': len(leagues),
        'leagues': {},
    }

    for lg in leagues:
        ms = by_league[lg]
        hist = hist_by_league[lg]
        lg_res = {'n_matches': len(ms), 'markets': []}
        print(f'=== {lg}  (n={len(ms)}) ===')
        for market, line in TARGETS:
            X, y, names = _design(ms, hist, market, line)
            if len(y) == 0:
                lg_res['markets'].append({'market': market, 'line': line,
                                          'status': 'no_labeled_rows'})
                print(f'  {market:8s} {str(line):5s}  no labeled rows')
                continue
            n = len(y)
            split = int(n * 0.7)
            r, why = _fit_eval(X[:split], y[:split], X[split:], y[split:], names)
            if r is None:
                lg_res['markets'].append({'market': market, 'line': line,
                                          'status': why, 'n_labeled': n})
                print(f'  {market:8s} {str(line):5s}  skipped ({why}, n={n})')
                continue
            entry = {'market': market, 'line': line, 'status': 'ok',
                     'n_train': r['n_train'], 'n_test': r['n_test'],
                     'base_rate': r['base_rate'], 'bss_pct': r['bss_pct'],
                     'ece': r['ece'], 'C': r['C'], 'l1_ratio': r['l1_ratio'],
                     'n_selected': r['n_selected'], 'n_pool': r['n_pool'],
                     'top_features': r['top_features']}
            lg_res['markets'].append(entry)
            tf = ', '.join(f"{t['feature']}({t['coef']:+.2f})" for t in r['top_features'][:2])
            print(f"  {market:8s} {str(line):5s}  BSS={r['bss_pct']:+6.2f}% "
                  f"ECE={r['ece']:.3f} n={r['n_train']}+{r['n_test']} sel={r['n_selected']} | {tf}")
        out['leagues'][lg] = lg_res
        print()

    json.dump(out, open(OUT, 'w'), indent=2, default=str)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
