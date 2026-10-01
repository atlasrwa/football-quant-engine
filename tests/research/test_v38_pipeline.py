import json
from src.research.v38_paired50.market import eval_pair
from src.research.v38_paired50.pipeline import select_paired_line

def test_selection_thresholds_match_v37():
    assert eval_pair(.61,2.0,2.0)['qualifies'] is True
    assert eval_pair(.59,2.0,2.0)['qualifies'] is False

def test_line_selection_is_market_only():
    control=[{'line':2.5},{'line':3.5}]
    challenger=[{'line':2.5},{'line':3.5}]
    odds={'data':{'bookmakers':[{'bookmaker':'Bet365','markets':{'total_goals':{
      '2.5':{'over':{'last_seen':2.0},'under':{'last_seen':2.0}},
      '3.5':{'over':{'last_seen':3.0},'under':{'last_seen':1.5}}
    }}}]}}
    line,pm,_,_=select_paired_line(control,challenger,odds,'goals')
    assert line==2.5 and abs(pm-.5)<1e-12
