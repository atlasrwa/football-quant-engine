from __future__ import annotations
import json
from src.research.v3_pilot.market import _bet365,_ou_pair,devig
from .config import SPEC
S=json.loads(SPEC.read_text())['selection']

def evaluate(p_over,over_odds,under_odds):
    mo,mu=devig(over_odds,under_odds)
    if p_over>=mo: side,p_model,p_market,price,opp='OVER',p_over,mo,over_odds,under_odds
    else: side,p_model,p_market,price,opp='UNDER',1-p_over,mu,under_odds,over_odds
    delta=p_model-p_market; raw=1/price
    return {'side':side,'p_model_selected':p_model,'p_market_novig_selected':p_market,'model_minus_market_novig':delta,'price_decimal':price,'opposite_price_decimal':opp,'raw_break_even_selected':raw,'two_way_overround':1/over_odds+1/under_odds,'qualifies':p_model>=S['min_selected_probability'] and delta>=S['min_model_minus_market_novig'] and (not S['must_beat_raw_break_even'] or p_model>raw)}

def goals(dist,odds):
    bk=_bet365(odds); out=[]
    if not bk:return out
    tg=(bk.get('markets') or {}).get('total_goals') or {}
    for line in (2.5,3.5):
        pair=_ou_pair(tg.get(str(line)) or {},'last_seen')
        if pair:
            p=float(dist['probabilities'][str(line)]['p_over']); out.append({'market_family':'goals','market':'Bet365_total_goals','line':line,'p_model_over':p,**evaluate(p,*pair)})
    return out

def corners(dist,odds):
    bk=_bet365(odds)
    if not bk:return None
    market=(bk.get('markets') or {}).get('match_corners') or {}; choices=[]
    for key,node in dist['probabilities'].items():
        pair=_ou_pair(market.get(str(key)) or {},'last_seen')
        if pair:
            pm,_=devig(*pair); choices.append((abs(pm-.5),float(key),pair,node))
    if not choices:return None
    _,line,pair,node=sorted(choices,key=lambda x:(x[0],x[1]))[0]; p=float(node['p_over'])
    return {'market_family':'corners','market':'Bet365_total_corners','line':line,'p_model_over':p,'model_parent_probabilities':{'v3':node['p_over_v3'],'pressure':node['p_over_pressure'],'pressure_weight':node['pressure_weight']},**evaluate(p,*pair)}
