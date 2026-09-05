"""
Pilot C — raw-stat mixer with proper regularization ("regulator").

TOP LOGIC (not a blind feature dump — that variance-bomb already failed):
  Each market gets a curated, mechanism-valid stat pool. The features that
  physically drive the line, both teams, attack AND defence sides, point-in-time,
  team-identity keyed. Rolling means over w5/w10 + season-to-date.

REGULATOR:
  Elastic-net logistic (L1+L2). CV selects BOTH C (strength) and l1_ratio
  (sparsity vs grouping). Elastic-net > pure L1 here because football stats are
  correlated (shots/SoT/xG move together); L1 would drop group members arbitrarily,
  elastic-net keeps correlated groups — better selection logic for this data.
  Standardized features; CV on a time-ordered split (no look-ahead in tuning).

Mechanism pools (both teams, for+against where it makes sense):
  goals   : shots, shotsOnTarget, xg, dangerous_attacks, attacks, possession
  corners : corners, attacks, dangerous_attacks, possession, shots, shotsOffTarget
            (wide play / shot volume -> corners), freekicks, throwins
  cards   : fouls, yellow_cards, red-proxy, tackles-proxy(fouls against), + referee rate
  btts    : both teams' attack (xg/shots) and defence (conceded xg/shots)

This module trains per-market models on the historical corpus (point-in-time),
reports OOS skill/calibration, and exposes predict(match_features) for the
forward pilot fixtures. Regulator hyperparameters are logged per market.
"""
import sys, json, glob, warnings
from collections import defaultdict
import numpy as np
warnings.filterwarnings('ignore')
sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

CORPUS='/home/ubuntu/data/discovery/corpus'

# ---- mechanism-valid raw-stat pools per market (team-side stats) ----
POOLS = {
 'goals':   ['shots','shotsOnTarget','xg','dangerous_attacks','attacks','possession'],
 'corners': ['corners','attacks','dangerous_attacks','possession','shots','shotsOffTarget','freekicks','throwins'],
 'cards':   ['fouls','yellow_cards','attacks','possession'],
 'btts':    ['shots','shotsOnTarget','xg','dangerous_attacks'],
}
WINDOWS=[5,10,None]  # None = season-to-date

FIELD={  # stat -> (home_field, away_field)
 'shots':('team_a_shots','team_b_shots'),'shotsOnTarget':('team_a_shotsOnTarget','team_b_shotsOnTarget'),
 'shotsOffTarget':('team_a_shotsOffTarget','team_b_shotsOffTarget'),'xg':('team_a_xg','team_b_xg'),
 'dangerous_attacks':('team_a_dangerous_attacks','team_b_dangerous_attacks'),'attacks':('team_a_attacks','team_b_attacks'),
 'possession':('team_a_possession','team_b_possession'),'corners':('team_a_corners','team_b_corners'),
 'fouls':('team_a_fouls','team_b_fouls'),'yellow_cards':('team_a_yellow_cards','team_b_yellow_cards'),
 'freekicks':('team_a_freekicks','team_b_freekicks'),'throwins':('team_a_throwins','team_b_throwins'),
}


def load_corpus():
    ms=[]
    for f in sorted(glob.glob(f'{CORPUS}/league-matches_*.json')):
        try: ms+=json.load(open(f)).get('data',[])
        except: pass
    # Only completed matches may enter training or rolling inference histories.
    # Scheduled rows contain provider placeholders (including zeroes and -1 values)
    # that would otherwise contaminate both model fitting and current features.
    ms=[m for m in ms if m.get('date_unix') and m.get('home_name') and m.get('away_name')
        and str(m.get('status') or '').casefold() == 'complete']
    ms.sort(key=lambda m:m['date_unix'])
    return ms


def build_histories(ms):
    h=defaultdict(list)
    for m in ms:
        h[m['home_name']].append((m['date_unix'],m,'home'))
        h[m['away_name']].append((m['date_unix'],m,'away'))
    return h


def _v(m,field):
    v=m.get(field)
    try: v=float(v)
    except: return None
    return v if v>=0 else None


