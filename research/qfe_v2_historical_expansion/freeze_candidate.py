from __future__ import annotations
import hashlib,json
from pathlib import Path
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
CUTOFF=1785542400
BASE=Path('/home/ubuntu/data/thestatsapi/championship')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jsha(o): return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def main():
 ext=json.loads((HERE/'CACHED_FOOTYSTATS_COUNT_EXTENSION_V1_MANIFEST.json').read_text())
 val=json.loads((HERE/'CROSS_PROVIDER_SEMANTIC_VALIDATION_V1.json').read_text())
 corpus=build_multiseason_pit_corpus(base_dir=BASE,pit_spec=PITDatasetSpec(decision_horizon_seconds=6*3600))
 core=[m for m in corpus.matches if m.date_unix<CUTOFF]
 core_hash=jsha([m.to_dict() for m in core])
 core_corners=sum(m.corners_home is not None and m.corners_away is not None for m in core)
 core_by={}
 for m in core: core_by[m.competition_ref]=core_by.get(m.competition_ref,0)+1
 obj={
  'version':'QFE_V2_HISTORICAL_CANDIDATE_V1','status':'FROZEN_RESEARCH_CANDIDATE_NOT_MODEL_INPUT',
  'created_from_network_calls':0,'protected_outcomes_opened':False,'cutoff_iso':'2026-08-01T00:00:00Z',
  'scope':{
   'target_competitions':20,'covered_competitions':18,
   'missing_competitions':['England EFL League One','England EFL League Two'],
   'core_provider':'THESTATSAPI','auxiliary_provider':'FOOTYSTATS_CACHED'},
  'counts':{
   'core_thestatsapi':len(core),'core_thestatsapi_corner_complete':core_corners,
   'auxiliary_footystats':ext['row_count'],'auxiliary_footystats_corner_complete':ext['corner_complete_rows'],
   'candidate_total':len(core)+ext['row_count'],'candidate_corner_complete':core_corners+ext['corner_complete_rows']},
  'core':{
   'full_foundation_manifest_hash':corpus.manifest.manifest_hash,
   'preprotected_content_hash':core_hash,'by_competition':dict(sorted(core_by.items())),
   'source_bundle_hash':corpus.manifest.unique_source_bundle_hash},
  'auxiliary':{
   'data_artifact':'research/qfe_v2_historical_expansion/CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz',
   'data_gzip_sha256':ext['data_gzip_sha256'],'data_uncompressed_sha256':ext['data_uncompressed_sha256'],
   'source_bundle_sha256':ext['source_bundle_sha256'],'by_competition':ext['by_competition']},
  'semantic_validation':{
   'artifact_sha256':sha(HERE/'CROSS_PROVIDER_SEMANTIC_VALIDATION_V1.json'),
   'identity_matched_fixtures':val['join_counts']['matched_identity_only'],
   'goals_exact_rate':val['goals']['exact_rate'],
   'corners_exact_rate':val['fields']['corners']['exact_rate'],
   'corners_mean_signed_difference':val['fields']['corners']['mean_signed_difference'],
   'shots_exact_rate':val['fields']['shots']['exact_rate'],
   'sot_exact_rate':val['fields']['sot']['exact_rate'],
   'possession_exact_rate':val['fields']['possession']['exact_rate'],
   'fouls_exact_rate':val['fields']['fouls']['exact_rate'],
   'yellow_exact_rate':val['fields']['yellow']['exact_rate'],
   'xg_exact_rate':val['fields']['xg']['exact_rate']},
  'governance':{
   'implicit_provider_blending':False,
   'permitted_auxiliary_fields':['goals_home','goals_away','corners_home','corners_away'],
   'forbidden_harmonization':['shots','shots_on_target','possession','fouls','yellow_cards','xg','odds','potential'],
   'required_next_test':'expanded-history challenger must be evaluated on TheStatsAPI-only chronological OOS/calibration before any promotion',
   'layer4_frozen_model_unchanged':True,'champion_unchanged':True}}
 obj['manifest_sha256']=jsha(obj)
 (HERE/'QFE_V2_HISTORICAL_CANDIDATE_V1.json').write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
 lines=[
 '# QFE V2 Historical Expansion — Cached Corpus Build Report','',
 'Status: **FROZEN RESEARCH CANDIDATE — NOT MODEL INPUT**','',
 '## Result','',
 f"- Network/API calls used: **0**",
 f"- TheStatsAPI core before protected cutoff: **{len(core):,}** fixtures; **{core_corners:,}** corner-complete.",
 f"- Cached FootyStats auxiliary extension: **{ext['row_count']:,}** fixtures; **{ext['corner_complete_rows']:,}** corner-complete.",
 f"- Candidate combined scope: **{len(core)+ext['row_count']:,}** fixtures across **18** competitions.",
 '- Missing from the 20-competition target: **EFL League One and EFL League Two**.',
 '- The 317 protected V2 outcomes were not opened or consumed.',
 '',
 '## Cross-provider semantic validation','',
 f"- Identity-only matched fixtures: **{val['join_counts']['matched_identity_only']:,}**.",
 f"- Regulation goals exact agreement: **{100*val['goals']['exact_rate']:.3f}%**.",
 f"- Corner side-count exact agreement: **{100*val['fields']['corners']['exact_rate']:.3f}%**; mean signed FS−TSA difference **{val['fields']['corners']['mean_signed_difference']:.4f}**.",
 f"- Shots exact agreement: **{100*val['fields']['shots']['exact_rate']:.2f}%**.",
 f"- SoT exact agreement: **{100*val['fields']['sot']['exact_rate']:.2f}%**.",
 f"- Possession exact agreement: **{100*val['fields']['possession']['exact_rate']:.2f}%**.",
 f"- Fouls exact agreement: **{100*val['fields']['fouls']['exact_rate']:.2f}%**.",
 f"- Yellow cards exact agreement: **{100*val['fields']['yellow']['exact_rate']:.2f}%**.",
 f"- xG exact agreement: **{100*val['fields']['xg']['exact_rate']:.2f}%**.",
 '',
 '## Governance decision','',
 '- **No implicit provider blending.** Cached FootyStats remains a separately tagged auxiliary provider.',
 '- Only goals and home/away corner counts are admitted to the auxiliary count-extension artifact.',
 '- Shots, SoT, possession, fouls, cards, xG, odds and provider potential fields are excluded from the normalized extension.',
 '- The expanded corpus may challenge the frozen Layer 4 model only through a new versioned experiment.',
 '- Promotion requires chronological TheStatsAPI-only OOS/calibration evidence; larger historical N alone is not evidence of improvement.',
 '',
 '## API-spend decision','',
 '- The planned 150–250-call semantic panel is **not needed**: the cache produced 2,413 identity-matched validation fixtures at zero cost.',
 '- League One/League Two backfill is deferred. One complete season of each would be roughly 1,104 per-match stats calls and is not justified before testing whether the 13,885-fixture candidate improves OOS scoring.',
 '',
 f"Manifest SHA-256: {obj['manifest_sha256']}",
 ]
 (HERE/'BUILD_REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps(obj,indent=2,sort_keys=True))
if __name__=='__main__': main()
