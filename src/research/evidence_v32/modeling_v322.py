"""V3.2.2 expanded deterministic modeling core.

All transforms are point-in-time reconstruction rules. No odds enter this module.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, PoissonRegressor

from .modeling import (
    COMPLETION_BUFFER_SECONDS, FEATURE_HORIZON_SECONDS, HALF_LIFE_DAYS,
    MIN_FEATURE_HISTORY, MIN_TEAM_TARGET_HISTORY, SHRINK_MATCHES,
    UnsupportedFeatures, estimate_nb_dispersion, event_outcomes,
    event_probabilities, fit_dc_rho, joint_distribution,
)

STAT_PATHS = {
    "shots":"overview.total_shots", "sot":"overview.shots_on_target",
    "box":"shots.shots_inside_box", "big":"overview.big_chances",
    "blocked":"shots.blocked_shots", "crosses":"passes.accurate_crosses",
    "entries":"passes.final_third_entries", "possession":"overview.ball_possession",
    "saves":"goalkeeping.saves", "clearances":"defending.clearances",
    "corners":"overview.corner_kicks", "fouls":"overview.fouls",
    "tackles":"defending.tackles", "interceptions":"defending.interceptions",
    "duels_won_percentage":"duels.duels_won_percentage",
    "xg":"overview.expected_goals",
    "touches_box":"attack.touches_in_penalty_area",
    "big_missed":"attack.big_chances_missed",
    "dispossessed":"duels.dispossessed",
    "fouled_final_third":"attack.fouled_in_final_third",
    "ball_recoveries":"defending.ball_recoveries",
    "shots_off":"shots.shots_off_target",
    "shots_outside":"shots.shots_outside_box",
    "passes":"overview.passes", "accurate_passes":"overview.accurate_passes",
    "offsides":"attack.offsides",
}
GOALS_PRIMARY=("shots","sot","box","big","blocked","crosses","entries",
               "possession","saves","clearances","corners")
GOALS_DEEP=GOALS_PRIMARY+("touches_box","big_missed","dispossessed",
    "fouled_final_third","ball_recoveries","shots_off","shots_outside",
    "passes","accurate_passes","offsides")
CARDS_PRIMARY=("fouls","tackles","interceptions","possession","duels_won_percentage")
CARDS_DEEP=CARDS_PRIMARY+("dispossessed","fouled_final_third",
                           "ball_recoveries","passes","accurate_passes")
def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out=float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out >= 0 else None

def _period_safe(row: dict, side: str) -> bool:
    target=(row.get("targets") or {}).get(f"corners.{side}") or {}
    return target.get("period_status")=="NO_EXTRA_TIME_RECORDED"

def _metric(row: dict, key: str, side: str) -> float | None:
    if not _period_safe(row, side):
        return None
    path=STAT_PATHS[key]
    bad={(x.get("path"),x.get("side")) for x in row.get("period_checks",[])}
    if (path,side) in bad:
        return None
    return number((row.get("raw_stats") or {}).get(f"{path}.all.{side}"))

def row_metrics(row: dict) -> dict:
    out={"home":{},"away":{}}
    for side in out:
        out[side]["goals"]=number(row["targets"][f"goals.{side}"]["value"])
        out[side]["yellow"]=number(row["targets"][f"bookings.{side}"]["value"])
        for key in STAT_PATHS:
            out[side][key]=_metric(row,key,side)
    return out
def _weighted(entries, key, kind, cutoff):
    vals=[]
    for entry in entries:
        value=entry[kind].get(key)
        if value is None:
            continue
        weight=2**(-(cutoff-entry["ts"])/86400.0/HALF_LIFE_DAYS)
        vals.append((value,weight))
    return sum(v*w for v,w in vals),sum(w for _,w in vals),len(vals)

def _profile(entries, pool, cutoff, keys):
    out={}
    for key in keys:
        for kind in ("own","opp"):
            num,den,n=_weighted(entries,key,kind,cutoff)
            gnum,gden,_=_weighted(pool,key,kind,cutoff)
            prior=gnum/gden if gden else None
            out[f"{kind}_{key}"]=(
                (num+SHRINK_MATCHES*prior)/(den+SHRINK_MATCHES)
                if prior is not None else None
            )
            out[f"{kind}_{key}_n"]=n
    return out

def _support(profile, keys, minimum):
    return all(profile.get(f"{kind}_{key}_n",0)>=minimum
               for key in keys for kind in ("own","opp"))

def _venue(row, side):
    neutral=(row.get("context") or {}).get("is_neutral")
    if neutral is None:
        return None
    if bool(neutral):
        return 0.0
    return 1.0 if side=="home" else -1.0
def _elo_expected(home, away, bonus):
    return 1.0/(1.0+10**(-(home+bonus-away)/400.0))

def _apply_elo(ratings, pending, cutoff):
    while pending and pending[0]["ts"]+COMPLETION_BUFFER_SECONDS<cutoff:
        event=pending.pop(0)
        h=ratings.get(event["home_id"],1500.0)
        a=ratings.get(event["away_id"],1500.0)
        bonus=50.0 if event.get("is_neutral") is False else 0.0
        expected=_elo_expected(h,a,bonus)
        actual=1.0 if event["home_goals"]>event["away_goals"] else (
            0.0 if event["home_goals"]<event["away_goals"] else 0.5)
        delta=20.0*(actual-expected)
        ratings[event["home_id"]]=h+delta
        ratings[event["away_id"]]=a-delta

def _comp_prior(pool, target, cutoff):
    num,den,_=_weighted(pool,target,"own",cutoff)
    return num/den if den else None

def _vector(p,q,target,keys,elo_delta,venue,comp_prior):
    values=[p[f"own_{target}"],p[f"opp_{target}"],
            q[f"own_{target}"],q[f"opp_{target}"],
            elo_delta,venue,comp_prior]
    for key in keys:
        values.extend([p[f"own_{key}"],p[f"opp_{key}"],
                       q[f"own_{key}"],q[f"opp_{key}"]])
    return values
def _similar(entries, opponent_profile, family, target, cutoff):
    dims=((target,"shots","sot","box","entries") if family=="goals"
          else (target,"fouls","tackles","possession"))
    current=[opponent_profile.get(f"opp_{k}") for k in dims]
    if any(v is None for v in current):
        return None,0
    values=[]
    for entry in entries:
        op=entry.get("opponent_profile") or {}
        past=[op.get(f"opp_{k}") for k in dims]
        outcome=entry["own"].get(target)
        if outcome is None or any(v is None for v in past):
            continue
        distance=sum(((a-b)/max(abs(b),1.0))**2 for a,b in zip(past,current))
        weight=math.exp(-0.5*distance)*2**(
            -(cutoff-entry["ts"])/86400.0/HALF_LIFE_DAYS)
        values.append((outcome,weight))
    if len(values)<5:
        return None,len(values)
    base_num,base_den,_=_weighted(entries,target,"own",cutoff)
    if not base_den:
        return None,len(values)
    base=base_num/base_den
    similar=(sum(v*w for v,w in values)+SHRINK_MATCHES*base)/(
        sum(w for _,w in values)+SHRINK_MATCHES)
    return similar-base,len(values)

def build_panel(rows, family):
    if family not in {"goals","cards"}:
        raise ValueError(f"unknown family {family}")
    target="goals" if family=="goals" else "yellow"
    primary=GOALS_PRIMARY if family=="goals" else CARDS_PRIMARY
    deep=GOALS_DEEP if family=="goals" else CARDS_DEEP
    profile_keys=(target,)+deep+(("xg",) if family=="goals" else ())
    history=defaultdict(list); pools=defaultdict(list)
    ratings=defaultdict(dict); pending=defaultdict(list); panel=[]
    for row in sorted(rows,key=lambda r:(r["kickoff_ts"],r["match_id"])):
        ts=float(row["kickoff_ts"]); cutoff=ts-FEATURE_HORIZON_SECONDS
        comp=str(row["competition_id"]); hid=str(row["home_id"]); aid=str(row["away_id"])
        pool=[e for e in pools[comp] if e["ts"]+COMPLETION_BUFFER_SECONDS<cutoff]
        hh=[e for e in history[hid] if e["ts"]+COMPLETION_BUFFER_SECONDS<cutoff]
        ah=[e for e in history[aid] if e["ts"]+COMPLETION_BUFFER_SECONDS<cutoff]
        hp=_profile(hh,pool,cutoff,profile_keys); ap=_profile(ah,pool,cutoff,profile_keys)
        _apply_elo(ratings[comp],pending[comp],cutoff)
        elo=(ratings[comp].get(hid,1500.0)-ratings[comp].get(aid,1500.0))/400.0
        prior=_comp_prior(pool,target,cutoff)
        metrics=row_metrics(row); y=[metrics["home"][target],metrics["away"][target]]
        core=_support(hp,(target,),MIN_TEAM_TARGET_HISTORY) and _support(ap,(target,),MIN_TEAM_TARGET_HISTORY)
        ps=core and _support(hp,primary,MIN_FEATURE_HISTORY) and _support(ap,primary,MIN_FEATURE_HISTORY)
        ds=core and _support(hp,deep,MIN_FEATURE_HISTORY) and _support(ap,deep,MIN_FEATURE_HISTORY)
        xs=family=="goals" and ds and _support(hp,("xg",),MIN_FEATURE_HISTORY) and _support(ap,("xg",),MIN_FEATURE_HISTORY)
        hv=_venue(row,"home"); av=_venue(row,"away")
        home_base=_vector(hp,ap,target,(),elo,hv,prior)
        away_base=_vector(ap,hp,target,(),-elo,av,prior)
        home_primary=_vector(hp,ap,target,primary,elo,hv,prior)
        away_primary=_vector(ap,hp,target,primary,-elo,av,prior)
        home_deep=_vector(hp,ap,target,deep,elo,hv,prior)
        away_deep=_vector(ap,hp,target,deep,-elo,av,prior)
        home_xg=_vector(hp,ap,target,deep+("xg",),elo,hv,prior) if family=="goals" else None
        away_xg=_vector(ap,hp,target,deep+("xg",),-elo,av,prior) if family=="goals" else None
        home_sim,home_sim_n=_similar(hh,ap,family,target,cutoff)
        away_sim,away_sim_n=_similar(ah,hp,family,target,cutoff)
        home_similar=home_deep+[home_sim]
        away_similar=away_deep+[away_sim]
        sim_support=ds and home_sim is not None and away_sim is not None
        panel.append({
            "match_id":row["match_id"],"competition_id":comp,"date":row["kickoff"][:10],
            "kickoff_ts":ts,"cutoff_ts":cutoff,"y":y,
            "eligible_core":core and None not in y,
            "eligible_primary":ps and None not in y,
            "eligible_deep":ds and None not in y,
            "eligible_similar":sim_support and None not in y,
            "eligible_xg":xs and None not in y,
            "home":{"base":home_base,"primary":home_primary,"deep":home_deep,
                    "similar":home_similar,"xg":home_xg},
            "away":{"base":away_base,"primary":away_primary,"deep":away_deep,
                    "similar":away_similar,"xg":away_xg},
            "match_deep":home_deep+away_deep,
            "similar_support":{"home":home_sim_n,"away":away_sim_n},
        })
        for side,other,tid,op_profile in (
            ("home","away",hid,ap),("away","home",aid,hp)):
            e={"match_id":row["match_id"],"ts":ts,"own":metrics[side],
               "opp":metrics[other],"opponent_profile":op_profile}
            history[tid].append(e); pools[comp].append(e)
        gh=metrics["home"]["goals"]; ga=metrics["away"]["goals"]
        if gh is not None and ga is not None:
            pending[comp].append({"ts":ts,"home_id":hid,"away_id":aid,
                "home_goals":gh,"away_goals":ga,
                "is_neutral":(row.get("context") or {}).get("is_neutral")})
    return panel
class LinearCount:
    def __init__(self,x,y):
        x=np.asarray(x,float)
        finite=np.isfinite(x)
        if x.ndim!=2 or not len(x) or np.any(finite.sum(axis=0)==0):
            raise UnsupportedFeatures("invalid/all-missing linear count design")
        self.median=np.array([np.median(c[np.isfinite(c)]) for c in x.T])
        z=self._impute(x); self.mean=z.mean(axis=0); self.std=z.std(axis=0)
        self.std[self.std==0]=1.0
        self.model=PoissonRegressor(alpha=1.0,max_iter=2500,tol=1e-8)
        self.model.fit((z-self.mean)/self.std,np.asarray(y,float))
    def _impute(self,x):
        x=np.asarray(x,float); missing=~np.isfinite(x)
        return np.column_stack((np.where(missing,self.median,x),missing.astype(float)))
    def predict(self,x):
        z=self._impute(x)
        return np.maximum(self.model.predict((z-self.mean)/self.std),1e-8)

class HistGBCount:
    def __init__(self,x,y):
        x=np.asarray(x,float)
        if x.ndim!=2 or not len(x) or np.any(np.isfinite(x).sum(axis=0)==0):
            raise UnsupportedFeatures("invalid/all-missing HistGB count design")
        self.model=HistGradientBoostingRegressor(
            loss="poisson",learning_rate=.05,max_iter=150,max_leaf_nodes=15,
            min_samples_leaf=25,l2_regularization=1.0,random_state=3220)
        self.model.fit(x,np.asarray(y,float))
    def predict(self,x):
        return np.maximum(self.model.predict(np.asarray(x,float)),1e-8)

def side_design(rows,key):
    return [r[s][key] for r in rows for s in ("home","away")]

def count_scales(means,outcomes,ridge=.05):
    means=np.asarray(means,float); outcomes=np.asarray(outcomes,float)
    def objective(theta):
        mu=means*np.exp(theta)[None,:]
        return float(np.mean(np.sum(mu-outcomes*np.log(mu)+
            np.vectorize(math.lgamma)(outcomes+1),axis=1))+ridge*np.sum(theta*theta))
    fit=minimize(objective,np.zeros(2),method="L-BFGS-B",bounds=[(-1.5,1.5)]*2)
    if not fit.success:
        raise UnsupportedFeatures("count calibration failed")
    return np.exp(fit.x)
class DirectLogistic:
    def __init__(self,x,y):
        x=np.asarray(x,float)
        finite=np.isfinite(x)
        if x.ndim!=2 or not len(x) or np.any(finite.sum(axis=0)==0):
            raise UnsupportedFeatures("invalid/all-missing logistic design")
        self.median=np.array([np.median(c[np.isfinite(c)]) for c in x.T])
        z=self._impute(x); self.mean=z.mean(axis=0); self.std=z.std(axis=0)
        self.std[self.std==0]=1.0
        self.model=LogisticRegression(C=1.0,max_iter=2000,solver="lbfgs")
        self.model.fit((z-self.mean)/self.std,np.asarray(y,int))
    def _impute(self,x):
        x=np.asarray(x,float); missing=~np.isfinite(x)
        return np.column_stack((np.where(missing,self.median,x),missing.astype(float)))
    def predict(self,x):
        z=self._impute(x)
        return self.model.predict_proba((z-self.mean)/self.std)[:,1]

class DirectHistGB:
    def __init__(self,x,y):
        x=np.asarray(x,float)
        if x.ndim!=2 or not len(x) or np.any(np.isfinite(x).sum(axis=0)==0):
            raise UnsupportedFeatures("invalid/all-missing HistGB classifier design")
        self.model=HistGradientBoostingClassifier(
            learning_rate=.05,max_iter=150,max_leaf_nodes=15,
            min_samples_leaf=25,l2_regularization=1.0,random_state=3220)
        self.model.fit(x,np.asarray(y,int))
    def predict(self,x):
        return self.model.predict_proba(np.asarray(x,float))[:,1]

def platt_fit(raw_p,y,ridge=.05):
    p=np.clip(np.asarray(raw_p,float),1e-8,1-1e-8); y=np.asarray(y,float)
    z=logit(p)
    def objective(beta):
        q=expit(beta[0]+beta[1]*z)
        nll=np.mean(-(y*np.log(np.clip(q,1e-10,1))+
                      (1-y)*np.log(np.clip(1-q,1e-10,1))))
        return float(nll+ridge*(beta[0]**2+(beta[1]-1)**2))
    fit=minimize(objective,[0.,1.],method="L-BFGS-B",bounds=[(-3,3),(.1,4)])
    if not fit.success:
        raise UnsupportedFeatures("Platt calibration failed")
    return np.asarray(fit.x,float)

def platt_apply(raw_p,beta):
    p=np.clip(np.asarray(raw_p,float),1e-8,1-1e-8)
    return expit(beta[0]+beta[1]*logit(p))
