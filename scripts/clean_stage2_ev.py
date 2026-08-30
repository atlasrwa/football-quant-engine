"""
Stage 2 — EV vs market.

The Stage-1 FDR survivors are all shots-on-target per-side, for which NO betting
market is cached (rich-slice Bet365 = match_odds/btts/total_goals/match_corners/
total_cards/DNB/double_chance/AH/first_half/first_team_to_score only). Therefore
EV on the survivors is UNTESTABLE — reported as a gap, not substituted.

To not leave the EV question blank, this runs an ILLUSTRATIVE EV backtest on the
best BETTABLE-market gate-passed candidates (goals/corners/cards) from Stage 1,
in the rich slice where both features and odds exist, with the mandatory
reliability filter. These are explicitly NOT Stage-1 survivors (none of these
markets produced an FDR survivor), so any positive edge here is a lead, not a
finding.
"""
from __future__ import annotations
import sys, json, glob, os
from datetime import datetime, timezone
import numpy as np
from scipy.special import expit

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches, _mid_of
from clean_stage1 import TARGETS, F
from src.discovery.combination_discovery import fit_logistic_l2

CH_DIR = '/home/ubuntu/data/thestatsapi/championship'
OUT = '/home/ubuntu/data/discovery/clean_stage2_ev.json'
MIN_TEAM_MATCHES = 5  # reliability: both teams need history in-window (w5 satisfies)


def load_odds_index():
    idx = {}
    for f in glob.glob(f'{CH_DIR}/*odds_mt_*.json'):
        mid = os.path.basename(f).replace('laliga2_','').replace('ligue2_','').replace('odds_','').replace('.json','')
        try:
            d = json.load(open(f))['data']
        except Exception:
            continue
        b = next((x for x in d.get('bookmakers',[]) if x.get('bookmaker')=='Bet365'), None)
        if b:
            idx[mid] = b.get('markets',{})
    return idx


def ou(markets, market, line):
    ld = markets.get(market,{}).get(str(line))
    if not ld: return None
    o = ld.get('over',{}).get('last_seen'); u = ld.get('under',{}).get('last_seen')
    if o is None or u is None: return None
    o,u=float(o),float(u)
    if o<=1 or u<=1: return None
    return o,u


def devig(o,u):
    ro,ru=1/o,1/u; s=ro+ru
    return ro/s, ru/s


def backtest(matches, odds_idx, feats, target_name, market, line, tot_fields):
    """Walk-forward: fit on first 60%, bet on last 40% where model edge>0 AND reliable."""
    tfn = TARGETS[target_name]
    rows = [m for m in matches]
    n = len(rows); split = int(n*0.6)
    def XY(ms):
        X,y,mm=[],[],[]
        for m in ms:
            r=[m['_f'].get(f) for f in feats]; o=tfn(m)
            if any(v is None for v in r) or o is None: continue
            X.append(r); y.append(o); mm.append(m)
        return np.array(X,float), np.array(y,float), mm
    Xtr,ytr,_=XY(rows[:split]); Xte,yte,mte=XY(rows[split:])
    if len(Xtr)<150 or len(Xte)<80 or len(set(ytr.tolist()))<2: return None
    mu,sd=Xtr.mean(0),Xtr.std(0); sd[sd==0]=1
    Xtr=(Xtr-mu)/sd; Xte=(Xte-mu)/sd
    beta=fit_logistic_l2(Xtr,ytr,lam=1.0)
    probs=np.clip(expit(np.column_stack([Xte,np.ones(len(Xte))])@beta),0.01,0.99)
    edges=[]; profits=[]; n_flags=0; n_removed=0; overrounds=[]
    for i,m in enumerate(mte):
        o=odds_idx.get(m['id'])
        if not o: continue
        pr=ou(o, market, line)
        if not pr: continue
        over_odds,under_odds=pr
        fair_over,fair_under=devig(over_odds,under_odds)
        overrounds.append(1/over_odds+1/under_odds-1)
        p_over=probs[i]
        edge=p_over-fair_over
        edges.append(edge)
        # reliability filter: both teams have >=MIN_TEAM_MATCHES history (w5 feature present already ensures 5)
        reliable = all(m['_f'].get(f) is not None for f in feats)
        if not reliable:
            n_removed+=1; continue
        if abs(edge)>=0.03:  # meaningful edge threshold 3pp
            n_flags+=1
            if edge>=0:  # back over
                win = yte[i]==1
                profits.append((over_odds-1) if win else -1)
            else:
                win = yte[i]==0
                profits.append((under_odds-1) if win else -1)
    if not edges: return None
    edges=np.array(edges)
    res={'market':f'{market} {line}','target':target_name,'n_eval':len(edges),
         'edge_mean_pp':round(float(edges.mean()*100),3),'edge_median_pp':round(float(np.median(edges)*100),3),
         'edge_p5_pp':round(float(np.percentile(edges,5)*100),3),'edge_p95_pp':round(float(np.percentile(edges,95)*100),3),
         'overround_mean_pct':round(float(np.mean(overrounds)*100),2) if overrounds else None,
         'n_flags':n_flags,'n_removed_by_reliability':n_removed}
    if profits:
        pr=np.array(profits); rng=np.random.default_rng(42)
        boot=np.array([pr[rng.integers(0,len(pr),len(pr))].mean() for _ in range(10000)])
        res.update({'flat_roi_pct':round(float(pr.mean()*100),2),
                    'roi_ci95_pct':[round(float(np.percentile(boot,2.5)*100),2),round(float(np.percentile(boot,97.5)*100),2)],
                    'hit_rate':round(float((pr>0).mean()),3)})
    return res