def roll(hist, team, stat, side, window, before):
    """team's rolling mean of `stat` (for=own, against=opponent) using prior matches only."""
    hf,af=FIELD[stat]
    rows=[(d,m,r) for d,m,r in hist.get(team,[]) if d<before]
    if window: rows=rows[-window:]
    if window and len(rows)<window: return None
    if not window and len(rows)<3: return None
    vals=[]
    for _,m,r in rows:
        if side=='for':  fld = hf if r=='home' else af
        else:            fld = af if r=='home' else hf
        v=_v(m,fld)
        if v is None: return None
        vals.append(v)
    return float(np.mean(vals)) if vals else None


def feat_names(market):
    names=[]
    for stat in POOLS[market]:
        for who in ('h','a'):
            for side in ('for','against'):
                for w in WINDOWS:
                    names.append(f'{who}_{stat}_{side}_{w or "std"}')
    return names


def match_features(hist, m, market):
    home,away,d=m['home_name'],m['away_name'],m['date_unix']
    row=[]
    for stat in POOLS[market]:
        for who,team in (('h',home),('a',away)):
            for side in ('for','against'):
                for w in WINDOWS:
                    row.append(roll(hist,team,stat,side,w,d))
    return row


def outcome(m, market, line=None):
    hg,ag=m.get('homeGoalCount'),m.get('awayGoalCount')
    if market=='goals':
        t=m.get('totalGoalCount')
        return 1.0 if (t is not None and t>line) else (0.0 if t is not None else None)
    if market=='corners':
        a,b=m.get('team_a_corners'),m.get('team_b_corners')
        if a in (None,-1) or b in (None,-1): return None
        return 1.0 if (a+b)>line else 0.0
    if market=='cards':
        a=m.get('team_a_cards_num'); b=m.get('team_b_cards_num')
        if a in (None,-1) or b in (None,-1):
            ya,yb=m.get('team_a_yellow_cards'),m.get('team_b_yellow_cards')
            if ya in (None,-1) or yb in (None,-1): return None
            a=(ya or 0)+(m.get('team_a_red_cards') or 0); b=(yb or 0)+(m.get('team_b_red_cards') or 0)
        return 1.0 if (a+b)>line else 0.0
    if market=='btts':
        if hg is None or ag is None: return None
        return 1.0 if (hg>=1 and ag>=1) else 0.0
    return None


