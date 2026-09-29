from __future__ import annotations
import hashlib, json, math
from collections import defaultdict
from typing import Any
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor
from .freeze import load_freeze

_F=load_freeze(); _G=_F['goals_btts']
HALF_LIFE=float(_G['feature_half_life_days']); SHRINK=float(_G['profile_shrink_k']); ALPHA=float(_G['poisson_alpha'])
MIN_TEAM=int(_G['min_team_history']); MIN_TRAIN=int(_G['min_train_fixtures']); MIN_CAL=int(_G['min_calibration_fixtures']); MAX_CAL=int(_G['max_calibration_fixtures']); CAL_FRAC=float(_G['calibration_fraction'])
CUTOFF_H=float(_G['historical_feature_cutoff_hours_before_fixture']); BUFFER_H=float(_G['historical_stat_publication_buffer_hours'])
FEATURES=('goals','shots','sot','box','big')

class InsufficientRichHistory(RuntimeError): pass

def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def _num(v):
    if isinstance(v,bool): return None
    try: x=float(v)
    except (TypeError,ValueError): return None
    return x if math.isfinite(x) and x>=0 else None

def _cell(payload: dict, group: str, stat: str, side: str):
    try: return _num(payload['data'][group][stat]['all'][side])
    except (KeyError,TypeError): return None

def rich_history_row(match: dict, stats_payload: dict) -> dict | None:
    try:
        sh=_num(match['score']['home']); sa=_num(match['score']['away'])
        if sh is None or sa is None: return None
        metrics={}
        for side in ('home','away'):
            metrics[side]={
                'goals': sh if side=='home' else sa,
                'shots': _cell(stats_payload,'overview','total_shots',side),
                'sot': _cell(stats_payload,'overview','shots_on_target',side),
                'box': _cell(stats_payload,'shots','shots_inside_box',side),
                'big': _cell(stats_payload,'overview','big_chances',side),
            }
        return {'match_id':str(match['match_id']),'ts':float(match['ts']),'home_id':str(match['home_id']),'away_id':str(match['away_id']),
                'is_neutral':match.get('is_neutral'),'metrics':metrics}
    except (KeyError,TypeError,ValueError): return None

def _weighted(entries,key,kind,cutoff):
    pairs=[]
    for e in entries:
        v=e[kind].get(key)
        if v is None: continue
        w=2**(-(cutoff-e['ts'])/86400/HALF_LIFE); pairs.append((v,w))
    return (sum(v*w for v,w in pairs),sum(w for _,w in pairs),len(pairs))

def _profile(entries,pool,cutoff):
    out={}
    for key in FEATURES:
        for kind in ('own','opp'):
            num,den,n=_weighted(entries,key,kind,cutoff); gn,gd,_=_weighted(pool,key,kind,cutoff)
            mean=gn/gd if gd else None
            out[f'{kind}_{key}']=(num+SHRINK*mean)/(den+SHRINK) if mean is not None else None
            out[f'{kind}_{key}_n']=n
    return out

def _side_vector(p,q,venue):
    base=[p['own_goals'],p['opp_goals'],q['own_goals'],q['opp_goals'],venue]
    rich=base
    for key in ('shots','sot','box','big'):
        rich += [p[f'own_{key}'],q[f'opp_{key}']]
    return rich

def build_panel(rows: list[dict], target: dict) -> tuple[list[dict],dict]:
    history=defaultdict(list); pool=[]; panel=[]
    ordered=sorted([r for r in rows if float(r['ts'])<float(target['ts'])],key=lambda r:(r['ts'],r['match_id']))
    def make_features(home_id,away_id,ts,is_neutral):
        cutoff=ts-CUTOFF_H*3600
        eligible_pool=[e for e in pool if e['ts']+BUFFER_H*3600<cutoff]
        hs=[e for e in history[home_id] if e['ts']+BUFFER_H*3600<cutoff]; aws=[e for e in history[away_id] if e['ts']+BUFFER_H*3600<cutoff]
        hp=_profile(hs,eligible_pool,cutoff); ap=_profile(aws,eligible_pool,cutoff)
        if is_neutral is None: hv=av=None
        elif bool(is_neutral): hv=av=0
        else: hv,av=1,-1
        return {'cutoff_ts':cutoff,'eligible':hp['own_goals_n']>=MIN_TEAM and ap['own_goals_n']>=MIN_TEAM,
                'sides':{'home':_side_vector(hp,ap,hv),'away':_side_vector(ap,hp,av)},
                'support':{'home_goal_n':hp['own_goals_n'],'away_goal_n':ap['own_goals_n']}}
    for row in ordered:
        feat=make_features(str(row['home_id']),str(row['away_id']),float(row['ts']),row.get('is_neutral'))
        feat.update({'match_id':row['match_id'],'ts':row['ts'],'y':[row['metrics']['home']['goals'],row['metrics']['away']['goals']]})
        panel.append(feat)
        for side,other,tid in (('home','away',row['home_id']),('away','home',row['away_id'])):
            e={'match_id':row['match_id'],'ts':row['ts'],'own':row['metrics'][side],'opp':row['metrics'][other]}
            history[str(tid)].append(e); pool.append(e)
    tgt=make_features(str(target['home_id']),str(target['away_id']),float(target['ts']),target.get('is_neutral'))
    tgt.update({'match_id':target['match_id'],'ts':target['ts']})
    return panel,tgt

