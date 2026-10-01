import json
from pathlib import Path
from src.research.v37_future50.clv import closing_clv

def _payload(p_over):
    over=1.0/p_over
    under=1.0/(1.0-p_over)
    return {'data':{'bookmakers':[{'bookmaker':'Bet365','markets':{
        'total_goals':{'3.5':{
            'over':{'last_seen':over},
            'under':{'last_seen':under},
        }}
    }}]}}

def test_clv_uses_same_declared_side_and_line(tmp_path):
    market=tmp_path/'market.jsonl'
    cache=tmp_path/'cache'
    ph='abc123'
    d=cache/'odds'/'m1'
    d.mkdir(parents=True)
    (d/f'100_{ph}.json').write_text(json.dumps(_payload(.40)))
    market.write_text(json.dumps({
        'fixture_id':'m1','vintage':'FINAL','observed_at':100.0,
        'observed_at_utc':'x','odds_payload_hash':ph,
    })+'\n')
    out=closing_clv(
        market_path=market,cache=cache,fixture_id='m1',
        family='goals',line=3.5,side='UNDER',
        entry_market_p=.50,model_p=.66,
    )
    assert out['status']=='OK'
    assert abs(out['closing_market_p']-.60)<1e-9
    assert abs(out['market_move_pp']-10.0)<1e-9
    assert abs(out['entry_model_market_gap_pp']-16.0)<1e-9
    assert abs(out['closing_model_market_gap_pp']-6.0)<1e-9
    assert out['direction']=='TOWARD_MODEL'
