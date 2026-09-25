"""V1.2.3 strong deterministic baseline extensions.

Preserves every V1.2.2 M0 feature and adds conventional multi-season history controls to BOTH
M0 and M1 so opponent-similarity cannot win merely because it alone reaches into prehistory.
No target labels or model results are used.
"""
from __future__ import annotations
from typing import Any, Dict, List, Mapping, Sequence
import math
import numpy as np

from src.research.target_aware_market_panel import predictive_v122 as B

ROOT=B.ROOT
OUT=B.OUT
CACHE=B.CACHE
RAW_MANIFEST=B.RAW_MANIFEST
FOLDS=B.FOLDS
REGISTRY=B.REGISTRY
TARGETS=B.TARGETS
PANEL_END_UNIX=B.PANEL_END_UNIX

MULTISEASON_WINDOWS=("MS_W20","MS_VENUE_W10","MS_EWMA_H10")
MS_W20_N=20
MS_VENUE_W10_N=10
EWMA_HALF_LIFE_MATCHES=10.0
MIN_MS_OBS=10

fsha=B.fsha
load_prehistory=B.load_prehistory
load_histories=B.load_histories
fixtures_from_folds=B.fixtures_from_folds
class_c_by_family=B.class_c_by_family
memoize_history=B.memoize_history
primary_targets=B.primary_targets
all_targets=B.all_targets
label_for_target=B.label_for_target

def _team(fx:Mapping[str,Any],side:str)->str:
    return fx["home_team_id"] if side=="HOME" else fx["away_team_id"]

def _venue(side:str)->str:
    return "HOME" if side=="HOME" else "AWAY"

def strong_specs(family:str)->List[Dict[str,Any]]:
    specs=[]
    for side in ("HOME","AWAY"):
        for metric in B.POL.FAMILY_CONTEXT[family]:
            for perspective in ("FOR","AGAINST"):
                for window in MULTISEASON_WINDOWS:
                    specs.append({"kind":"MULTISEASON","side":side,"metric":metric,
                                  "perspective":perspective,"period":"FULL_MATCH","window":window})
        for metric in B.POL.HALF_CONTEXT.get(family,[]):
            for period in ("FIRST_HALF","SECOND_HALF"):
                for perspective in ("FOR","AGAINST"):
                    for window in MULTISEASON_WINDOWS:
                        specs.append({"kind":"MULTISEASON","side":side,"metric":metric,
                                      "perspective":perspective,"period":period,"window":window})
    return specs

def strong_name(s:Mapping[str,Any])->str:
    return f"M0S.{s['side']}.{s['metric']}.{s['perspective']}.{s['period']}.{s['window']}"

def _values(h,team,before,metric,perspective,period,venue=None):
    rows=h.prior(team,before,venue=venue)
    return [float(v) for r in rows
            for v in [r.get(metric,perspective,period)] if v is not None]

def strong_value(h,fx:Mapping[str,Any],s:Mapping[str,Any])->float:
    team=_team(fx,s["side"]); venue=_venue(s["side"])
    if s["window"]=="MS_W20":
        vals=_values(h,team,fx["kickoff"],s["metric"],s["perspective"],s["period"])[-MS_W20_N:]
        return np.nan if len(vals)<MIN_MS_OBS else float(np.mean(vals))
    if s["window"]=="MS_VENUE_W10":
        vals=_values(h,team,fx["kickoff"],s["metric"],s["perspective"],s["period"],venue=venue)[-MS_VENUE_W10_N:]
        return np.nan if len(vals)<MIN_MS_OBS else float(np.mean(vals))
    if s["window"]=="MS_EWMA_H10":
        vals=_values(h,team,fx["kickoff"],s["metric"],s["perspective"],s["period"])
        if len(vals)<MIN_MS_OBS: return np.nan
        # newest observation has age 0; older observations decay by a fixed 10-match half-life.
        ages=np.arange(len(vals)-1,-1,-1,dtype=float)
        w=np.power(0.5,ages/EWMA_HALF_LIFE_MATCHES)
        return float(np.average(np.asarray(vals,float),weights=w))
    raise ValueError(f"UNKNOWN_MULTISEASON_WINDOW:{s['window']}")

def build_strong_matrix(h,fixtures:Sequence[Mapping[str,Any]],family:str):
    specs=strong_specs(family)
    names=[strong_name(s) for s in specs]
    x=np.empty((len(fixtures),len(specs)),dtype=np.float64)
    for i,fx in enumerate(fixtures):
        for j,s in enumerate(specs):
            x[i,j]=strong_value(h,fx,s)
    return names,x
