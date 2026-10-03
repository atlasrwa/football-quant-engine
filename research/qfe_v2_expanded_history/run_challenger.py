from __future__ import annotations
import gzip,hashlib,json,math
from pathlib import Path
from typing import Any
import numpy as np
from scipy.stats import poisson
from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json,sha256_json
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec
from src.research.evaluation.chronology import PROTECTED_START_TS
from src.research.evaluation.similar_oof import SimilarContextConfig
from src.research.layer4.calibrators import calibrator_from_spec
from src.research.layer4.raw_calibration import _similar_goal_predictions
from src.research.models.dynamic_count_strength import CORNERS_TARGET,GOALS_TARGET,DynamicCountConfig,DynamicHierarchicalCountBaseline
from src.research.models.structured_distributions import binary_log_loss,brier_score,nb2_cdf,nb2_total_under_probability_from_sides

ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
FOUNDATION=Path('/home/ubuntu/data/thestatsapi/championship')
EXT=ROOT/'research/qfe_v2_historical_expansion/CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz'
HIST=ROOT/'research/qfe_v2_historical_expansion/QFE_V2_HISTORICAL_CANDIDATE_V1.json'
SPEC=HERE/'SPEC_V1.json'
RAW_SUM=ROOT/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_V1.json'
RAW_ROWS=ROOT/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_ROWS_V1.jsonl.gz'
CAL_ROWS=ROOT/'evidence/layer4/QFE_LAYER4_CALIBRATED_ROWS_V1.jsonl.gz'
FREEZE=ROOT/'evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V1.json'
ENSEMBLE=ROOT/'evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V1.json'
STRUCT=ROOT/'evidence/layer3/STRUCTURED_DEVELOPMENT_OOF.json'
SIM=ROOT/'evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json'
OUT=HERE/'RESULT_V1.json'; OUT_ROWS=HERE/'PAIRED_ROWS_V1.jsonl.gz'; OUT_MD=HERE/'RESULT_V1.md'
SEED=20261002; REPS=4000; EPS=1e-12

