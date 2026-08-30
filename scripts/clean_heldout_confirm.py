"""
Held-out confirmation of the Stage-1 rich-tier survivor(s).

Survivor: SOT per-side persistence — {home,away} SOT-for x opp SOT-conceded ->
per-side shots-on-target over 3.5, in England Championship (and La Liga 2).

This is the ONLY held-out access in this run. We reserve the NEWEST season as
held-out: fit the feature model on the older seasons, evaluate on the newest.
Confirms the relationship as a PREDICTION (there is no SOT betting market, so this
is not an EV confirmation).
"""
from __future__ import annotations
import sys, json, datetime
import numpy as np
from scipy import stats as sp_stats
from scipy.special import expit

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches
from clean_stage1 import TARGETS, F
from src.discovery.combination_discovery import fit_logistic_l2

OUT = '/home/ubuntu/data/discovery/clean_heldout_confirm.json'


def season_start_year(m):
    d = datetime.datetime.fromtimestamp(m['date_unix'], datetime.timezone.utc)
    return d.year if d.month >= 8 else d.year - 1


def confirm(matches, feats, target_name, heldout_year):
    """Fit on matches with season < heldout_year, evaluate on == heldout_year."""
    tfn = TARGETS[target_name]
    train = [m for m in matches if season_start_year(m) < heldout_year]
    test = [m for m in matches if season_start_year(m) == heldout_year]
    def XY(ms):
        X, y = [], []
        for m in ms:
            row = [m['_f'].get(f) for f in feats]
            o = tfn(m)
            if any(v is None for v in row) or o is None:
                continue
            X.append(row); y.append(o)
        return np.array(X, float), np.array(y, float)
    Xtr, ytr = XY(train); Xte, yte = XY(test)
    if len(Xtr) < 150 or len(Xte) < 80 or len(set(yte.tolist())) < 2:
        return {'status': 'insufficient', 'n_train': len(Xtr), 'n_test': len(Xte)}
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr = (Xtr - mu)/sd; Xte = (Xte - mu)/sd
    beta = fit_logistic_l2(Xtr, ytr, lam=1.0)
    probs = np.clip(expit(np.column_stack([Xte, np.ones(len(Xte))]) @ beta), 0.01, 0.99)
    brier = float(np.mean((probs-yte)**2)); base = float(yte.mean())
    nb = float(np.mean((base-yte)**2)); bss = (1-brier/nb)*100 if nb > 0 else 0.0
    ll_m = float(np.sum(yte*np.log(probs)+(1-yte)*np.log(1-probs)))
    p0 = np.clip(base,0.01,0.99); ll0 = float(np.sum(yte*np.log(p0)+(1-yte)*np.log(1-p0)))
    p = float(sp_stats.chi2.sf(max(2*(ll_m-ll0),0), len(feats)))
    return {'status': 'confirmed' if (bss > 0 and p < 0.05) else 'not_confirmed',
            'heldout_bss_pct': round(bss, 4), 'heldout_p': p,
            'n_train': len(Xtr), 'n_test': len(Xte), 'base_rate': round(base, 4)}


def main():
    ms = load_rich_matches()
    build_features(ms, BASE_STATS_RICH)
    by = {}
    for m in ms:
        by.setdefault(m['_league'], []).append(m)

    survivors = [
        ('England Championship (2nd tier)', 'sot_a_3.5',
         (F('h','shotsOnTarget','for','w5'), F('a','shotsOnTarget','against','w5'))),
        ('England Championship (2nd tier)', 'sot_b_3.5',
         (F('a','shotsOnTarget','for','w5'), F('h','shotsOnTarget','against','w5'))),
        ('La Liga 2', 'sot_b_3.5',
         (F('a','shotsOnTarget','for','w5'), F('h','shotsOnTarget','against','w5'))),
    ]
    HELDOUT_YEAR = 2025   # newest season reserved as held-out
    out = {'note': 'Held-out = newest season (2025) reserved; fit on older seasons. '
                   'ONLY held-out access this run. SOT has no betting market -> prediction confirmation only.',
           'heldout_year': HELDOUT_YEAR, 'access_count': 1, 'results': []}
    print("Held-out confirmation (newest season reserved):")
    for lg, tname, feats in survivors:
        r = confirm(by[lg], feats, tname, HELDOUT_YEAR)
        r.update({'league': lg, 'target': tname, 'features': list(feats)})
        out['results'].append(r)
        print(f"  {lg[:22]:22s} {tname:10s} {r.get('status'):14s} "
              f"heldout_BSS={r.get('heldout_bss_pct')}% p={r.get('heldout_p')} "
              f"n_train={r.get('n_train')} n_test={r.get('n_test')}")
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {OUT}")
    return out


if __name__ == '__main__':
    main()
