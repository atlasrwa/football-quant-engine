from __future__ import annotations
import collections, datetime as dt, hashlib, json, math, re, unicodedata
from pathlib import Path

ROOT=Path('/home/ubuntu')
WT=Path(__file__).resolve().parents[2]
CUTOFF=int(dt.datetime(2026,8,1,tzinfo=dt.timezone.utc).timestamp())
FS_LEAGUES=ROOT/'docs/research/footystats-ground-truth-raw/league_list.json'
FS_CORPUS=ROOT/'data/discovery/corpus'
REGISTRY=ROOT/'data/discovery/provider_league_registry.json'
V39=ROOT/'handoff_out/evidence_v323/research/v39_historical1000/evidence_v4.jsonl'
FOUND=WT/'evidence/foundation_v1/QFE_FOUNDATION_V1_CAPABILITY_COVERAGE.json'
OUT=WT/'research/qfe_v2_historical_expansion'

CORE={
 'England Premier League','England Championship','Spain La Liga','Spain Segunda División',
 'France Ligue 1','France Ligue 2'}
EXT={
 'Germany Bundesliga','Germany 2. Bundesliga','Italy Serie A','Italy Serie B',
 'Netherlands Eredivisie','Portugal Liga NOS','Belgium Pro League','Turkey Süper Lig',
 'Poland Ekstraklasa','Denmark Superliga','Brazil Serie A','USA MLS'}
TARGET=CORE|EXT|{'England EFL League One','England EFL League Two'}
ALIASES={
 'montreal impact':'montreal','new york rb':'new york red bulls',
 'sj earthquakes':'san jose earthquakes','sporting kc':'sporting kansas city',
 'wolverhampton wanderers':'wolverhampton'}
FIELDS={
 'corners':('team_a_corners','team_b_corners','overview.corner_kicks.all.home','overview.corner_kicks.all.away'),
 'shots':('team_a_shots','team_b_shots','overview.total_shots.all.home','overview.total_shots.all.away'),
 'sot':('team_a_shotsOnTarget','team_b_shotsOnTarget','overview.shots_on_target.all.home','overview.shots_on_target.all.away'),
 'possession':('team_a_possession','team_b_possession','overview.ball_possession.all.home','overview.ball_possession.all.away'),
 'fouls':('team_a_fouls','team_b_fouls','overview.fouls.all.home','overview.fouls.all.away'),
 'yellow':('team_a_yellow_cards','team_b_yellow_cards','overview.yellow_cards.all.home','overview.yellow_cards.all.away'),
 'xg':('team_a_xg','team_b_xg','overview.expected_goals.all.home','overview.expected_goals.all.away')}

def sha(p:Path)->str:
 return hashlib.sha256(p.read_bytes()).hexdigest()

def norm(s):
 s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().casefold().replace('&',' and ')
 toks=[x for x in re.sub(r'[^a-z0-9]+',' ',s).split() if x not in {'fc','afc','sc','cf'}]
 s=' '.join(toks)
 return ALIASES.get(s,s)

