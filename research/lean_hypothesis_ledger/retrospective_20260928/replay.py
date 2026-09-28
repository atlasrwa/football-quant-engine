#!/usr/bin/env python3
"""Retrospective replay. Uses recorded inputs; does not select a fitted model."""
import json, math, sys, pathlib
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from lean_goal_probability_v0 import over_half,btts_yes,one_x_two
rows=[json.loads(x) for x in (BASE/'ledger_v1.jsonl').read_text().splitlines()]
corner=next(r for r in rows if r.get('scan_id')=='QFE-WEB-CORNERS-20260928-01')
goal=next(r for r in rows if r.get('scan_id')=='QFE-GOALS-CARDS-SENSITIVITY-20260928-01')
out={'classification':'RETROSPECTIVE_REPLAY_NOT_A_DECLARATION','counts_toward_40':False,
'input_events':[corner['scan_id'],goal['scan_id']],
'warning':'Scenario ranges are not confidence intervals. No calibrated p_model or executable Rushbet edge established.',
'fixtures':[]}
def compare(p,odds,opposite=None):
    nv=(1/odds)/(1/odds+1/opposite) if opposite else None
    return {'p':p,'odds':odds,'break_even':1/odds,'no_vig_reference':nv,
            'gap_break_even_pp':100*(p-1/odds),'gap_no_vig_pp':100*(p-nv) if nv else None,'ev':p*odds-1}
alt_rates=[[6.5,7.4],[4.7,5.8],[4.1,4.2]]
teams=[['Türkiye','Italy'],['Sweden','Poland'],['Romania','Bosnia']]
extra=[
 {'totals':[(1.5,1.20,4.40),(2.5,1.65,2.20),(3.5,2.55,1.50),(4.5,4.50,1.19)],
  'team': [[(0.5,1.25,3.55),(1.5,2.20,1.60),(2.5,4.70,1.15)],[(0.5,1.20,4.10),(1.5,1.94,1.77),(2.5,3.90,1.22)]],
  '1x2':[2.95,3.45,2.38]},
 {'totals':[(2.5,1.61,2.23),(3.5,2.48,1.50)],
  'team':[[(0.5,1.14,4.70),(1.5,1.71,1.97),(2.5,3.15,1.30)],[(0.5,1.32,3.00),(1.5,2.49,1.45),(2.5,5.40,1.10)]],
  '1x2':[1.92,3.80,3.65]},
 {'totals':[],'team':[[],[]],'1x2':[2.32,3.25,3.05]}]
for i,(c,g) in enumerate(zip(corner['fixtures'],goal['fixtures'])):
    f={'fixture':c['name'],'corner_original_lambda':c['lambda'],'corners':[],'goals':[],'cards':[]}
    alt=[(alt_rates[i][j]+sum(c['inputs'][j][2:])/2)/2 for j in range(2)]
    alt.append(sum(alt)); f['corner_source_window_sensitivity_lambda']=alt
    for r in c['rows']:
        for side in ['over','under']:
            odds=r[side+'_odds']
            if odds is None: continue
            p=r['p_over'] if side=='over' else 1-r['p_over']
            pa=over_half(alt[r['team']],r['line'])
            if side=='under': pa=1-pa
            d=compare(p,odds,r['under_odds' if side=='over' else 'over_odds'])
            d.update(market=(teams[i][r['team']] if r['team']<2 else 'Total')+' '+side+' '+str(r['line'])+' corners',
                     source_window_sensitivity_p=pa,source_window_sensitivity_gap_be_pp=100*(pa-1/odds))
            f['corners'].append(d)
    def pair(name,ps,odds,opp,source):
        for side,price,other in [('over',odds,opp),('under',opp,odds)]:
            vals={k:compare(p if side=='over' else 1-p,price,other) for k,p in ps.items()}
            f['goals'].append({'market':name+' '+side,'source':source,'scenarios':vals,
                'both_scenarios_clear_break_even':all(v['gap_break_even_pp']>0 for v in vals.values())})
    lam={k:v['lambda'] for k,v in g['goal_sensitivity'].items()}
    q=g['quotes']
    pair('Total 2.5 goals',{k:over_half(sum(v),2.5) for k,v in lam.items()},q['over'],q['under'],'recorded original SG quote')
    pair('BTTS (over=Yes; under=No)',{k:btts_yes(*v) for k,v in lam.items()},q['yes'],q['no'],'recorded original BTTS quote')
    for line,o,u in extra[i]['totals']:
        pair('Total '+str(line)+' goals',{k:over_half(sum(v),line) for k,v in lam.items()},o,u,'pre-match conversation YesPlay snapshot')
    for j,quotes in enumerate(extra[i]['team']):
        for line,o,u in quotes:
            pair(teams[i][j]+' '+str(line)+' goals',{k:over_half(v[j],line) for k,v in lam.items()},o,u,'pre-match conversation YesPlay snapshot')
    prices=extra[i]['1x2']; z=sum(1/x for x in prices)
    for j,label in enumerate([teams[i][0]+' win','Draw',teams[i][1]+' win']):
        values={}
        for k,v in lam.items():
            p=one_x_two(*v)[j]; d=compare(p,prices[j])
            d.update(no_vig_reference=(1/prices[j])/z,gap_no_vig_pp=100*(p-(1/prices[j])/z))
            values[k]=d
        f['goals'].append({'market':label,'source':'pre-match conversation YesPlay (TUR/SWE), SG (ROU) snapshot','scenarios':values,
                          'both_scenarios_clear_break_even':all(d['gap_break_even_pp']>0 for d in values.values())})
    for j,rate in enumerate(g['cards']+[sum(g['cards'])]):
        for line in ([1.5,2.5,3.5] if j<2 else [3.5,4.5,5.5]):
            p=1-over_half(rate,line)
            f['cards'].append({'market':(teams[i][j] if j<2 else 'Total')+' under '+str(line)+' cards','lambda_raw':rate,
                               'diagnostic_p':p,'diagnostic_fair_odds':1/p,'verified_comparable_odds':None,
                               'reason':'Undefined screenshot cards vs yellow-card/bookings contract; no fitted referee/opponent model.'})
    out['fixtures'].append(f)
target=pathlib.Path(__file__).parent/'calculations.json'
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
for f in out['fixtures']:
 print(f['fixture'])
 for r in f['corners']:
  if r['gap_break_even_pp']>0: print(' CORNER',r['market'],round(r['p']*100,2),round(r['gap_break_even_pp'],2),'alternative',round(r['source_window_sensitivity_p']*100,2))
 for r in f['goals']:
  if r['both_scenarios_clear_break_even']: print(' GOAL BOTH POSITIVE',r['market'],[(k,round(v['p']*100,2),round(v['gap_break_even_pp'],2)) for k,v in r['scenarios'].items()])
