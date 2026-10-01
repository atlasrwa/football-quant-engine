from __future__ import annotations
import json
from pathlib import Path
from src.research.v37_future50.model import predict_fixture
from src.research.v37_future50.market import evaluate
ROOT=Path('/home/ubuntu/data/v3_pilot'); OUT=Path(__file__).resolve().parent/'OLD_PILOT_COUNTERFACTUAL.json'
def grade(side,line,value):
    if value is None:return None
    if value==line:return 'PUSH'
    return 'WIN' if (value>line if side=='OVER' else value<line) else 'LOSS'
def main():
    ledger=json.load(open(ROOT/'lean_ledger_map_v1.json')); oldstate=json.load(open(ROOT/'state.json')); out=[]
    for row in ledger['tests']:
        rec={'test_number':row['pilot_test_number'],'cohort':row['cohort'],'fixture':row['fixture'],'old_side':row['side'],'old_line':row['line'],'old_result':row['result'],'status':'UNSUPPORTED'}
        mid=row.get('fixture_id'); fam=row.get('market_family')
        if row.get('market') not in {'Bet365_total_goals','Bet365_total_corners'} or not mid or mid not in oldstate['fixtures']:
            rec['reason']='requires identifiable Bet365 match-total goals/corners fixture'; out.append(rec); continue
        fx=oldstate['fixtures'][mid]
        if 'kickoff_ts' not in fx: fx['kickoff_ts']=fx['ts']
        if 'kickoff' not in fx: fx['kickoff']=fx['utc_date']
        # Recover explicit neutral value from cached scheduled payload when available.
        neutral=None
        for p in sorted((ROOT/'provider_cache'/'upcoming'/fx['competition_id']).glob('*.json')):
            try:
                obj=json.load(open(p))
                m=next((x for x in (obj.get('data') or []) if str(x.get('id'))==mid),None)
                if m and isinstance(m.get('is_neutral'),bool): neutral=m['is_neutral']
            except Exception: pass
        fx['is_neutral']=neutral; fx['context']={'is_neutral':neutral}
        pred=predict_fixture(fx); dist=pred.get(fam)
        if not dist or str(row['line']) not in dist['probabilities']:
            rec['reason']='new model abstained or line unsupported'; rec['abstentions']=pred['abstentions']; out.append(rec); continue
        p_over=float(dist['probabilities'][str(row['line'])]['p_over'])
        if row['side']=='OVER': over=float(row['price_decimal']); under=float(row['opposite_price_decimal'])
        else: under=float(row['price_decimal']); over=float(row['opposite_price_decimal'])
        cmp=evaluate(p_over,over,under); value=row.get('settled_value')
        rec.update({'status':'RESCORED','new_side':cmp['side'],'new_p_model':cmp['p_model_selected'],'new_p_market':cmp['p_market_novig_selected'],'new_delta':cmp['model_minus_market_novig'],'new_qualifies':cmp['qualifies'],'new_result':grade(cmp['side'],float(row['line']),value),'settled_value':value,'model_version':dist['version'],'abstentions':pred['abstentions']}); out.append(rec)
    summary={'ledger_declared':len(ledger['tests']),'expected_design_target':40,'supported_rescored':sum(r['status']=='RESCORED' for r in out),'new_qualifiers':sum(r.get('new_qualifies') is True for r in out),'new_qualifier_wins':sum(r.get('new_qualifies') is True and r.get('new_result')=='WIN' for r in out),'new_qualifier_losses':sum(r.get('new_qualifies') is True and r.get('new_result')=='LOSS' for r in out),'new_qualifier_pending':sum(r.get('new_qualifies') is True and r.get('new_result') is None for r in out)}
    OUT.write_text(json.dumps({'summary':summary,'rows':out},indent=2,sort_keys=True)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
