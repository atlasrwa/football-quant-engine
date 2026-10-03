from __future__ import annotations
import gzip, hashlib, json, re
from pathlib import Path
import audit_cached_corpus as a

OUT=Path(__file__).resolve().parent
DATA=OUT/'CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz'
MAN=OUT/'CACHED_FOOTYSTATS_COUNT_EXTENSION_V1_MANIFEST.json'
CONTRACT=OUT/'FOOTYSTATS_CACHED_CAPABILITIES_V1.json'
VAL=OUT/'CROSS_PROVIDER_SEMANTIC_VALIDATION_V1.json'

def canonical(o): return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest_bytes(b): return hashlib.sha256(b).hexdigest()

def main():
 reg=json.loads(a.REGISTRY.read_text()); comp={}
 for x in reg['leagues']:
  name=x['footystats']['name']
  cs=(x.get('thestatsapi') or {}).get('competitions') or []
  if name in a.EXT:
   if len(cs)!=1: raise RuntimeError(f'{name}: expected one TSA competition, got {len(cs)}')
   comp[name]=cs[0]['id']
 league_obj=json.loads(a.FS_LEAGUES.read_text())['data']
 sid={}
 for lg in league_obj:
  for s in lg.get('season',[]): sid[int(s['id'])]=(lg['name'],s.get('year'))
 pat=re.compile(r'season_id:_(\d+)')
 selected={}; source_files={}
 for p in sorted(a.FS_CORPUS.glob('league-matches_*.json')):
  m=pat.search(p.name)
  if not m: continue
  season_id=int(m.group(1)); meta=sid.get(season_id)
  if not meta or meta[0] not in a.EXT: continue
  raw=p.read_bytes(); ph=digest_bytes(raw); obj=json.loads(raw); file_used=False
  for q in obj.get('data') or []:
   if str(q.get('status')).lower()!='complete': continue
   ts=q.get('date_unix')
   if not isinstance(ts,(int,float)) or ts>=a.CUTOFF: continue
   file_used=True
   mid=str(q['id']); row_hash=digest_bytes(canonical(q).encode())
   def val(k):
    v=q.get(k)
    return v if a.good(v) else None
   row={
    'schema_version':'qfe-footystats-cached-count-row-v1','provider':'FOOTYSTATS_CACHED',
    'provider_match_id':mid,'competition_name':meta[0],'deployment_competition_ref':comp[meta[0]],
    'footystats_season_id':season_id,'season_label':q.get('season'),'kickoff_unix':int(ts),
    'home_provider_team_id':str(q.get('homeID')),'away_provider_team_id':str(q.get('awayID')),
    'home_name':q.get('home_name'),'away_name':q.get('away_name'),
    'goals_home':val('homeGoalCount'),'goals_away':val('awayGoalCount'),
    'corners_home':val('team_a_corners'),'corners_away':val('team_b_corners'),
    'source_path':str(p),'source_file_sha256':ph,'source_row_sha256':row_hash,
    'availability_mode':'RETROSPECTIVE_CACHED_POSTMATCH'}
   prior=selected.get((meta[0],mid))
   if prior is not None and canonical({k:v for k,v in prior.items() if not k.startswith('source_')})!=canonical({k:v for k,v in row.items() if not k.startswith('source_')}):
    raise RuntimeError(f'conflicting duplicate FootyStats row {meta[0]} {mid}')
   selected[(meta[0],mid)]=row
  if file_used: source_files[str(p)]={'sha256':ph,'bytes':len(raw)}
 rows=sorted(selected.values(),key=lambda r:(r['kickoff_unix'],r['deployment_competition_ref'],r['provider_match_id']))
 payload=(''.join(canonical(r)+'\n' for r in rows)).encode()
 import io
 buf=io.BytesIO()
 with gzip.GzipFile(filename='',mode='wb',fileobj=buf,compresslevel=9,mtime=0) as gz: gz.write(payload)
 DATA.write_bytes(buf.getvalue())
 by={}
 for r in rows:
  x=by.setdefault(r['competition_name'],{'rows':0,'corner_complete':0,'first_kickoff':r['kickoff_unix'],'last_kickoff':r['kickoff_unix']})
  x['rows']+=1; x['corner_complete']+=int(r['corners_home'] is not None and r['corners_away'] is not None)
  x['first_kickoff']=min(x['first_kickoff'],r['kickoff_unix']); x['last_kickoff']=max(x['last_kickoff'],r['kickoff_unix'])
 bundle=[{'path':p,**v} for p,v in sorted(source_files.items())]
 manifest={
  'version':'QFE_V2_CACHED_FOOTYSTATS_COUNT_EXTENSION_V1','status':'AUXILIARY_RESEARCH_NOT_CHAMPION',
  'network_calls':0,'protected_outcomes_opened':False,'cutoff_iso':'2026-08-01T00:00:00Z',
  'row_count':len(rows),'corner_complete_rows':sum(r['corners_home'] is not None and r['corners_away'] is not None for r in rows),
  'competition_count':len(by),'by_competition':by,'data_path':str(DATA),
  'data_gzip_sha256':digest_bytes(DATA.read_bytes()),'data_uncompressed_sha256':digest_bytes(payload),
  'source_file_count':len(bundle),'source_files':bundle,'source_bundle_sha256':digest_bytes(canonical(bundle).encode()),
  'semantic_validation_sha256':hashlib.sha256(VAL.read_bytes()).hexdigest(),
  'eligible_fields':['goals_home','goals_away','corners_home','corners_away'],
  'forbidden_implicit_fields':['shots','shots_on_target','possession','fouls','yellow_cards','xg','odds','potential'],
  'provider_transfer_rule':'must be evaluated as explicit auxiliary-provider challenger against TSA-only OOS; no silent pooling'}
 MAN.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 validation=json.loads(VAL.read_text())
 contract={
  'version':'FOOTYSTATS_CACHED_CAPABILITIES_V1','provider':'FOOTYSTATS_CACHED','network_source_available':False,
  'source_scope':'immutable local cache only','missing_semantics':'negative sentinel -> null; zero remains valid',
  'implicit_cross_provider_blending':False,'fields':[
   {'field':'goals_home/away','historical_model_eligible':True,'target_source_eligible':True,'cross_provider_status':'NEAR_EQUIVALENT_NOT_EXACT','validation_exact_rate':validation['goals']['exact_rate']},
   {'field':'corners_home/away','historical_model_eligible':True,'target_source_eligible':True,'cross_provider_status':'NEAR_EQUIVALENT_NOT_EXACT','validation_exact_rate':validation['fields']['corners']['exact_rate'],'validation_mean_signed_difference':validation['fields']['corners']['mean_signed_difference']},
   {'field':'shots','historical_model_eligible':False,'cross_provider_status':'PROVIDER_SPECIFIC_ONLY','validation_exact_rate':validation['fields']['shots']['exact_rate']},
   {'field':'shots_on_target','historical_model_eligible':False,'cross_provider_status':'PROVIDER_SPECIFIC_ONLY','validation_exact_rate':validation['fields']['sot']['exact_rate']},
   {'field':'possession','historical_model_eligible':False,'cross_provider_status':'PROVIDER_SPECIFIC_ONLY','validation_exact_rate':validation['fields']['possession']['exact_rate']},
   {'field':'fouls','historical_model_eligible':False,'cross_provider_status':'PROVIDER_SPECIFIC_ONLY','validation_exact_rate':validation['fields']['fouls']['exact_rate']},
   {'field':'yellow_cards','historical_model_eligible':False,'cross_provider_status':'PROVIDER_SPECIFIC_ONLY','validation_exact_rate':validation['fields']['yellow']['exact_rate']},
   {'field':'xg','historical_model_eligible':False,'cross_provider_status':'PROVIDER_MODEL_NOT_EQUIVALENT','validation_exact_rate':validation['fields']['xg']['exact_rate']}]}
 CONTRACT.write_text(json.dumps(contract,indent=2,sort_keys=True)+'\n')
 print(json.dumps(manifest,indent=2,sort_keys=True))
if __name__=='__main__': main()
