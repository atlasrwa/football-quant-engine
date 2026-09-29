from __future__ import annotations
import math
from typing import Any
from .freeze import load_freeze
_F=load_freeze(); _SEL=_F['selection']

def _decimal(v: Any):
    try: x=float(v)
    except (TypeError,ValueError): return None
    return x if x>1 and math.isfinite(x) else None

def devig(a: float,b: float):
    x,y=1/a,1/b; s=x+y; return x/s,y/s

def _bet365(payload):
    for bk in ((payload or {}).get('data') or {}).get('bookmakers',[]) or []:
        if str(bk.get('bookmaker') or '').strip().lower().startswith('bet365'): return bk
    return None

def _evaluate(p_selected,selected_odds,opposite_odds,side):
    pm,_=devig(selected_odds,opposite_odds); delta=p_selected-pm; breakeven=1/selected_odds
    qualifies=(p_selected>=float(_SEL['min_selected_probability']) and delta>=float(_SEL['min_model_minus_market_novig']) and
               (not _SEL['must_beat_vig_loaded_break_even'] or p_selected>breakeven))
    return {'side':side,'p_model_selected':p_selected,'p_market_novig_selected':pm,'model_minus_market_novig':delta,
            'price_decimal':selected_odds,'opposite_price_decimal':opposite_odds,'raw_break_even_selected':breakeven,
            'two_way_overround':1/selected_odds+1/opposite_odds,'qualifies':bool(qualifies)}

def goal_comparisons(dist: dict, odds_payload: dict):
    bk=_bet365(odds_payload)
    if not bk: return []
    tg=(bk.get('markets') or {}).get('total_goals') or {}; out=[]
    for line in (2.5,3.5):
        node=tg.get(str(line)) or {}; over=_decimal((node.get('over') or {}).get('last_seen')); under=_decimal((node.get('under') or {}).get('last_seen'))
        if over is None or under is None: continue
        p_over=float(dist['probabilities'][str(line)]['p_over']); mo,mu=devig(over,under)
        if p_over>=mo: cmp=_evaluate(p_over,over,under,'OVER')
        else: cmp=_evaluate(1-p_over,under,over,'UNDER')
        opening=None; oo=_decimal((node.get('over') or {}).get('opening')); ou=_decimal((node.get('under') or {}).get('opening'))
        if oo and ou:
            x,y=devig(oo,ou); opening={'over_odds':oo,'under_odds':ou,'p_novig_selected':x if cmp['side']=='OVER' else y}
        out.append({'market_family':'goals','market':'Bet365_total_goals','line':line,'p_model_over':p_over,'opening':opening,**cmp})
    return out

def btts_comparison(dist: dict, odds_payload: dict):
    bk=_bet365(odds_payload)
    if not bk: return None
    node=(bk.get('markets') or {}).get('btts') or {}; yes=_decimal((node.get('yes') or {}).get('last_seen')); no=_decimal((node.get('no') or {}).get('last_seen'))
    if yes is None or no is None: return None
    p_yes=float(dist['p_btts_yes']); my,mn=devig(yes,no)
    cmp=_evaluate(p_yes,yes,no,'YES') if p_yes>=my else _evaluate(1-p_yes,no,yes,'NO')
    opening=None; oy=_decimal((node.get('yes') or {}).get('opening')); on=_decimal((node.get('no') or {}).get('opening'))
    if oy and on:
        x,y=devig(oy,on); opening={'yes_odds':oy,'no_odds':on,'p_novig_selected':x if cmp['side']=='YES' else y}
    return {'market_family':'btts','market':'Bet365_btts','line':None,'p_model_yes':p_yes,'opening':opening,**cmp}