def readj(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rowsgz(p): return [json.loads(x) for x in gzip.decompress(Path(p).read_bytes()).decode().splitlines() if x.strip()]
def aux(r):
    hg,ag,ch,ca=r['goals_home'],r['goals_away'],r['corners_home'],r['corners_away']
    return ResearchMatch(match_id=int(r['provider_match_id']),date_unix=int(r['kickoff_unix']),league_id=0,
      season=str(r.get('season_label') or r['footystats_season_id']),home_team=str(r['home_name']),away_team=str(r['away_name']),
      source_provider='FOOTYSTATS_CACHED',source_match_ref=str(r['provider_match_id']),competition_ref=str(r['deployment_competition_ref']),
      season_ref='FOOTYSTATS_CACHED:'+str(r['footystats_season_id']),
      home_team_ref='FOOTYSTATS_CACHED:team:'+str(r['home_provider_team_id']),
      away_team_ref='FOOTYSTATS_CACHED:team:'+str(r['away_provider_team_id']),
      home_goals=None if hg is None else int(hg),away_goals=None if ag is None else int(ag),
      total_goals=None if hg is None or ag is None else int(hg)+int(ag),
      corners_home=None if ch is None else int(ch),corners_away=None if ca is None else int(ca),
      total_corners=None if ch is None or ca is None else int(ch)+int(ca))
def dmap(ms,target,cfg):
    return {f.fixture_key:f for f in DynamicHierarchicalCountBaseline(target,cfg).walk_forward(ms)}
def pois(mu,line): return float(poisson.sf(int(line),mu))
def nb(mu,line,a): return float(1-nb2_cdf(int(line),mu,a))
def loss(p,y): return binary_log_loss(p,y),brier_score(p,y)

def metrics(rr,prefix):
    if not rr: return {'event_cells':0,'unique_fixtures':0,'log_loss':None,'brier':None,'ece_10':None}
    w=np.asarray([float(r['sample_weight']) for r in rr]); p=np.asarray([float(r[prefix+'_probability']) for r in rr]); y=np.asarray([1. if r['outcome_over'] else 0. for r in rr])
    p=np.clip(p,EPS,1-EPS); ll=-(y*np.log(p)+(1-y)*np.log1p(-p)); br=(p-y)**2; den=float(w.sum()); e=0.
    for i in range(10):
        lo=i/10; hi=(i+1)/10; m=(p>=lo)&(p<(hi if i<9 else hi+1e-12))
        if m.any():
            bw=float(w[m].sum()); e+=(bw/den)*abs(float(np.average(p[m],weights=w[m]))-float(np.average(y[m],weights=w[m])))
    return {'event_cells':len(rr),'unique_fixtures':len({r['fixture_key'] for r in rr}),'log_loss':float(np.average(ll,weights=w)),'brier':float(np.average(br,weights=w)),'ece_10':float(e)}

def boot(rr,refp,chalp,kind):
    blocks={}
    for r in rr:
        w=float(r['sample_weight']); y=bool(r['outcome_over']); rp=float(r[refp+'_probability']); cp=float(r[chalp+'_probability'])
        if kind=='log_loss': rv,_=loss(rp,y); cv,_=loss(cp,y)
        else: _,rv=loss(rp,y); _,cv=loss(cp,y)
        b=int(r['kickoff_ts'])//604800; a=blocks.setdefault(b,[0.,0.]); a[0]+=w*(rv-cv); a[1]+=w
    vals=list(blocks.values()); point=sum(x[0] for x in vals)/sum(x[1] for x in vals); rng=np.random.default_rng(SEED); z=[]
    for _ in range(REPS):
        idx=rng.integers(0,len(vals),size=len(vals)); num=sum(vals[i][0] for i in idx); den=sum(vals[i][1] for i in idx); z.append(num/den)
    z=np.asarray(z)
    return {'metric':kind,'mean_improvement':float(point),'ci_low':float(np.quantile(z,.025)),'ci_high':float(np.quantile(z,.975)),
      'bootstrap_probability_positive':float(np.mean(z>0)),'bootstrap_replicates':REPS,'n_time_blocks':len(vals),'seed':SEED}

def summary(rows,phase,group=None,role=None,corners=False):
    rr=[r for r in rows if r['phase']==phase and (group is None or r['group']==group) and (role is None or r.get('role')==role)]
    if corners: rr=[r for r in rr if r['group'] in {'CORNERS_SIDE','CORNERS_TOTAL'}]
    return {'reference_raw':metrics(rr,'reference_raw'),'challenger_raw':metrics(rr,'challenger_raw'),
      'reference_calibrated':metrics(rr,'reference_calibrated'),'challenger_calibrated':metrics(rr,'challenger_calibrated'),
      'raw_paired_log_loss':boot(rr,'reference_raw','challenger_raw','log_loss'),'raw_paired_brier':boot(rr,'reference_raw','challenger_raw','brier'),
      'calibrated_paired_log_loss':boot(rr,'reference_calibrated','challenger_calibrated','log_loss'),
      'calibrated_paired_brier':boot(rr,'reference_calibrated','challenger_calibrated','brier')}

def bycomp(rows,phase,group):
    out={}
    for c in sorted({r['competition_ref'] for r in rows if r['phase']==phase and r['group']==group}):
        rr=[r for r in rows if r['phase']==phase and r['group']==group and r['competition_ref']==c]
        out[c]={'reference_raw':metrics(rr,'reference_raw'),'challenger_raw':metrics(rr,'challenger_raw')}
    return out

def decision(result):
    s=result['primary_calibration_select']; g=s['groups']['GOALS_TOTAL']; c=s['corner_composite']; roles=s['corner_role_guards']
    gc=[g['challenger_raw']['log_loss']<g['reference_raw']['log_loss'],g['challenger_raw']['brier']<=g['reference_raw']['brier'],
        g['challenger_calibrated']['log_loss']<g['reference_calibrated']['log_loss'],g['challenger_calibrated']['brier']<=g['reference_calibrated']['brier'],
        g['raw_paired_log_loss']['ci_low']>0]
    cc=[c['challenger_raw']['log_loss']<c['reference_raw']['log_loss'],c['challenger_raw']['brier']<=c['reference_raw']['brier'],
        c['challenger_calibrated']['log_loss']<c['reference_calibrated']['log_loss'],c['challenger_calibrated']['brier']<=c['reference_calibrated']['brier'],
        c['raw_paired_log_loss']['ci_low']>0,
        roles['HOME']['challenger_raw']['log_loss']<=roles['HOME']['reference_raw']['log_loss'],
        roles['AWAY']['challenger_raw']['log_loss']<=roles['AWAY']['reference_raw']['log_loss']]
    return {'goals':{'criteria':gc,'all_pass':all(gc),'status':'ADVANCE_TO_SEPARATE_PROTECTED_EVALUATION' if all(gc) else 'DO_NOT_ADVANCE'},
      'corners':{'criteria':cc,'all_pass':all(cc),'status':'ADVANCE_TO_SEPARATE_PROTECTED_EVALUATION' if all(cc) else 'DO_NOT_ADVANCE'},'promotion_authorized':False}

def main():
    sp,hist,fr,en,st,si,rs=map(readj,[SPEC,HIST,FREEZE,ENSEMBLE,STRUCT,SIM,RAW_SUM])
    rr=rowsgz(RAW_ROWS); cr=rowsgz(CAL_ROWS)
    if fr['model_freeze_hash']!=sp['reference_model_freeze_hash']: raise ValueError('freeze mismatch')
    if any(int(r['kickoff_ts'])>=PROTECTED_START_TS for r in rr): raise ValueError('protected reference row')
    corpus=build_multiseason_pit_corpus(base_dir=FOUNDATION,pit_spec=PITDatasetSpec(decision_horizon_seconds=6*3600))
    tsa=tuple(m for m in corpus.matches if m.date_unix<PROTECTED_START_TS); ax=tuple(aux(r) for r in rowsgz(EXT))
    merged=tuple(sorted(tsa+ax,key=lambda m:(m.date_unix,m.stable_fixture_key or '')))
    if len({m.stable_fixture_key for m in merged})!=len(merged): raise ValueError('duplicate merged identity')
    gc=DynamicCountConfig(**st['goal_dynamic_config']); cc=DynamicCountConfig(**st['corner_dynamic_config'])
    rg=dmap(tsa,GOALS_TARGET,gc); rc=dmap(tsa,CORNERS_TARGET,cc); cg=dmap(merged,GOALS_TARGET,gc); ccv=dmap(merged,CORNERS_TARGET,cc)
    sim=_similar_goal_predictions(corpus,SimilarContextConfig(**si['config'])); gw=float(en['goals']['selected_weight']); cw=float(en['corners']['selected_weight']); alpha=float(rs['corners_common_alpha'])
    specs={'GOALS_TOTAL':fr['goals_total_2_5']['calibrator_spec'],'CORNERS_SIDE':fr['corners']['side']['calibrator_spec'],'CORNERS_TOTAL':fr['corners']['total']['calibrator_spec']}
    cals={k:calibrator_from_spec(v) for k,v in specs.items()}; crm={(r['fixture_key'],r['group'],r.get('role'),float(r['line'])):r for r in cr}
    paired=[]; mx=0.; mxc=0.
    for r in rr:
        k,g,line,role=r['fixture_key'],r['group'],float(r['line']),r.get('role')
        if g=='GOALS_TOTAL':
            sm=sim[k][0]; a=rg[k]; b=cg[k]; p0=pois(a.lambda_total,line); p1=pois(sm,line); rp=pois((1-gw)*a.lambda_total+gw*sm,line); cp=pois((1-gw)*b.lambda_total+gw*sm,line); exp=(1-gw)*b.lambda_total+gw*sm
        elif g=='CORNERS_SIDE':
            a,b=rc[k],ccv[k]; am=a.lambda_home if role=='HOME' else a.lambda_away; bm=b.lambda_home if role=='HOME' else b.lambda_away
            p0=pois(am,line); p1=nb(am,line,alpha); rp=(1-cw)*p0+cw*p1; q0=pois(bm,line); q1=nb(bm,line,alpha); cp=(1-cw)*q0+cw*q1; exp=bm
        else:
            a,b=rc[k],ccv[k]; p0=pois(a.lambda_total,line); p1=1-nb2_total_under_probability_from_sides(line,a.lambda_home,a.lambda_away,alpha); rp=(1-cw)*p0+cw*p1
            q0=pois(b.lambda_total,line); q1=1-nb2_total_under_probability_from_sides(line,b.lambda_home,b.lambda_away,alpha); cp=(1-cw)*q0+cw*q1; exp=b.lambda_total
        mx=max(mx,abs(p0-float(r['component_0_probability'])),abs(p1-float(r['component_1_probability'])),abs(rp-float(r['raw_probability'])))
        cal=cals[g]; rcal=cal.transform(rp,role=role,competition_ref=r['competition_ref']); ccal=cal.transform(cp,role=role,competition_ref=r['competition_ref'])
        mxc=max(mxc,abs(rcal-float(crm[(k,g,role,line)]['p_model'])))
        paired.append({'fixture_key':k,'kickoff_ts':int(r['kickoff_ts']),'phase':r['phase'],'competition_ref':r['competition_ref'],'group':g,'role':role,'line':line,
          'outcome_over':bool(r['outcome_over']),'sample_weight':float(r['sample_weight']),'reference_raw_probability':float(rp),'challenger_raw_probability':float(cp),
          'reference_calibrated_probability':float(rcal),'challenger_calibrated_probability':float(ccal),'reference_expected_count':float(r['expected_count']),
          'challenger_expected_count':float(exp),'reference_dynamic_effective_support':float(r['dynamic_effective_team_support']),
          'challenger_dynamic_effective_support':float(cg[k].effective_support if g=='GOALS_TOTAL' else ccv[k].effective_support)})
    if mx>1e-10 or mxc>1e-10: raise ValueError('reference reproduction drift '+str((mx,mxc)))
    seln=len({r['fixture_key'] for r in paired if r['phase']=='CALIBRATION_SELECT'})
    if seln!=int(sp['evaluation']['primary_fixture_count_expected']): raise ValueError('select fixture count drift')
    def phase(name):
        return {'fixture_count':len({r['fixture_key'] for r in paired if r['phase']==name}),
          'groups':{g:summary(paired,name,group=g) for g in ['GOALS_TOTAL','CORNERS_SIDE','CORNERS_TOTAL']},
          'corner_composite':summary(paired,name,corners=True),
          'corner_role_guards':{z:summary(paired,name,group='CORNERS_SIDE',role=z) for z in ['HOME','AWAY']},
          'by_competition':{g:bycomp(paired,name,g) for g in ['GOALS_TOTAL','CORNERS_SIDE','CORNERS_TOTAL']}}
    raw=''.join(canonical_json(r)+'\n' for r in paired).encode(); gz=gzip.compress(raw,compresslevel=9,mtime=0); OUT_ROWS.write_bytes(gz)
    res={'version':'QFE_V2_EXPANDED_HISTORY_CHALLENGER_RESULT_V1','scientific_status':'RETROSPECTIVE_TSA_ONLY_CALIBRATION_SELECT_EVALUATION_PROTECTED_UNOPENED',
      'spec_sha256':sha(SPEC),'bindings':{'reference_model_freeze_hash':fr['model_freeze_hash'],'historical_candidate_manifest_hash':hist['manifest_sha256'],
      'historical_candidate_file_sha256':sha(HIST),'auxiliary_extension_sha256':sha(EXT),'raw_layer4_summary_sha256':sha(RAW_SUM),'raw_layer4_rows_sha256':sha(RAW_ROWS),'calibrated_layer4_rows_sha256':sha(CAL_ROWS)},
      'boundaries':{'network_calls':0,'market_odds_used':False,'protected_outcomes_scored':0,'protected_start_ts':PROTECTED_START_TS,'champion_changed':False,'layer4_reference_changed':False,'llm_numeric_feature':False},
      'history':{'tsa_preprotected_matches':len(tsa),'auxiliary_footystats_matches':len(ax),'merged_preprotected_matches':len(merged),'auxiliary_competitions':len({m.competition_ref for m in ax}),
      'team_identity_cross_provider_mapping':False,'corner_dispersion_alpha_frozen':alpha,'goals_similar_weight_frozen':gw,'corners_nb2_weight_frozen':cw},
      'implementation_verification':{'reference_component_assertions':3*len(rr),'max_reference_component_probability_error':mx,'max_reference_calibration_probability_error':mxc},
      'descriptive_calibration_fit':phase('CALIBRATION_FIT'),'primary_calibration_select':phase('CALIBRATION_SELECT'),
      'paired_rows':{'row_count':len(paired),'unique_fixtures':len({r['fixture_key'] for r in paired}),'sha256':hashlib.sha256(gz).hexdigest(),'content_hash':sha256_json(paired),'path':str(OUT_ROWS.relative_to(ROOT))}}
    res['advance_decision']=decision(res); res['result_hash']=sha256_json(res); OUT.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    s=res['primary_calibration_select']; gd=res['advance_decision']['goals']; cd=res['advance_decision']['corners']; c=s['corner_composite']; g=s['groups']['GOALS_TOTAL']
    OUT_MD.write_text('\n'.join(['# QFE V2 Expanded-History Challenger V1','', 'Result hash: '+res['result_hash'],'',
      '> TSA-only CALIBRATION_SELECT evaluation. Protected outcomes remain unopened. No promotion authorized.','',
      '## Primary results','',
      'Goals raw LL: %.6f -> %.6f'%(g['reference_raw']['log_loss'],g['challenger_raw']['log_loss']),
      'Goals calibrated LL: %.6f -> %.6f'%(g['reference_calibrated']['log_loss'],g['challenger_calibrated']['log_loss']),
      'Goals raw LL paired 95%% CI: [%.6g, %.6g]'%(g['raw_paired_log_loss']['ci_low'],g['raw_paired_log_loss']['ci_high']),
      'Corners composite raw LL: %.6f -> %.6f'%(c['reference_raw']['log_loss'],c['challenger_raw']['log_loss']),
      'Corners composite calibrated LL: %.6f -> %.6f'%(c['reference_calibrated']['log_loss'],c['challenger_calibrated']['log_loss']),
      'Corners raw LL paired 95%% CI: [%.6g, %.6g]'%(c['raw_paired_log_loss']['ci_low'],c['raw_paired_log_loss']['ci_high']),'',
      'Goals gate: '+gd['status']+' (%d/%d)'%(sum(gd['criteria']),len(gd['criteria'])),
      'Corners gate: '+cd['status']+' (%d/%d)'%(sum(cd['criteria']),len(cd['criteria'])),'']))
    print(json.dumps({'result_hash':res['result_hash'],'select_fixtures':s['fixture_count'],'goals_gate':gd,'corners_gate':cd,
      'goals_raw':g['raw_paired_log_loss'],'corners_raw':c['raw_paired_log_loss'],'reproduction':res['implementation_verification']},indent=2,sort_keys=True))
if __name__=='__main__': main()
