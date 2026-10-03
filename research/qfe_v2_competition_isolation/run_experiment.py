from __future__ import annotations
import gzip,hashlib,json
from dataclasses import replace
from pathlib import Path
import numpy as np
from scipy.stats import poisson

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json,sha256_json
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec
from src.research.evaluation.chronology import PROTECTED_START_TS
from src.research.layer4.calibrators import WeightedIsotonic,PlattGlobal,RidgeContextPlatt
from src.research.models.dynamic_count_strength import CORNERS_TARGET,GOALS_TARGET,DynamicCountConfig,DynamicHierarchicalCountBaseline
from src.research.models.structured_distributions import binary_log_loss,nb2_cdf,nb2_total_under_probability_from_sides

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
FOUND=Path('/home/ubuntu/data/thestatsapi/championship')
EXT=ROOT/'research/qfe_v2_historical_expansion/CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz'
SPEC=HERE/'SPEC_V1.json'
STRUCT=ROOT/'evidence/layer3/STRUCTURED_DEVELOPMENT_OOF.json'
SIM=ROOT/'evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json'
L31=ROOT/'evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_ROWS.jsonl.gz'
RAW_SUM=ROOT/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_V1.json'
RAW_ROWS=ROOT/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_ROWS_V1.jsonl.gz'
CAL_ROWS=ROOT/'evidence/layer4/QFE_LAYER4_CALIBRATED_ROWS_V1.jsonl.gz'
FREEZE=ROOT/'evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V1.json'
ENSEMBLE=ROOT/'evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V1.json'
HIST=ROOT/'research/qfe_v2_historical_expansion/QFE_V2_HISTORICAL_CANDIDATE_V1.json'
OUT=HERE/'RESULT_V1.json'
OUT_MD=HERE/'RESULT_V1.md'
PAIRS=HERE/'CALIBRATION_PAIRED_ROWS_V1.jsonl.gz'
GRID=(4.0,10.0,20.0,40.0)
SEED=20261003
REPS=4000
EPS=1e-12

