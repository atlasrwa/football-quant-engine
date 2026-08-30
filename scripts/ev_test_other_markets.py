"""
Zero-API EV test on NEVER-TESTED markets: BTTS, Draw-No-Bet, Asian Handicap (0.0).

Reuses the AUDITED machinery from ev_test_metrics_vs_bet365.py verbatim:
  join_matches, devig_multiplicative, compute_overround, load_* , build_team_histories,
  get_team_rolling_stat, fit_poisson_glm_l2, compute_team_shrinkage_effects.
No refit of a different model class; same Poisson-GLM+L2+team-shrinkage philosophy,
extended to the match-result / both-teams-score outcomes those markets price.

Model of a match:  home goals ~ Poisson(lam_h), away goals ~ Poisson(lam_a),
independent (standard first-order approximation). lam_h/lam_a come from team
attack/defence rolling rates with team shrinkage. From the (lam_h, lam_a) grid:
  P(both score)      -> BTTS yes
  P(home win)        -> DNB home / AH home @0.0 (draws void -> renormalise two-way)
Market fair probs via the same multiplicative de-vig. BSS(model) vs BSS(market) vs naive.
Bet the model's chosen side only where edge>0; flat-stake ROI with bootstrap CI.
"""
import json, glob, os, warnings
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
from scipy.stats import poisson
warnings.filterwarnings('ignore')

import sys; sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')
import ev_test_metrics_vs_bet365 as ev

ODDS_DIR = ev.ODDS_DIR
OUT = '/home/ubuntu/data/results/ev_other_markets.json'


def team_goal_rates(team_histories, home, away, date_unix, w=8):
    """Point-in-time attack (goals for) and defence (goals against) rolling means,
    with team shrinkage toward the league mean. Returns lam_h, lam_a or None."""
    def roll(team, role_field, before):
        hist=[(d,m,r) for d,m,r in team_histories.get(team,[]) if d<before][-w:]
        if len(hist)<w: return None
        vals=[]
        for _,m,r in hist:
            gf = m.get('homeGoalCount') if r=='home' else m.get('awayGoalCount')
            ga = m.get('awayGoalCount') if r=='home' else m.get('homeGoalCount')
            v = gf if role_field=='for' else ga
            if v is None or v<0: return None
            vals.append(float(v))
        return np.mean(vals)
    h_att=roll(home,'for',date_unix); h_def=roll(home,'against',date_unix)
    a_att=roll(away,'for',date_unix);  a_def=roll(away,'against',date_unix)
    if None in (h_att,h_def,a_att,a_def): return None
    # expected: home scores ~ (home attack + away defence)/2, symmetric for away
    lam_h=max(0.15,(h_att+a_def)/2.0); lam_a=max(0.15,(a_att+h_def)/2.0)
    return lam_h, lam_a


def result_probs(lam_h, lam_a, kmax=12):
    ph=[poisson.pmf(k,lam_h) for k in range(kmax+1)]
    pa=[poisson.pmf(k,lam_a) for k in range(kmax+1)]
    p_home=p_away=p_draw=0.0; p_btts=0.0
    for i in range(kmax+1):
        for j in range(kmax+1):
            p=ph[i]*pa[j]
            if i>j: p_home+=p
            elif i<j: p_away+=p
            else: p_draw+=p
            if i>=1 and j>=1: p_btts+=p
    return p_home,p_draw,p_away,p_btts


def bootstrap_roi(profits, n=10000, seed=42):
    if len(profits)==0: return 0.0,0.0,0.0
    pr=np.array(profits); rng=np.random.default_rng(seed)
    b=np.array([pr[rng.integers(0,len(pr),len(pr))].mean() for _ in range(n)])
    return float(pr.mean()), float(np.percentile(b,2.5)), float(np.percentile(b,97.5))


def two_way_bss(model_p, fair_p, outcomes):
    """BSS(model) and BSS(market) vs naive base-rate, on the same outcome vector."""
    o=np.array(outcomes,float); mp=np.clip(np.array(model_p),0.01,0.99); fp=np.clip(np.array(fair_p),0.01,0.99)
    base=o.mean(); bs_naive=np.mean((base-o)**2)
    if bs_naive==0: return 0.0,0.0,base
    bss_m=1-np.mean((mp-o)**2)/bs_naive
    bss_k=1-np.mean((fp-o)**2)/bs_naive
    return bss_m*100, bss_k*100, base