def train_eval(ms, hist, market, line):
    names=feat_names(market)
    X=[];y=[]
    for m in ms:
        o=outcome(m,market,line)
        if o is None: continue
        row=match_features(hist,m,market)
        X.append(row); y.append(o)
    if len(y)<400: return None
    n=len(y); split=int(n*0.7)
    Xtr_raw=X[:split]; ytr=np.array(y[:split]); Xte_raw=X[split:]; yte=np.array(y[split:])
    # Apply the predeclared unsupervised coverage rule on the outer-training period
    # only. The untouched final 30% never influences the feature set, and this matches
    # the feature-selection rule used by forward refits.
    cov=np.mean([[v is not None for v in r] for r in Xtr_raw],axis=0)
    keep=[i for i in range(len(names)) if cov[i]>=0.6]
    if len(keep)<3: return None
    names=[names[i] for i in keep]
    def mat(raw):
        return np.array([[ (np.nan if r[i] is None else r[i]) for i in keep] for r in raw],float)
    Xtr_raw_matrix=mat(Xtr_raw); Xte_raw_matrix=mat(Xte_raw)
    if len(set(ytr.tolist()))<2 or len(set(yte.tolist()))<2: return None

    # Tune preprocessing and elastic-net hyperparameters together inside expanding,
    # chronological folds. Fitting medians/scales on all outer-training rows before
    # CV would leak later fold distribution information into earlier folds.
    tuning = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('model', LogisticRegression(penalty='elasticnet', solver='saga',
                                     max_iter=4000, random_state=0)),
    ])
    search = GridSearchCV(
        tuning,
        param_grid={'model__C':[0.01,0.03,0.1,0.3,1.0],
                    'model__l1_ratio':[0.2,0.5,0.8]},
        cv=TimeSeriesSplit(n_splits=4), scoring='neg_log_loss', refit=True,
    )
    search.fit(Xtr_raw_matrix, ytr)
    selected_C=float(search.best_params_['model__C'])
    selected_l1=float(search.best_params_['model__l1_ratio'])

    # Refit the selected fixed specification on all outer-training rows and evaluate
    # once on the untouched final 30%. These final preprocessing parameters are also
    # the same form used by forward inference.
    Xtr=Xtr_raw_matrix.copy(); Xte=Xte_raw_matrix.copy()
    med=np.nanmedian(Xtr,0); med=np.where(np.isnan(med),0,med)
    for A in (Xtr,Xte):
        idx=np.where(np.isnan(A)); A[idx]=np.take(med,idx[1])
    mu,sd=Xtr.mean(0),Xtr.std(0); sd[sd==0]=1
    Xtr=(Xtr-mu)/sd; Xte=(Xte-mu)/sd
    clf=LogisticRegression(penalty='elasticnet', solver='saga', C=selected_C,
                           l1_ratio=selected_l1, max_iter=4000, random_state=0)
    clf.fit(Xtr,ytr)
    coefs=clf.coef_[0]; nsel=int(np.sum(np.abs(coefs)>1e-8))
    p=np.clip(clf.predict_proba(Xte)[:,1],0.01,0.99)
    base=yte.mean(); bs_naive=np.mean((base-yte)**2)
    bss=(1-np.mean((p-yte)**2)/bs_naive)*100 if bs_naive>0 else 0
    ece=0
    for b in range(10):
        lo,hi=b/10,(b+1)/10; mk=(p>=lo)&(p<hi if b<9 else p<=hi)
        if mk.sum(): ece+=(mk.sum()/len(p))*abs(p[mk].mean()-yte[mk].mean())
    order=np.argsort(-np.abs(coefs))
    top=[{'feature':names[i],'coef':round(float(coefs[i]),3)} for i in order if abs(coefs[i])>1e-8][:8]
    return {'market':market,'line':line,'n_train':len(ytr),'n_test':len(yte),'base_rate':round(float(base),3),
            'C':selected_C,'l1_ratio':selected_l1,'n_pool':len(names),'n_selected':nsel,
            'bss_pct':round(bss,3),'ece':round(ece,4),'top_features':top}


def main():
    ms=load_corpus(); hist=build_histories(ms)
    print(f'corpus {len(ms)} matches')
    targets=[('goals',1.5),('goals',2.5),('goals',3.5),('corners',8.5),('corners',9.5),
             ('corners',10.5),('cards',3.5),('cards',4.5),('btts',None)]
    out={'method':'elastic-net logistic (CV C + l1_ratio) on mechanism-valid raw-stat pools, PIT team-keyed',
         'validation': {'outer_split': 'first 70% train / final 30% test, chronological',
                        'inner_cv': 'TimeSeriesSplit(n_splits=4), expanding and chronological',
                        'inner_preprocessing': 'median imputation and standardization fitted inside each tuning fold',
                        'feature_coverage_selection': 'predeclared >=60% rule on outer-training period only',
                        'random_state': 0},
         'models':[]}
    for market,line in targets:
        r=train_eval(ms,hist,market,line)
        if r:
            out['models'].append(r)
            tf=', '.join(f"{t['feature']}({t['coef']:+.2f})" for t in r['top_features'][:3])
            print(f"{market:8s} {str(line):5s} BSS={r['bss_pct']:+6.2f}% ECE={r['ece']:.3f} "
                  f"C={r['C']} l1r={r['l1_ratio']} sel={r['n_selected']}/{r['n_pool']} | {tf}")
        else:
            print(f"{market:8s} {str(line):5s} insufficient")
    json.dump(out, open('/home/ubuntu/data/discovery/pilotC_stat_mixer.json','w'), indent=2, default=str)
    print('saved data/discovery/pilotC_stat_mixer.json')


if __name__=='__main__':
    main()