def rj(p): return json.loads(Path(p).read_text())
def gzrows(p): return [json.loads(x) for x in gzip.decompress(Path(p).read_bytes()).decode().splitlines() if x.strip()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pois(mu,line): return float(poisson.sf(int(line),mu))
def nb(mu,line,a): return float(1-nb2_cdf(int(line),mu,a))
def aux(r):
    hg,ag,ch,ca=r['goals_home'],r['goals_away'],r['corners_home'],r['corners_away']
    return ResearchMatch(
      match_id=int(r['provider_match_id']),date_unix=int(r['kickoff_unix']),league_id=0,
      season=str(r.get('season_label') or r['footystats_season_id']),
      home_team=str(r['home_name']),away_team=str(r['away_name']),
      source_provider='FOOTYSTATS_CACHED',source_match_ref=str(r['provider_match_id']),
      competition_ref=str(r['deployment_competition_ref']),
      season_ref='FOOTYSTATS_CACHED:'+str(r['footystats_season_id']),
      home_team_ref='FOOTYSTATS_CACHED:team:'+str(r['home_provider_team_id']),
      away_team_ref='FOOTYSTATS_CACHED:team:'+str(r['away_provider_team_id']),
      home_goals=None if hg is None else int(hg),away_goals=None if ag is None else int(ag),
      total_goals=None if hg is None or ag is None else int(hg)+int(ag),
      corners_home=None if ch is None else int(ch),corners_away=None if ca is None else int(ca),
      total_corners=None if ch is None or ca is None else int(ch)+int(ca))
def dmap(ms,target,cfg):
    return {f.fixture_key:f for f in DynamicHierarchicalCountBaseline(target,cfg).walk_forward(ms)}

def multi_dmap(ms,target,base_cfg,weights):
    # Prior weight changes posterior forecasts only. State updates depend on
    # observed counts + half-life, which is frozen across this grid. Forecast
    # all weights from the exact same pre-fixture state before one common update.
    model=DynamicHierarchicalCountBaseline(target,base_cfg)
    out={w:{} for w in weights}
    ordered=sorted(ms,key=lambda m:(m.date_unix,m.stable_fixture_key or ''))
    batch=[]; kickoff=None
    def flush(rows,ts):
        if not rows:return
        for w in weights:
            model.config=replace(base_cfg,competition_prior_weight=w)
            for m in rows:
                f=model.forecast(m); out[w][f.fixture_key]=f
        model.config=base_cfg
        for m in rows:model._update_match(m)
        model._last_processed_kickoff=int(ts)
    for m in ordered:
        if kickoff is None:kickoff=m.date_unix
        if m.date_unix!=kickoff:
            flush(batch,kickoff); batch=[]; kickoff=m.date_unix
        batch.append(m)
    flush(batch,kickoff)
    model.config=base_cfg
    return out

def wm(rows,pkey):
    if not rows:
        return {'n':0,'fixtures':0,'log_loss':None,'brier':None}
    w=np.asarray([float(r['weight']) for r in rows])
    p=np.asarray([float(r[pkey]) for r in rows])
    y=np.asarray([1. if r['y'] else 0. for r in rows])
    p=np.clip(p,EPS,1-EPS)
    ll=-(y*np.log(p)+(1-y)*np.log1p(-p))
    br=(p-y)**2
    return {'n':len(rows),'fixtures':len({r['fixture'] for r in rows}),
            'log_loss':float(np.average(ll,weights=w)),
            'brier':float(np.average(br,weights=w))}
def boot(rows,refkey,chalkey):
    blocks={}
    for r in rows:
        y=bool(r['y'])
        w=float(r['weight'])
        rl=binary_log_loss(float(r[refkey]),y)
        cl=binary_log_loss(float(r[chalkey]),y)
        b=int(r['ts'])//604800
        a=blocks.setdefault(b,[0.,0.])
        a[0]+=w*(rl-cl)
        a[1]+=w
    vals=list(blocks.values())
    point=sum(x[0] for x in vals)/sum(x[1] for x in vals)
    rng=np.random.default_rng(SEED)
    z=[]
    for _ in range(REPS):
        idx=rng.integers(0,len(vals),size=len(vals))
        z.append(sum(vals[i][0] for i in idx)/sum(vals[i][1] for i in idx))
    a=np.asarray(z)
    return {'mean_improvement':float(point),
            'ci_low':float(np.quantile(a,.025)),
            'ci_high':float(np.quantile(a,.975)),
            'bootstrap_probability_positive':float(np.mean(a>0)),
            'n_time_blocks':len(vals),'replicates':REPS,'seed':SEED}
def choose(scores,ref):
    passing=[(w,m) for w,m in scores.items() if m['brier']<=ref['brier']]
    if not passing:
        return None
    passing.sort(key=lambda x:(x[1]['log_loss'],-x[0]))
    return passing[0][0]

def fit_cal(method,rows):
    p=[r['challenger_raw'] for r in rows]
    y=[r['y'] for r in rows]
    w=[r['weight'] for r in rows]
    if method=='ISOTONIC_GLOBAL':
        return WeightedIsotonic.fit(p,y,w)
    if method=='PLATT_GLOBAL':
        return PlattGlobal.fit(p,y,w,1e-6)
    if method=='PLATT_ROLE_COMP_RIDGE':
        return RidgeContextPlatt.fit(
            p,y,w,[r.get('role') for r in rows],
            [r['competition'] for r in rows],1.0,1e-6,False)
    raise ValueError(method)

def main():
    spec,st,si,rawsum,freeze,en,hist=map(
        rj,[SPEC,STRUCT,SIM,RAW_SUM,FREEZE,ENSEMBLE,HIST])
    if freeze['model_freeze_hash']!=spec['reference']['model_freeze_hash']:
        raise ValueError('reference hash drift')
    corpus=build_multiseason_pit_corpus(
        base_dir=FOUND,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6*3600))
    tsa=tuple(m for m in corpus.matches if m.date_unix<PROTECTED_START_TS)
    ax=tuple(aux(r) for r in gzrows(EXT))
    merged=tuple(sorted(tsa+ax,key=lambda m:(m.date_unix,m.stable_fixture_key or '')))
    if any(m.date_unix>=PROTECTED_START_TS for m in merged):
        raise ValueError('protected leak')
    gbase=DynamicCountConfig(**st['goal_dynamic_config'])
    cbase=DynamicCountConfig(**st['corner_dynamic_config'])
    refg=dmap(tsa,GOALS_TARGET,gbase)
    refc=dmap(tsa,CORNERS_TARGET,cbase)
    gmaps=multi_dmap(merged,GOALS_TARGET,gbase,GRID)
    cmaps=multi_dmap(merged,CORNERS_TARGET,cbase,GRID)
    gw=float(en['goals']['selected_weight'])
    cw=float(en['corners']['selected_weight'])

    simdev=[r for r in si['rows'] if r['target']=='goals']
    devg=[]
    for r in simdev:
        k=r['fixture_key']; sm=float(r['expected_total'])
        line=float(r['line']); y=int(r['observed_total'])>line
        row={'fixture':k,'ts':int(r['kickoff_ts']),
             'fold':r['fold_id'],'competition':r['competition_ref'],
             'weight':1.0,'y':y}
        row['reference']=pois((1-gw)*refg[k].lambda_total+gw*sm,line)
        for w in GRID:
            row[f'w{int(w)}']=pois((1-gw)*gmaps[w][k].lambda_total+gw*sm,line)
        devg.append(row)

    l31=gzrows(L31)
    keyed={}
    for r in l31:
        key=(r['fixture_key'],r['market_scope'],r.get('role'),float(r['line']))
        keyed.setdefault(key,{})[r['candidate']]=r
    devc=[]
    for (k,scope,role,line),pair in keyed.items():
        if set(pair)!={'dynamic_poisson','dynamic_side_nb2'}:
            continue
        a=pair['dynamic_poisson']; b=pair['dynamic_side_nb2']
        alpha=float(b['alpha']); y=bool(a['outcome_over'])
        wt=1/12 if scope=='SIDE' else 1/6
        row={'fixture':k,'ts':int(a['kickoff_ts']),
             'fold':a['fold_id'],'competition':a['competition_ref'],
             'scope':scope,'role':None if role is None else str(role).upper(),
             'line':line,'weight':wt,'y':y}
        def prob(f):
            if scope=='SIDE':
                mu=f.lambda_home if role=='home' else f.lambda_away
                return (1-cw)*pois(mu,line)+cw*nb(mu,line,alpha)
            p0=pois(f.lambda_total,line)
            p1=1-nb2_total_under_probability_from_sides(
                line,f.lambda_home,f.lambda_away,alpha)
            return (1-cw)*p0+cw*p1
        row['reference']=prob(refc[k])
        for w in GRID:
            row[f'w{int(w)}']=prob(cmaps[w][k])
        devc.append(row)

    def dev_select(rows):
        tune=[r for r in rows if r['fold'] in {'D1','D2','D3'}]
        d4=[r for r in rows if r['fold']=='D4']
        ref=wm(tune,'reference')
        scores={w:wm(tune,f'w{int(w)}') for w in GRID}
        selected=choose(scores,ref)
        d4out=None
        if selected is not None:
            d4ref=wm(d4,'reference')
            d4chal=wm(d4,f'w{int(selected)}')
            tmp=[{**r,'selected':r[f'w{int(selected)}']} for r in d4]
            bi=boot(tmp,'reference','selected')
            d4out={
              'reference':d4ref,'challenger':d4chal,
              'paired_log_loss':bi,
              'confirmed':(
                d4chal['log_loss']<d4ref['log_loss']
                and d4chal['brier']<=d4ref['brier']
                and bi['mean_improvement']>0)}
        return {
          'tune_reference':ref,
          'tune_candidates':{str(k):v for k,v in scores.items()},
          'selected_weight':selected,'d4':d4out}
    gs=dev_select(devg)
    cs=dev_select(devc)

    rawrows=gzrows(RAW_ROWS)
    frozen_cal=gzrows(CAL_ROWS)
    fcal={
      (r['fixture_key'],r['group'],r.get('role'),float(r['line'])):r
      for r in frozen_cal}
    alpha=float(rawsum['corners_common_alpha'])
    pairs=[]
    for r in rawrows:
        k,g,line,role=(
          r['fixture_key'],r['group'],float(r['line']),r.get('role'))
        sel=gs['selected_weight'] if g=='GOALS_TOTAL' else cs['selected_weight']
        if sel is None:
            continue
        if g=='GOALS_TOTAL':
            sm=(float(r['expected_count'])
                -(1-gw)*refg[k].lambda_total)/gw
            cp=pois((1-gw)*gmaps[sel][k].lambda_total+gw*sm,line)
        elif g=='CORNERS_SIDE':
            f=cmaps[sel][k]
            mu=f.lambda_home if role=='HOME' else f.lambda_away
            cp=(1-cw)*pois(mu,line)+cw*nb(mu,line,alpha)
        else:
            f=cmaps[sel][k]
            cp=(1-cw)*pois(f.lambda_total,line)+cw*(
              1-nb2_total_under_probability_from_sides(
                line,f.lambda_home,f.lambda_away,alpha))
        pairs.append({
          'fixture':k,'ts':int(r['kickoff_ts']),
          'phase':r['phase'],'competition':r['competition_ref'],
          'group':g,'role':role,'line':line,
          'weight':float(r['sample_weight']),
          'y':bool(r['outcome_over']),
          'reference_raw':float(r['raw_probability']),
          'challenger_raw':float(cp),
          'reference_calibrated':float(
            fcal[(k,g,role,line)]['p_model'])})

    methods={
      'GOALS_TOTAL':'ISOTONIC_GLOBAL',
      'CORNERS_SIDE':'PLATT_GLOBAL',
      'CORNERS_TOTAL':'PLATT_ROLE_COMP_RIDGE'}
    cals={}
    for g,meth in methods.items():
        fit=[r for r in pairs
             if r['group']==g and r['phase']=='CALIBRATION_FIT']
        if fit:
            cals[g]=fit_cal(meth,fit)
    for r in pairs:
        cal=cals[r['group']]
        r['challenger_calibrated']=float(
          cal.transform(
            r['challenger_raw'],
            role=r.get('role'),
            competition_ref=r['competition']))

    def cal_summary(group=None,role=None,corners=False):
        rr=[r for r in pairs
            if r['phase']=='CALIBRATION_SELECT'
            and (group is None or r['group']==group)
            and (role is None or r.get('role')==role)]
        if corners:
            rr=[r for r in rr
                if r['group'] in {'CORNERS_SIDE','CORNERS_TOTAL'}]
        out={}
        for k in [
          'reference_raw','challenger_raw',
          'reference_calibrated','challenger_calibrated']:
            out[k]=wm([{**x,'p':x[k]} for x in rr],'p')
        tmp=[
          {**x,'ref':x['reference_raw'],'chal':x['challenger_raw']}
          for x in rr]
        out['raw_paired_log_loss']=boot(tmp,'ref','chal') if tmp else None
        return out

    cal={
      'GOALS_TOTAL':cal_summary('GOALS_TOTAL'),
      'CORNERS_SIDE':cal_summary('CORNERS_SIDE'),
      'CORNERS_TOTAL':cal_summary('CORNERS_TOTAL'),
      'CORNERS_COMPOSITE':cal_summary(corners=True)}
    roles={
      z:cal_summary('CORNERS_SIDE',z)
      for z in ['HOME','AWAY']}

    def gate(summ,d4,extra_roles=False):
        valid=(
          summ['challenger_raw']['log_loss'] is not None
          and summ['reference_raw']['log_loss'] is not None
          and summ['challenger_calibrated']['log_loss'] is not None
          and summ['reference_calibrated']['log_loss'] is not None
          and summ['raw_paired_log_loss'] is not None)
        c=[
          bool(d4 and d4['confirmed']),
          bool(valid and summ['challenger_raw']['log_loss']<summ['reference_raw']['log_loss']),
          bool(valid and summ['challenger_raw']['brier']<=summ['reference_raw']['brier']),
          bool(valid and summ['challenger_calibrated']['log_loss']<summ['reference_calibrated']['log_loss']),
          bool(valid and summ['challenger_calibrated']['brier']<=summ['reference_calibrated']['brier']),
          bool(valid and summ['raw_paired_log_loss']['ci_low']>0)]
        if extra_roles:
            c += [
              bool(roles['HOME']['challenger_raw']['log_loss'] is not None and roles['HOME']['reference_raw']['log_loss'] is not None and
                roles['HOME']['challenger_raw']['log_loss']<=roles['HOME']['reference_raw']['log_loss']),
              bool(roles['AWAY']['challenger_raw']['log_loss'] is not None and roles['AWAY']['reference_raw']['log_loss'] is not None and
                roles['AWAY']['challenger_raw']['log_loss']<=roles['AWAY']['reference_raw']['log_loss'])]
        return {
          'criteria':c,'all_pass':all(c),
          'status':(
            'ADVANCE_TO_SEPARATE_PROTECTED_EVALUATION'
            if all(c) else 'DO_NOT_ADVANCE')}
    gates={
      'goals':gate(cal['GOALS_TOTAL'],gs['d4']),
      'corners':gate(cal['CORNERS_COMPOSITE'],cs['d4'],True),
      'promotion_authorized':False}

    raw=''.join(canonical_json(r)+'\n' for r in pairs).encode()
    gz=gzip.compress(raw,compresslevel=9,mtime=0)
    PAIRS.write_bytes(gz)
    result={
      'version':'QFE_V2_COMPETITION_ISOLATION_RESULT_V1',
      'scientific_status':'PREREGISTERED_MECHANISM_TEST_PROTECTED_UNOPENED',
      'spec_sha256':sha(SPEC),
      'bindings':{
        'reference_freeze_hash':freeze['model_freeze_hash'],
        'historical_manifest_hash':hist['manifest_sha256'],
        'extension_sha256':sha(EXT)},
      'boundaries':{
        'network_calls':0,'market_odds_used':False,
        'protected_outcomes_scored':0,'champion_changed':False,
        'layer4_reference_changed':False},
      'history':{
        'tsa_matches':len(tsa),'auxiliary_matches':len(ax),
        'merged_matches':len(merged)},
      'goals_selection':gs,'corners_selection':cs,
      'calibration_select':cal,'corner_role_guards':roles,
      'challenger_calibrators':{
        g:cals[g].to_spec() for g in cals},
      'advance_gate':gates,
      'paired_rows':{
        'rows':len(pairs),
        'fixtures':len({r['fixture'] for r in pairs}),
        'sha256':hashlib.sha256(gz).hexdigest(),
        'content_hash':sha256_json(pairs)}}
    result['result_hash']=sha256_json(result)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    lines=[
      '# QFE V2 Competition Isolation V1','',
      'Result hash: '+result['result_hash'],'',
      '> Mechanism test only. Protected outcomes remain unopened. No direct promotion authorized.','',
      '## Selection',
      '- Goals selected competition prior weight: **'+str(gs['selected_weight'])+'**',
      '- Corners selected competition prior weight: **'+str(cs['selected_weight'])+'**',
      '- Goals D4 confirmed: **'+str(None if gs['d4'] is None else gs['d4']['confirmed'])+'**',
      '- Corners D4 confirmed: **'+str(None if cs['d4'] is None else cs['d4']['confirmed'])+'**','',
      '## CALIBRATION_SELECT']
    for g in ['GOALS_TOTAL','CORNERS_COMPOSITE']:
        x=cal[g]
        if x['challenger_raw']['log_loss'] is None:
            lines += ['### '+g,'- NO_CANDIDATE passed the preregistered D1-D3 Brier guard.','']
        else:
            lines += [
              '### '+g,
              '- RAW LL: %.6f -> %.6f'%(x['reference_raw']['log_loss'],x['challenger_raw']['log_loss']),
              '- RAW Brier: %.6f -> %.6f'%(x['reference_raw']['brier'],x['challenger_raw']['brier']),
              '- Calibrated LL: %.6f -> %.6f'%(x['reference_calibrated']['log_loss'],x['challenger_calibrated']['log_loss']),
              '- Calibrated Brier: %.6f -> %.6f'%(x['reference_calibrated']['brier'],x['challenger_calibrated']['brier']),
              '- RAW LL improvement 95%% CI: [%.6g, %.6g]'%(x['raw_paired_log_loss']['ci_low'],x['raw_paired_log_loss']['ci_high']),'']
    lines += [
      '## Gate',
      '- Goals: **'+gates['goals']['status']+'** ('+
        str(sum(gates['goals']['criteria']))+'/'+
        str(len(gates['goals']['criteria']))+')',
      '- Corners: **'+gates['corners']['status']+'** ('+
        str(sum(gates['corners']['criteria']))+'/'+
        str(len(gates['corners']['criteria']))+')']
    OUT_MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({
      'result_hash':result['result_hash'],
      'goals_selection':gs,
      'corners_selection':cs,
      'calibration_select':cal,
      'roles':roles,
      'gates':gates},indent=2,sort_keys=True))

if __name__=='__main__':
    main()