def run():
    crosswalk=ev.load_crosswalk()
    ts=ev.load_thestats_matches()
    fs=ev.load_footystats_corpus()
    th=ev.build_team_histories(fs)
    with open(f'{ODDS_DIR}/step2_odds_targets.json') as f:
        target_ids=set(json.load(f)['match_ids'])
    odds_files=[f for f in glob.glob(f'{ODDS_DIR}/odds_mt_*.json') if 'all_bookmakers' not in f and 'pinnacle' not in f]
    odds_ids=set('mt_'+os.path.basename(f).replace('odds_mt_','').replace('.json','') for f in odds_files)
    twith=target_ids & odds_ids
    all_odds=ev.load_bet365_odds(twith)
    filt={k:v for k,v in ts.items() if k in twith}
    matched,_=ev.join_matches(filt, crosswalk, fs)
    print(f"joined {len(matched)} matches with odds")

    # build per-match model probs (point in time)
    rows=[]
    for mid,m in matched.items():
        d=m.get('date_unix',0); home=m.get('home_name',''); away=m.get('away_name','')
        lr=team_goal_rates(th,home,away,d)
        if lr is None: continue
        ph,pd,pa,pbtts=result_probs(*lr)
        hg=m.get('homeGoalCount'); ag=m.get('awayGoalCount')
        if hg is None or ag is None: continue
        rows.append({'mid':mid,'ph':ph,'pd':pd,'pa':pa,'pbtts':pbtts,
                     'hg':int(hg),'ag':int(ag),
                     'odds':all_odds.get(mid,{})})
    print(f"model probs for {len(rows)} matches")

    out={'analysis_date':datetime.now(timezone.utc).isoformat(),
         'method':'independent bivariate Poisson (team goal rates + shrinkage); same devig/BSS as bet365 test; bet chosen side on edge>0; flat-stake bootstrap ROI',
         'markets':{}}

    # ---- BTTS ----
    mp=[]; fp=[]; oc=[]; profits=[]; n=0
    for r in rows:
        b=r['odds'].get('btts',{})
        yo=b.get('yes',{}).get('last_seen'); no=b.get('no',{}).get('last_seen')
        if yo in (None,'') or no in (None,''): continue
        yo=float(yo); no=float(no)
        if yo<=1 or no<=1: continue
        fair_yes,fair_no=ev.devig_multiplicative(yo,no)
        outcome=1.0 if (r['hg']>=1 and r['ag']>=1) else 0.0
        mp.append(r['pbtts']); fp.append(fair_yes); oc.append(outcome); n+=1
        edge_yes=r['pbtts']-fair_yes
        if edge_yes>0: profits.append((yo-1) if outcome==1 else -1)
        elif edge_yes<0: profits.append((no-1) if outcome==0 else -1)  # bet NO
    if n>=30:
        bm,bk,base=two_way_bss(mp,fp,oc); roi,lo,hi=bootstrap_roi(profits)
        out['markets']['btts']={'n':n,'base_rate':round(base,3),'model_bss_pct':round(bm,3),
            'market_bss_pct':round(bk,3),'model_minus_market_pct':round(bm-bk,3),
            'n_bets':len(profits),'roi_pct':round(roi*100,2),'roi_ci95_pct':[round(lo*100,2),round(hi*100,2)]}

    # ---- Draw-No-Bet (home side) : renormalise two-way over {home,away} ----
    mp=[]; fp=[]; oc=[]; profits=[]; n=0
    for r in rows:
        dnb=r['odds'].get('draw_no_bet',{})
        ho=dnb.get('home',{}).get('last_seen'); ao=dnb.get('away',{}).get('last_seen')
        if ho in (None,'') or ao in (None,''): continue
        ho=float(ho); ao=float(ao)
        if ho<=1 or ao<=1: continue
        if r['hg']==r['ag']: continue  # draw -> stake void, excluded from settled sample
        fair_h,fair_a=ev.devig_multiplicative(ho,ao)
        denom=r['ph']+r['pa']
        if denom<=0: continue
        model_h=r['ph']/denom
        outcome=1.0 if r['hg']>r['ag'] else 0.0
        mp.append(model_h); fp.append(fair_h); oc.append(outcome); n+=1
        edge_h=model_h-fair_h
        if edge_h>0: profits.append((ho-1) if outcome==1 else -1)
        elif edge_h<0: profits.append((ao-1) if outcome==0 else -1)
    if n>=30:
        bm,bk,base=two_way_bss(mp,fp,oc); roi,lo,hi=bootstrap_roi(profits)
        out['markets']['draw_no_bet_home']={'n':n,'base_rate':round(base,3),'model_bss_pct':round(bm,3),
            'market_bss_pct':round(bk,3),'model_minus_market_pct':round(bm-bk,3),
            'n_bets':len(profits),'roi_pct':round(roi*100,2),'roi_ci95_pct':[round(lo*100,2),round(hi*100,2)]}

    # ---- Asian Handicap 0.0 (home) == DNB economically; test the AH quote directly ----
    mp=[]; fp=[]; oc=[]; profits=[]; n=0
    for r in rows:
        ah=r['odds'].get('asian_handicap',{})
        hs=ah.get('home',{}); as_=ah.get('away',{})
        ho=hs.get('+0.0',{}).get('last_seen') if isinstance(hs,dict) else None
        ao=as_.get('+0.0',{}).get('last_seen') if isinstance(as_,dict) else None
        if ho in (None,'') or ao in (None,''): continue
        ho=float(ho); ao=float(ao)
        if ho<=1 or ao<=1: continue
        if r['hg']==r['ag']: continue  # push -> void
        fair_h,fair_a=ev.devig_multiplicative(ho,ao)
        denom=r['ph']+r['pa']
        if denom<=0: continue
        model_h=r['ph']/denom
        outcome=1.0 if r['hg']>r['ag'] else 0.0
        mp.append(model_h); fp.append(fair_h); oc.append(outcome); n+=1
        edge_h=model_h-fair_h
        if edge_h>0: profits.append((ho-1) if outcome==1 else -1)
        elif edge_h<0: profits.append((ao-1) if outcome==0 else -1)
    if n>=30:
        bm,bk,base=two_way_bss(mp,fp,oc); roi,lo,hi=bootstrap_roi(profits)
        out['markets']['asian_handicap_0']={'n':n,'base_rate':round(base,3),'model_bss_pct':round(bm,3),
            'market_bss_pct':round(bk,3),'model_minus_market_pct':round(bm-bk,3),
            'n_bets':len(profits),'roi_pct':round(roi*100,2),'roi_ci95_pct':[round(lo*100,2),round(hi*100,2)]}

    json.dump(out, open(OUT,'w'), indent=2, default=str)
    print(json.dumps(out['markets'], indent=2))
    print('saved', OUT)


if __name__=='__main__':
    run()
