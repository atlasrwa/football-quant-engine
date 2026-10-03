from __future__ import annotations
import collections, json
from pathlib import Path
import audit_cached_corpus as a

OUT=Path(__file__).resolve().parent/'CROSS_PROVIDER_SEMANTIC_VALIDATION_V1.json'

def main():
 fs,_=a.build_fs(); cmap=a.registry_map(); idx={lg:a.fs_index(rr) for lg,rr in fs.items()}
 matched=[]; join=collections.Counter(); by=collections.Counter()
 with a.V39.open() as f:
  for line in f:
   r=json.loads(line)
   if r.get('kickoff_ts',10**20)>=a.CUTOFF or not r.get('raw_stats'): continue
   lg=cmap.get(r.get('competition_id'))
   if lg not in idx: continue
   fx=a.extract_fixture(r)
   if not fx: join['fixture_source_missing']+=1; continue
   key=(a.norm((fx.get('home_team') or {}).get('name')),a.norm((fx.get('away_team') or {}).get('name')))
   cand=[q for q in idx[lg].get(key,[]) if abs(float(q.get('date_unix',0))-float(r['kickoff_ts']))<=21600]
   if len(cand)!=1:
    join['ambiguous' if len(cand)>1 else 'no_match']+=1; continue
   matched.append((lg,r,cand[0],fx)); join['matched_identity_only']+=1; by[lg]+=1
 # Goals are evaluated independently of the identity join.
 goals_n=goals_exact=0; goal_mismatch=[]
 for lg,r,q,fx in matched:
  reg=(fx.get('score') or {}).get('regulation') or {}
  if all(a.good(v) for v in [q.get('homeGoalCount'),q.get('awayGoalCount'),reg.get('home'),reg.get('away')]):
   goals_n+=1
   ok=(q['homeGoalCount']==reg['home'] and q['awayGoalCount']==reg['away'])
   goals_exact+=int(ok)
   if not ok and len(goal_mismatch)<50:
    goal_mismatch.append({'league':lg,'match_id':r['match_id'],'kickoff':fx.get('utc_date'),
      'home':(fx.get('home_team') or {}).get('name'),'away':(fx.get('away_team') or {}).get('name'),
      'footystats':[q['homeGoalCount'],q['awayGoalCount']],'thestatsapi':[reg['home'],reg['away']]})
 comparisons={}
 for label,(fa,fb,ta,tb) in a.FIELDS.items():
  diffs=[]; mismatch=[]; league=collections.defaultdict(list)
  for lg,r,q,fx in matched:
   raw=r['raw_stats']; vals=[q.get(fa),q.get(fb),raw.get(ta),raw.get(tb)]
   if not all(a.good(v) for v in vals): continue
   for side,x,y in [('home',vals[0],vals[2]),('away',vals[1],vals[3])]:
    d=float(x)-float(y); diffs.append(d); league[lg].append(d)
    if d and len(mismatch)<50:
     mismatch.append({'league':lg,'match_id':r['match_id'],'kickoff':fx.get('utc_date'),'side':side,
       'home':(fx.get('home_team') or {}).get('name'),'away':(fx.get('away_team') or {}).get('name'),
       'footystats':x,'thestatsapi':y,'difference':d})
  comparisons[label]={
   'side_observations':len(diffs),'exact':sum(d==0 for d in diffs),
   'exact_rate':None if not diffs else sum(d==0 for d in diffs)/len(diffs),
   'mean_signed_difference':None if not diffs else sum(diffs)/len(diffs),
   'mae':None if not diffs else sum(abs(d) for d in diffs)/len(diffs),
   'max_abs_difference':None if not diffs else max(abs(d) for d in diffs),
   'by_league':{lg:{'n':len(ds),'exact_rate':sum(d==0 for d in ds)/len(ds),'mean_signed_difference':sum(ds)/len(ds)} for lg,ds in sorted(league.items())},
   'mismatch_examples':mismatch}
 out={
  'version':'QFE_V2_CROSS_PROVIDER_SEMANTIC_VALIDATION_V1','network_calls':0,
  'cutoff_iso':'2026-08-01T00:00:00Z','protected_outcomes_opened':False,
  'identity_join':'exact normalized home/away + kickoff within ±6h + unique candidate; score NOT used for identity',
  'join_counts':dict(join),'matched_by_league':dict(sorted(by.items())),
  'goals':{'fixtures':goals_n,'exact':goals_exact,'exact_rate':goals_exact/goals_n if goals_n else None,'mismatch_examples':goal_mismatch},
  'fields':comparisons,
  'interpretation':{
   'implicit_blending_allowed':False,
   'goals':'provider-scoped auxiliary only; high agreement but nonzero provider disagreements',
   'corners':'provider-scoped auxiliary only; near-equivalent empirically but not exact',
   'shots_sot_possession_fouls_yellows':'provider-specific only; do not harmonize into TSA feature definitions',
   'xg':'provider-specific model output; never harmonize by name'}}
 OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:v for k,v in out.items() if k not in {'fields'}},indent=2,sort_keys=True))
 print('FIELD_SUMMARY',json.dumps({k:{x:v[x] for x in ['side_observations','exact_rate','mean_signed_difference','mae','max_abs_difference']} for k,v in comparisons.items()},indent=2,sort_keys=True))
if __name__=='__main__': main()