class _Fit:
    def __init__(self,x,y):
        x=np.asarray(x,dtype=float)
        self.median=np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).any() else 0.0 for col in x.T])
        z=self._impute(x); self.mean=z.mean(axis=0); self.std=z.std(axis=0); self.std[self.std==0]=1
        self.model=PoissonRegressor(alpha=ALPHA,max_iter=2000,tol=1e-8).fit((z-self.mean)/self.std,y)
    def _impute(self,x):
        missing=~np.isfinite(x); return np.column_stack((np.where(missing,self.median,x),missing.astype(float)))
    def predict(self,x):
        z=self._impute(np.asarray(x,dtype=float)); return np.maximum(self.model.predict((z-self.mean)/self.std),1e-8)

def _matrix(records): return [r['sides'][s] for r in records for s in ('home','away')]

def _calibrate(means,outcomes):
    logmeans=np.log(np.clip(means,1e-8,None)); ridge=float(_G['joint_calibration']['ridge'])
    def loss(theta):
        z=theta[:2]+theta[2]*logmeans
        return float(np.mean(np.sum(np.exp(z)-outcomes*z+gammaln(outcomes+1),axis=1))+ridge*(sum(theta[:2]**2)+(theta[2]-1)**2))
    lo,hi=_G['joint_calibration']['intercept_bounds']; slo,shi=_G['joint_calibration']['slope_bounds']
    fit=minimize(loss,np.array([0.,0.,1.]),method='L-BFGS-B',bounds=[(lo,hi),(lo,hi),(slo,shi)])
    if not fit.success or not np.isfinite(fit.x).all(): raise InsufficientRichHistory('joint calibration convergence failure')
    return fit.x

def fit_predict(rows: list[dict], target: dict) -> dict:
    panel,tgt=build_panel(rows,target)
    valid=[r for r in panel if r['eligible'] and None not in r['y']]
    if not tgt['eligible']: raise InsufficientRichHistory(f"target team history below {MIN_TEAM}")
    if len(valid)<MIN_TRAIN+MIN_CAL: raise InsufficientRichHistory(f'eligible fixtures {len(valid)} < {MIN_TRAIN+MIN_CAL}')
    cal_n=max(MIN_CAL,int(round(len(valid)*CAL_FRAC))); cal_n=min(MAX_CAL,cal_n,len(valid)-MIN_TRAIN)
    train,cal=valid[:-cal_n],valid[-cal_n:]
    ytrain=np.asarray([r['y'] for r in train],dtype=float).ravel(); ycal=np.asarray([r['y'] for r in cal],dtype=float)
    model=_Fit(_matrix(train),ytrain); cm=model.predict(_matrix(cal)).reshape(-1,2); theta=_calibrate(cm,ycal)
    raw=model.predict(_matrix([tgt])).reshape(1,2)[0]; mu=np.exp(theta[:2]+theta[2]*np.log(np.clip(raw,1e-8,None)))
    home,away=map(float,mu); total=home+away
    probs={str(line):{'p_over':float(poisson.sf(math.floor(line),total))} for line in (2.5,3.5)}
    btts=float((-np.expm1(-home))*(-np.expm1(-away)))
    art={'version':_G['version'],'lambda_home':home,'lambda_away':away,'lambda_total':total,'probabilities':probs,'p_btts_yes':btts,
         'n_train':len(train),'n_calibration':len(cal),'train_ids':[r['match_id'] for r in train],'calibration_ids':[r['match_id'] for r in cal],
         'target_feature_cutoff_ts':tgt['cutoff_ts'],'target_feature_hash':canonical_hash(tgt),'history_hash':canonical_hash(rows),
         'joint_calibration_parameters':[float(x) for x in theta],'model_intercept':float(model.model.intercept_),
         'model_coefficients':[float(x) for x in model.model.coef_],'imputation_median':[float(x) for x in model.median],
         'scaler_mean':[float(x) for x in model.mean],'scaler_std':[float(x) for x in model.std],
         'research_state':_G['research_state'],'dependence':_G['dependence']}
    art['distribution_hash']=canonical_hash(art); return art
