"""
Pilot C — apply the regularized stat-mixer to FORWARD fixtures and compare to
multi-book fair prices (Bet365, Betfair-exchange, Pinnacle). PROSPECTIVE: most
fixtures are unsettled; this writes a prediction log to be scored as games finish.

Reuses pilotC_stat_mixer training (same pools, PIT features, elastic-net regulator)
by refitting each market on the FULL corpus with the CV-selected (C, l1_ratio) already
found, then predicting the forward fixtures whose teams we have histories for.

Edge is measured against EACH book's devigged fair prob, with Betfair (near-zero vig)
as the primary honest benchmark and cross-book disagreement recorded. No bets settled
here; outcomes filled in later by pilotC_settle.py as fixtures complete.
"""
import sys, json, glob, os, warnings
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
warnings.filterwarnings('ignore')
sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')
from sklearn.linear_model import LogisticRegression
import pilotC_stat_mixer as mix

CH='/home/ubuntu/data/thestatsapi/championship'
OUT='/home/ubuntu/data/discovery/pilotC_forward_predictions.json'
BOOKS=['bet365','betfair-exchange','pinnacle']
MKT_ODDSKEY={'goals':'total_goals','corners':'match_corners','cards':'total_cards','btts':'btts'}


def devig(o,u):
    if not o or not u: return None
    o,u=float(o),float(u)
    if o<=1 or u<=1: return None
    s=1/o+1/u; return (1/o)/s, s-1


def fit_full(ms, hist, market, line, C, l1r):
    names=mix.feat_names(market); X=[];y=[]
    for m in ms:
        o=mix.outcome(m,market,line)
        if o is None: continue
        X.append(mix.match_features(hist,m,market)); y.append(o)
    cov=np.mean([[v is not None for v in r] for r in X],axis=0)
    keep=[i for i in range(len(names)) if cov[i]>=0.6]
    names=[names[i] for i in keep]
    M=np.array([[ (np.nan if r[i] is None else r[i]) for i in keep] for r in X],float)
    med=np.nanmedian(M,0); med=np.where(np.isnan(med),0,med)
    idx=np.where(np.isnan(M)); M[idx]=np.take(med,idx[1])
    mu,sd=M.mean(0),M.std(0); sd[sd==0]=1; Ms=(M-mu)/sd
    clf=LogisticRegression(penalty='elasticnet',solver='saga',C=C,l1_ratio=l1r,max_iter=4000)
    clf.fit(Ms,np.array(y))
    return {'clf':clf,'keep':keep,'names_all':mix.feat_names(market),'med':med,'mu':mu,'sd':sd}


def predict_one(model, hist, m, market):
    raw=mix.match_features(hist,m,market)
    x=np.array([ (np.nan if raw[i] is None else raw[i]) for i in model['keep']],float)
    if np.all(np.isnan(x)): return None
    nanidx=np.where(np.isnan(x))[0]; x[nanidx]=model['med'][nanidx]
    xs=(x-model['mu'])/model['sd']
    return float(np.clip(model['clf'].predict_proba(xs.reshape(1,-1))[0,1],0.01,0.99))


def load_forward_books(mid):
    out={}
    for bk in BOOKS:
        f=f'{CH}/pilotC_odds_{mid}_{bk}.json'
        if not os.path.exists(f): continue
        try: d=json.load(open(f))
        except: continue
        bks=d.get('data',{}).get('bookmakers',[])
        if bks and isinstance(bks[0],dict) and bks[0].get('markets'):
            out[bk]=bks[0]['markets']
    return out


def main():
    ms=mix.load_corpus(); hist=mix.build_histories(ms)
    corpus_teams=set(hist.keys())
    saved=json.load(open('/home/ubuntu/data/discovery/pilotC_stat_mixer.json'))['models']
    hp={(x['market'], x['line']):(x['C'],x['l1_ratio']) for x in saved}
    print('fitting forward models with CV-selected hyperparameters...')
    models={}
    for (market,line),(C,l1r) in hp.items():
        models[(market,line)]=fit_full(ms,hist,market,line,C,l1r)

    fx=json.load(open(f'{CH}/_pilotC_fixture_list.json'))['meta']
    preds=[]
    for mid,info in fx.items():
        home,away=info.get('home'),info.get('away')
        if home not in corpus_teams or away not in corpus_teams: continue
        books=load_forward_books(mid)
        if not books: continue
        m={'home_name':home,'away_name':away,'date_unix':info['ts']}
        for (market,line),model in models.items():
            pm=predict_one(model,hist,m,market)
            if pm is None: continue
            ok=MKT_ODDSKEY[market]
            row={'match_id':mid,'home':home,'away':away,'kickoff_ts':info['ts'],
                 'status':info['status'],'market':market,'line':line,'model_p':round(pm,4),'books':{}}
            for bk,mk in books.items():
                if market=='btts':
                    node=mk.get('btts',{}); o=node.get('yes',{}).get('last_seen'); u=node.get('no',{}).get('last_seen')
                else:
                    node=mk.get(ok,{}).get(str(line),{}); o=node.get('over',{}).get('last_seen'); u=node.get('under',{}).get('last_seen')
                dv=devig(o,u)
                if dv:
                    fair,ovr=dv
                    row['books'][bk]={'fair_p':round(fair,4),'overround':round(ovr,4),
                                      'edge_pp':round((pm-fair)*100,2),
                                      'over_odds':float(o),'under_odds':float(u)}
            if row['books']: preds.append(row)

    # cross-book disagreement summary
    disagree=[]
    for r in preds:
        if 'bet365' in r['books'] and 'betfair-exchange' in r['books']:
            disagree.append(abs(r['books']['bet365']['fair_p']-r['books']['betfair-exchange']['fair_p']))
    out={'generated':datetime.now(timezone.utc).isoformat(),
         'STATUS':'PROSPECTIVE — most fixtures unsettled; score with pilotC_settle.py after kickoff',
         'n_predictions':len(preds),
         'n_mappable_fixtures':len(set(r['match_id'] for r in preds)),
         'betfair_vs_bet365_disagreement_pp':{
             'mean':round(float(np.mean(disagree))*100,2) if disagree else None,
             'max':round(float(np.max(disagree))*100,2) if disagree else None,
             'n':len(disagree)},
         'predictions':preds}
    json.dump(out, open(OUT,'w'), indent=2, default=str)
    print(f"predictions={len(preds)} over {out['n_mappable_fixtures']} fixtures")
    print(f"betfair vs bet365 disagreement: {out['betfair_vs_bet365_disagreement_pp']}")
    # show a few example edges vs Betfair
    ex=[r for r in preds if 'betfair-exchange' in r['books']][:8]
    for r in ex:
        bf=r['books']['betfair-exchange']
        print(f"  {r['market']:7s} {str(r['line']):5s} {r['home'][:14]:14s} v {r['away'][:14]:14s} model={r['model_p']:.2f} betfair_fair={bf['fair_p']:.2f} edge={bf['edge_pp']:+.1f}pp")
    print('saved', OUT)


if __name__=='__main__':
    main()
