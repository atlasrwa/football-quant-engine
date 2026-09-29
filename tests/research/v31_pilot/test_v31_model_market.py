from src.research.v31_pilot.model import fit_predict
from src.research.v31_pilot.market import goal_comparisons,btts_comparison

def synthetic_rows(n=90):
    teams=['A','B','C','D','E','F']; rows=[]
    for i in range(n):
        h=teams[i%6]; a=teams[(i+1+i//6)%6]
        if h==a: a=teams[(i+2)%6]
        gh=(i*7)%4; ga=(i*5+1)%3
        rows.append({'match_id':f'm{i}','ts':1_000_000+i*172800,'home_id':h,'away_id':a,'is_neutral':False,
                     'metrics':{'home':{'goals':float(gh),'shots':10+i%5,'sot':3+i%4,'box':6+i%3,'big':1+i%3},
                                'away':{'goals':float(ga),'shots':8+i%4,'sot':2+i%3,'box':4+i%4,'big':i%2}}})
    return rows

def test_joint_goals_and_btts_share_distribution():
    rows=synthetic_rows(); target={'match_id':'t','ts':rows[-1]['ts']+3*172800,'home_id':'A','away_id':'B','is_neutral':False}
    d=fit_predict(rows,target)
    assert d['n_train']>=30 and d['n_calibration']>=15
    assert 0<d['p_btts_yes']<1
    for line in ('2.5','3.5'): assert 0<d['probabilities'][line]['p_over']<1
    assert len(d['distribution_hash'])==64

def test_market_comparison_supports_btts_and_goal_totals():
    dist={'probabilities':{'2.5':{'p_over':0.68},'3.5':{'p_over':0.32}},'p_btts_yes':0.66}
    odds={'data':{'bookmakers':[{'bookmaker':'Bet365','markets':{
        'total_goals':{'2.5':{'over':{'last_seen':'2.00','opening':'2.10'},'under':{'last_seen':'1.80','opening':'1.75'}},
                       '3.5':{'over':{'last_seen':'2.80','opening':None},'under':{'last_seen':'1.45','opening':None}}},
        'btts':{'yes':{'last_seen':'2.00','opening':'1.95'},'no':{'last_seen':'1.80','opening':'1.85'}}}}]}}
    goals=goal_comparisons(dist,odds); b=btts_comparison(dist,odds)
    assert next(x for x in goals if x['line']==2.5)['qualifies'] is True
    assert b is not None and b['side']=='YES' and b['qualifies'] is True
