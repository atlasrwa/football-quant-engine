from __future__ import annotations
import json
from src.research.v3_pilot.market import _bet365,_ou_pair,devig
from .config import SPEC
S=json.loads(SPEC.read_text())['selection']
def eval_pair(p_over,over,under):
    mo,mu=devig(over,under)
    if p_over>=mo: side,pm,pk,price='OVER',p_over,mo,over
    else: side,pm,pk,price='UNDER',1-p_over,mu,under
    delta=pm-pk; raw=1/price
    return {'side':side,'p_model':float(pm),'p_market':float(pk),'delta':float(delta),'price':float(price),'raw_break_even':float(raw),'qualifies':bool(pm>=S['min_selected_probability'] and delta>=S['min_model_minus_market_novig'] and (not S['must_beat_raw_break_even'] or pm>raw))}
def compare_family(dist,odds,family):
    bk=_bet365(odds)
    if not bk:return []
    market=(bk.get('markets') or {}).get('total_goals' if family=='goals' else 'match_corners') or {}
    lines=[2.5,3.5] if family=='goals' else [8.5,9.5,10.5]
    out=[]
    for line in lines:
        pair=_ou_pair(market.get(str(line)) or {},'last_seen')
        if not pair or str(line) not in (dist.get('probabilities') or {}): continue
        p=float(dist['probabilities'][str(line)]['p_over'])
        out.append({'family':family,'line':line,'p_over':p,**eval_pair(p,*pair)})
    return out