def main():
    ms=load_rich_matches(); build_features(ms, BASE_STATS_RICH)
    by={}
    for m in ms: by.setdefault(m['_league'],[]).append(m)
    odds_idx=load_odds_index()
    print('odds indexed:', len(odds_idx))

    # Illustrative bettable-market candidates (NOT Stage-1 survivors)
    jobs=[
        ('England Championship (2nd tier)', 'goals_tot_2.5', (F('h','xg','for','w5'),F('a','xg','for','w5')), 'total_goals', 2.5),
        ('England Championship (2nd tier)', 'corners_tot_9.5', (F('h','corners','for','w5'),F('a','corners','for','w5')), 'match_corners', 9.5),
        ('England Championship (2nd tier)', 'corners_tot_10.5', (F('h','corners','for','w5'),F('a','corners','for','w5')), 'match_corners', 10.5),
        ('England Championship (2nd tier)', 'cards_tot_3.5', (F('h','yellow_cards','for','w5'),F('a','yellow_cards','for','w5')), 'total_cards', 3.5),
        ('La Liga 2', 'goals_tot_2.5', (F('h','xg','for','w5'),F('a','xg','for','w5')), 'total_goals', 2.5),
    ]
    out={'analysis_date':datetime.now(timezone.utc).isoformat(),
         'CRITICAL_NOTE':'Stage-1 FDR survivors are shots-on-target per-side, which have NO cached betting market -> EV on survivors is UNTESTABLE (reported as a gap, not substituted). The rows below are ILLUSTRATIVE EV on bettable-market candidates that did NOT survive Stage 1 FDR; positive edge here is a lead, not a finding.',
         'reliability_filter':'both teams w5 history present; flag threshold |edge|>=3pp',
         'survivor_markets_available':False,
         'illustrative':[]}
    for lg,tname,feats,market,line in jobs:
        r=backtest(by[lg],odds_idx,feats,tname,market,line,None)
        if r: r['league']=lg
        out['illustrative'].append(r)
        if r:
            print(f"  {lg[:20]:20s} {r['market']:16s} edge_med={r['edge_median_pp']:+.2f}pp overround={r['overround_mean_pct']}% "
                  f"flags={r['n_flags']} ROI={r.get('flat_roi_pct')}% CI={r.get('roi_ci95_pct')}")
    with open(OUT,'w') as f: json.dump(out,f,indent=2,default=str)
    print(f"\nSaved: {OUT}")


if __name__=='__main__':
    main()
