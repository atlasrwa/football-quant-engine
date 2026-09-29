import sys,json,pathlib,datetime,hashlib
import numpy as np
from scipy.stats import poisson
p=pathlib.Path(__file__).resolve().parent
source=p.parent/'three_family_evidence';sys.path.insert(0,str(source))
import run_development as core
core.BUNDLES={k:v for k,v in core.BUNDLES.items() if k=='goals'}
spec=json.loads((p/'spec.json').read_text());quotes=json.loads((p/'reference_quotes.json').read_text())
now=datetime.datetime.now(datetime.timezone.utc);nowts=now.timestamp()
history=[json.loads(x) for x in (source/'out/v1/evidence.jsonl').read_text().splitlines()]
for r in history:
 assert r['kickoff_ts']<nowts
 for v in r['provenance'].values():
  if v is not None:assert v['observed_at']<=nowts
up={}
for path in pathlib.Path('/home/ubuntu/data/v3_pilot/provider_cache/upcoming').rglob('*.json'):
 observed=float(path.name.split('_')[0])
 if observed>nowts:continue
 for raw in json.loads(path.read_text()).get('data',[]):
  if raw['id'] in spec['fixture_ids'] and (raw['id'] not in up or up[raw['id']][0]<observed):up[raw['id']]=(observed,raw,str(path))
assert set(up)==set(spec['fixture_ids'])
targets=[]
for match_id,(observed,r,path) in up.items():
 ts=datetime.datetime.fromisoformat(r['utc_date'].replace('Z','+00:00')).timestamp();assert ts>nowts and r['status']=='scheduled'
 targets.append({'match_id':match_id,'kickoff':r['utc_date'],'kickoff_ts':ts,'home_id':r['home_team']['id'],'away_id':r['away_team']['id'],'context':{'is_neutral':r.get('is_neutral')},'raw_stats':{},'period_checks':[],'targets':{f+'.'+s:{'value':None,'period_status':'PERIOD_UNRESOLVED'} for f in ('goals','corners','bookings') for s in ('home','away')},'provenance':{'fixture':{'path':path,'observed_at':observed,'sha256':hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}}})
newpanel,_=core.features(sorted(history+targets,key=lambda r:(r['kickoff_ts'],r['match_id'])))
byid={r['match_id']:r for r in newpanel}
oldpanel={r['match_id']:r for r in json.loads((source/'out/development_v1/features.json').read_text())}
run=next(r for r in json.loads((source/'out/development_v1/runs.json').read_text()) if r.get('arm')=='M2' and r['family']=='goals' and r['fold']==1)
train=[oldpanel[i] for i in run['train_ids']];cal=[oldpanel[i] for i in run['calibration_ids']]
model=core.Fit(core.matrix(train,'goals','M2'),np.array([r['families']['goals']['y'] for r in train]).ravel())
cm=model.predict(core.matrix(cal,'goals','M2')).reshape(-1,2);factor=(np.array([r['families']['goals']['y'] for r in cal]).sum(axis=0)+20)/(cm.sum(axis=0)+20)
rows=[]
for target in targets:
 mid=target['match_id'];features=byid[mid];assert features['families']['goals']['eligible']
 mu=model.predict(core.matrix([features],'goals','M2'))*factor
 probs={'home':float(poisson.sf(1,mu[0])),'away':float(poisson.sf(1,mu[1])),'total':float(poisson.sf(2,sum(mu))),'btts':float((-np.expm1(-mu[0]))*(-np.expm1(-mu[1])))}
 q=quotes['quotes'][mid]
 for key,prob in probs.items():
  selected,opposite=q['pairs'][key];market=(1/selected)/(1/selected+1/opposite)
  rows.append({'fixture_id':mid,'fixture':q['fixture'],'kickoff':target['kickoff'],'freeze_at':now.isoformat(),'market':key,'line':None if key=='btts' else 2.5 if key=='total' else 1.5,'selected_outcome':'yes' if key=='btts' else 'over','p_model':prob,'p_opposite':1-prob,'selected_reference_odds':selected,'opposite_reference_odds':opposite,'p_market_no_vig':market,'disagreement_pp':100*(prob-market),'source_url':q['url'],'source_update_time':None,'odds_execution_verified':False,'state':'PROSPECTIVE_WORKFLOW_ONLY','settlement':'PENDING','model_status':'UNVALIDATED_RESEARCH_BASELINE','historical_feature_cutoff_ts':features['cutoff_ts'],'feature_sha256':hashlib.sha256(json.dumps(features,sort_keys=True).encode()).hexdigest()})
freeze={'test_id':spec['test_id'],'frozen_at':now.isoformat(),'predictions':rows,'model':'M2 development baseline original mean correction','model_coefficients':model.model.coef_.tolist(),'model_intercept':model.model.intercept_,'imputation':model.median.tolist(),'scaler_mean':model.mean.tolist(),'scaler_std':model.std.tolist(),'calibration_factor':factor.tolist(),'train_ids':run['train_ids'],'calibration_ids':run['calibration_ids'],'target_features':[byid[r['match_id']] for r in targets],'target_sources':targets,'spec_sha256':hashlib.sha256((p/'spec.json').read_bytes()).hexdigest(),'code_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'history_sha256':hashlib.sha256((source/'out/v1/evidence.jsonl').read_bytes()).hexdigest(),'corners':'UNCHANGED','cards':'NOT_EVALUATED_UNVERIFIED_SETTLEMENT','live_provider_calls':0}
with (p/'freeze.json').open('x') as f:f.write(json.dumps(freeze,indent=2,sort_keys=True)+'\n')
lines=['# Prospective workflow test — 29 September 2026','',f'Frozen at {now.isoformat()}. Two fixtures, eight markets. Research-only; neither validated probabilities nor verified executable odds.','', 'Both kickoffs: 18:45 UTC / 13:45 America/Bogota. Actual forecast timestamp is above; historical feature cutoff remains kickoff minus 24 hours. No backdated prediction.','', '| Fixture | Market | Model % | No-vig reference % | Difference pp | Over/Yes odds | Under/No odds |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
for r in rows:lines.append(f"| {r['fixture']} | {r['market']} {r['line'] or 'yes'} | {100*r['p_model']:.1f} | {100*r['p_market_no_vig']:.1f} | {r['disagreement_pp']:+.1f} | {r['selected_reference_odds']} | {r['opposite_reference_odds']} |")
lines+=['','Reference sources: https://yesplay.bet/sports/events/czechia-england-68931694 and https://yesplay.bet/sports/events/spain-croatia-68931696 . Retrieved from public pages; exact original quote-update timestamps are unavailable. Differences are observational references, not tradeable edge claims.','', 'All eight markets were fixed before probabilities were computed and remain in the ledger regardless of outcome. Settlement uses independently verified regulation-time scores. Settlement records must be appended separately, never overwrite freeze.json. No bets placed. Existing V3 corners unchanged. Cards omitted due to unverified settlement equivalence. The new calibration experiment was not promoted.']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