def good(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and v>=0

def extract_fixture(row):
 prov=(row.get('provenance') or {}).get('fixture') or {}
 p=Path(str(prov.get('path') or ''))
 if not p.exists(): return None
 try: obj=json.loads(p.read_text())
 except Exception: return None
 for fx in obj.get('data') or []:
  if str(fx.get('id'))==str(row.get('match_id')): return fx
 return None

def build_fs():
 league_obj=json.loads(FS_LEAGUES.read_text())['data']
 sid={}
 for lg in league_obj:
  for s in lg.get('season',[]): sid[int(s['id'])]=(lg['name'],s.get('year'))
 rows=collections.defaultdict(dict); files=collections.defaultdict(set)
 pat=re.compile(r'season_id:_(\d+)')
 for p in FS_CORPUS.glob('league-matches_*.json'):
  m=pat.search(p.name)
  if not m: continue
  meta=sid.get(int(m.group(1)))
  if not meta or meta[0] not in TARGET: continue
  obj=json.loads(p.read_text()); files[meta[0]].add(str(p))
  for r in obj.get('data') or []:
   if str(r.get('status')).lower()!='complete': continue
   ts=r.get('date_unix')
   if not isinstance(ts,(int,float)) or ts>=CUTOFF: continue
   rows[meta[0]][str(r['id'])]=r
 return {k:list(v.values()) for k,v in rows.items()},files

def registry_map():
 o=json.loads(REGISTRY.read_text()); out={}
 for x in o['leagues']:
  name=x['footystats']['name']
  for c in (x.get('thestatsapi') or {}).get('competitions') or []:
   out[c['id']]=name
 return out

def fs_index(rows):
 idx=collections.defaultdict(list)
 for r in rows:
  key=(norm(r.get('home_name')),norm(r.get('away_name')))
  idx[key].append(r)
 return idx

def main():
 fs,fs_files=build_fs(); cmap=registry_map()
 indices={lg:fs_index(rr) for lg,rr in fs.items()}
 matches=[]; join=collections.Counter(); by_league=collections.Counter()
 with V39.open() as f:
  for line in f:
   r=json.loads(line)
   if r.get('kickoff_ts',10**20)>=CUTOFF or not r.get('raw_stats'): continue
   lg=cmap.get(r.get('competition_id'))
   if lg not in indices: continue
   fx=extract_fixture(r)
   if not fx: join['fixture_source_missing']+=1; continue
   home=norm((fx.get('home_team') or {}).get('name')); away=norm((fx.get('away_team') or {}).get('name'))
   candidates=[]
   reg=(fx.get('score') or {}).get('regulation') or {}
   for q in indices[lg].get((home,away),[]):
    if abs(float(q.get('date_unix',0))-float(r['kickoff_ts']))>21600: continue
    if q.get('homeGoalCount')!=reg.get('home') or q.get('awayGoalCount')!=reg.get('away'): continue
    candidates.append(q)
   if len(candidates)!=1:
    join['ambiguous' if len(candidates)>1 else 'no_match']+=1; continue
   q=candidates[0]; join['matched']+=1; by_league[lg]+=1
   matches.append((lg,r,q))
 comp={}
 for label,(fa,fb,ta,tb) in FIELDS.items():
  n=exact=0; absdiff=[]
  for lg,r,q in matches:
   raw=r['raw_stats']
   vals=[q.get(fa),q.get(fb),raw.get(ta),raw.get(tb)]
   if not all(good(v) for v in vals): continue
   for a,b in ((vals[0],vals[2]),(vals[1],vals[3])):
    n+=1; exact+=int(float(a)==float(b)); absdiff.append(abs(float(a)-float(b)))
  comp[label]={'side_observations':n,'exact':exact,'exact_rate':None if not n else exact/n,
               'mae':None if not absdiff else sum(absdiff)/len(absdiff),
               'max_abs_diff':None if not absdiff else max(absdiff)}
 foundation=json.loads(FOUND.read_text())
 disc=foundation.get('discovery') or []
 core_pre=collections.Counter()
 for s in disc:
  # All current 2026/27 slices have f27 in filename; exclude them from development history.
  if 'f27_' in str(s.get('fixture_file','')): continue
  if s.get('usable_for_audit'):
   for c in s.get('competition_refs') or []: core_pre[c]+=int(s.get('finished_fixture_count') or 0)
 # fallback from frozen known total if older evidence file omits discovery
 if not core_pre: core_total=5323
 else: core_total=sum(core_pre.values())
 ext_counts={lg:len(fs.get(lg,[])) for lg in sorted(EXT)}
 candidate=core_total+sum(ext_counts.values())
 sources={
  'foundation_coverage':{'path':str(FOUND),'sha256':sha(FOUND)},
  'v39_evidence_validation_only':{'path':str(V39),'sha256':sha(V39)},
  'footystats_league_list':{'path':str(FS_LEAGUES),'sha256':sha(FS_LEAGUES)},
  'provider_registry':{'path':str(REGISTRY),'sha256':sha(REGISTRY)}}
 obj={
  'version':'QFE_V2_HISTORICAL_CACHE_AUDIT_V1','network_calls':0,'cutoff_unix':CUTOFF,
  'cutoff_iso':'2026-08-01T00:00:00Z','source_policy':{
   'core_six':'THESTATSAPI_FOUNDATION_CANONICAL',
   'extension_twelve':'FOOTYSTATS_CACHED_PROVIDER_SCOPED_ONLY',
   'v39':'VALIDATION_ONLY_NOT_TRAINING_SOURCE',
   'field_blending':False,'protected_outcomes_opened':False},
  'candidate':{'core_thestatsapi_preprotected':core_total,'extension_cached_footystats':sum(ext_counts.values()),
               'candidate_unique_by_scope':candidate,'extension_by_league':ext_counts,
               'missing_target_competitions':['England EFL League One','England EFL League Two']},
  'validation_panel':{'matched_fixtures':join['matched'],'join_counts':dict(join),'matched_by_league':dict(sorted(by_league.items())),
                      'identity_rule':'NFKD/casefold/remove FC-AFC-SC-CF; exact home-away; kickoff ±6h; regulation-score agreement; unique candidate',
                      'field_comparison':comp},
  'sources':sources}
 OUT.mkdir(parents=True,exist_ok=True)
 audit=OUT/'CACHED_CORPUS_AUDIT_V1.json'; audit.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
 manifest={
  'version':'QFE_V2_HISTORICAL_CANDIDATE_MANIFEST_V1','status':'RESEARCH_CANDIDATE_NOT_MODEL_INPUT',
  'cutoff_iso':obj['cutoff_iso'],'network_calls':0,'protected_outcomes_opened':False,
  'candidate_unique_fixture_count':candidate,'provider_scopes':obj['source_policy'],
  'core_thestatsapi_fixture_count':core_total,'footystats_extension_fixture_count':sum(ext_counts.values()),
  'footystats_extension_by_league':ext_counts,'semantic_validation_audit_sha256':sha(audit),
  'source_hashes':sources}
 (OUT/'CANDIDATE_MANIFEST_V1.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps(obj,indent=2,sort_keys=True))
if __name__=='__main__': main()
