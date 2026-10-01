"""Offline, bounded chronological development experiment. Run as a module."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import poisson

from research.evidence_v32.market_audit_v322 import load_snapshots
from src.research.evidence_v32.modeling_v322 import LinearCount, count_scales, side_design
from src.research.evidence_v32.modeling_v323 import build_venue_panel
from src.research.evidence_v32.modeling_v33_corners import build_corner_panel
from src.research.v35_frontier.features import v3_corner_rows
from src.research.v35_frontier.model import export_linear_count
from src.research.v3_pilot.model import predict_corners, InsufficientHistory
from src.research.v3_pilot.market import _bet365
from src.research.v36_calibration.runtime import digest
from src.research.v36_calibration.core import (
    BUFFER, HORIZON, Unsupported, split_stages, prior_corner_rows,
    count_probabilities, fit_affine, apply_affine, fit_sigmoid, apply_sigmoid,
    fit_blend, coherent_blend, assert_coherent, select_quote, summary,
    paired_interval, fit_market, apply_market, temporal_eligibility,
)

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/v36_calibration'
OUT=BASE/'out'
EVIDENCE=ROOT/'research/evidence_v32/out/evidence_v2/evidence.jsonl'
CACHE=Path('/home/ubuntu/data/v3_pilot/provider_cache')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj): Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')


def snapshots():
    out=load_snapshots()
    malformed=0
    for path in sorted((CACHE/'odds').glob('*/*.json')):
        try:
            obs=float(path.name.split('_',1)[0]); payload=json.loads(path.read_text())
            book=_bet365(payload)
            mid=str((payload.get('data') or {}).get('match_id') or '')
            # A stored directory is an index, not proof of payload identity.
            if not book or mid != path.parent.name:
                malformed+=1; continue
        except (ValueError,TypeError,AttributeError,OSError):
            malformed+=1;continue
        out[mid].append({'observed_at':obs,'markets':book.get('markets') or {},
                        'source_path':str(path),'source_sha256':sha(path)})
    return out,malformed


def parent_means(panel,evidence):
    bycomp={c:v3_corner_rows(evidence,c) for c in {r['competition_id'] for r in panel}}
    values={}; abstentions={}
    for row in panel:
        history=prior_corner_rows(bycomp[row['competition_id']],row['cutoff_ts'])
        target={'match_id':row['match_id'],'competition_id':row['competition_id'],
                'ts':row['kickoff_ts'],'home_id':row['home_id'],'away_id':row['away_id']}
        try:
            result=predict_corners(history,history,target)
            values[row['match_id']]=float(result['lambda_total'])
        except InsufficientHistory as ex:
            abstentions[row['match_id']]=str(ex)
    return values,abstentions


def count_diagnostics(means,actual):
    mu=np.asarray(means).sum(axis=1); y=np.asarray(actual).sum(axis=1)
    return {'n':len(y),'mean_expected':float(mu.mean()),'mean_observed':float(y.mean()),
            'mean_residual':float((y-mu).mean()),
            'pearson_residual_second_moment':float(np.mean((y-mu)**2/mu)),
            'note':'Residual diagnostic; not proof of Poisson dispersion misspecification.'}


def experiment_family(family,panel,evidence,boundaries,spec,quotes):
    key='venue' if family=='goals' else 'pressure'
    lines=np.asarray(spec['families'][family],float)
    parent,abstentions=parent_means(panel,evidence) if family=='corners' else ({},{})
    forecasts=[]; artifacts=[]; folds=[]; unavailable=[]
    for fold,edges in enumerate(boundaries):
        stages=split_stages(panel,edges)
        train,cal,stack,test=stages
        support={name:len(stage) for name,stage in zip(spec['stages'],stages)}
        print(f'{family} fold {fold}: {support}',flush=True)
        if any(len(s)<n for s,n in zip(stages,spec['minimum_stage_fixtures'])):
            folds.append({'fold':fold,'status':'UNSUPPORTED','support':support});continue
        ytrain=np.asarray([r['y'] for r in train],float)
        model=LinearCount(side_design(train,key),ytrain.ravel())
        raw=[model.predict(side_design(s,key)).reshape(-1,2) for s in [cal,stack,test]]
        outcomes=[np.asarray([r['y'] for r in s],float) for s in [cal,stack,test]]
        scales=count_scales(raw[0],outcomes[0],ridge=spec['ridge'])
        affine=fit_affine(raw[0],outcomes[0],ridge=spec['ridge'])
        stack_p=count_probabilities(raw[1]*scales,lines)
        stack_y=(outcomes[1].sum(axis=1)[:,None]>lines).astype(int)
        sigmoid=fit_sigmoid(stack_p,stack_y,ridge=spec['ridge'])
        p={
            'raw':count_probabilities(raw[2],lines),
            'count_scale':count_probabilities(raw[2]*scales,lines),
            'count_affine':count_probabilities(apply_affine(raw[2],affine),lines),
        }
        p['shared_sigmoid']=apply_sigmoid(p['count_scale'],sigmoid)
        weights={}
        if family=='corners':
            common=np.array([r['match_id'] in parent for r in stack])
            if common.sum()>=spec['minimum_stage_fixtures'][2]:
                parent_stack=np.array([poisson.sf(np.floor(lines),parent[r['match_id']]) for r in stack if r['match_id'] in parent])
                for kind in ['logit','pmf']:
                    weights[kind]=fit_blend(parent_stack,stack_p[common],stack_y[common],kind,spec['ridge'])
            else: unavailable.append({'fold':fold,'arm':'stacks','reason':'INSUFFICIENT_PARENT_SUPPORT','n':int(common.sum())})
        fit_last=max(r['kickoff_ts'] for r in stack)
        bounds=[{'n':len(s),'min_kickoff':min(r['kickoff_ts'] for r in s),
                 'max_kickoff':max(r['kickoff_ts'] for r in s),
                 'first_forecast':min(r['cutoff_ts'] for r in s)} for s in stages]
        artifacts.append({'family':family,'fold':fold,'lines':lines.tolist(),
            'linear_count':export_linear_count(model),'count_scales':scales.tolist(),
            'count_affine':affine.tolist(),'shared_sigmoid':sigmoid.tolist(),
            'shared_stack_weights':weights,'fit_last_kickoff_ts':fit_last,'stages':bounds,
            'status':'DEVELOPMENT_ONLY','availability_mode':'RETROSPECTIVE_RECONSTRUCTION'})
        folds.append({'fold':fold,'support':support,'stages':bounds,
            'count_diagnostics':{name:count_diagnostics(mu,outcomes[2]) for name,mu in [
                ('raw',raw[2]),('count_scale',raw[2]*scales),('count_affine',apply_affine(raw[2],affine))]}})
        for values in p.values(): assert_coherent(values)
        for i,row in enumerate(test):
            assert not temporal_eligibility(kickoff_ts=row['kickoff_ts'],fit_last_kickoff_ts=fit_last)
            ps={name:v[i] for name,v in p.items()}
            if family=='corners' and row['match_id'] in parent:
                pr=poisson.sf(np.floor(lines),parent[row['match_id']])
                ps['v3_horizon_matched']=pr
                for kind,name in [('logit','shared_logit_stack'),('pmf','pmf_mixture')]:
                    if kind in weights: ps[name]=coherent_blend(pr,ps['count_scale'],weights[kind],kind)
            for vals in ps.values(): assert_coherent(np.asarray(vals)[None,:])
            for j,line in enumerate(lines):
                matched=select_quote(quotes.get(row['match_id'],[]),row['cutoff_ts'],family,line,spec['market_quote_age_max_seconds'])
                close=select_quote(quotes.get(row['match_id'],[]),row['kickoff_ts'],family,line,spec['closing_max_seconds_before_kickoff'])
                def compact(q):
                    return None if q is None else {k:v for k,v in q.items() if k!='markets'}
                forecasts.append({'family':family,'fold':fold,'match_id':row['match_id'],
                    'competition_id':row['competition_id'],'kickoff_ts':row['kickoff_ts'],
                    'forecast_ts':row['cutoff_ts'],'line':float(line),
                    'y':int(sum(row['y'])>line),'p':{name:float(v[j]) for name,v in ps.items()},
                    'matched_market':compact(matched),'closing_market':compact(close)})
    for artifact in artifacts:
        artifact['evidence_content_sha256']=digest(evidence)
        artifact['artifact_sha256']=digest(artifact)
    return forecasts,{'folds':folds,'artifacts':artifacts,'parent_abstentions':abstentions,'unavailable':unavailable}


def score_family(rows,lines):
    arms=sorted({a for r in rows for a in r['p']})
    out={'all_lines':{},'by_line':{},'paired_comparisons':{}}
    for arm in arms:
        eligible=[r for r in rows if arm in r['p']]
        out['all_lines'][arm]=summary(eligible,arm)
        out['by_line'][arm]={str(line):summary([r for r in eligible if r['line']==line],arm) for line in lines}
        if arm!='count_scale':
            out['paired_comparisons']['count_scale_vs_'+arm]={metric:paired_interval(eligible,'count_scale',arm,metric) for metric in ['ll','brier']}
    return out


def market_experiment(rows,spec):
    out={}; all_market_rows=[]
    for family in spec['families']:
        family_rows=[r for r in rows if r['family']==family]
        # Require the registered full line bundle for pooled adjustment, preserving nesting.
        groups=defaultdict(list)
        for r in family_rows:groups[(r['fold'],r['match_id'])].append(r)
        complete=[]
        for group in groups.values():
            ordered=sorted(group,key=lambda r:r['line'])
            if len(group)!=len(spec['families'][family]) or not all(r['matched_market'] for r in group):continue
            try: assert_coherent(np.array([[r['matched_market']['p_market'] for r in ordered]]))
            except ValueError:continue
            complete.extend(ordered)
        reasons=[]; fitted=[]; evaluated=[]
        for fold in sorted({r['fold'] for r in family_rows}):
            test=[r for r in complete if r['fold']==fold]
            if not test:
                reasons.append({'fold':fold,'reason':'NO_COMPLETE_MATCHED_TIME_MARKETS'});continue
            first=min(r['forecast_ts'] for r in test)
            train=[r for r in complete if r['fold']<fold and r['kickoff_ts']+BUFFER<first]
            n=len({r['match_id'] for r in train})
            counts=[len({r['match_id'] for r in train if r['y']==y}) for y in [0,1]]
            if n<spec['market_minimum_fit_fixtures'] or min(counts)<spec['market_minimum_class_fixtures']:
                reasons.append({'fold':fold,'reason':'INSUFFICIENT_EARLIER_OOF_MARKET_SUPPORT','fixtures':n,'class_fixtures':counts});continue
            q=np.array([r['matched_market']['p_market'] for r in train]); y=np.array([r['y'] for r in train])
            calibrators={}
            for arm in ['market_calibrated','count_scale','shared_sigmoid']:
                football=None if arm=='market_calibrated' else np.array([r['p'][arm] for r in train])
                calibrators[arm]=fit_market(q,football,y,spec['ridge'])
            fitted.append({'fold':fold,'n_fit_fixtures':n,'parameters':{k:v.tolist() for k,v in calibrators.items()}})
            for r in test:
                q=r['matched_market']['p_market']; probs={'market_raw':q,**r['p']}
                for arm,theta in calibrators.items():
                    name=arm if arm=='market_calibrated' else 'market_plus_'+arm
                    probs[name]=float(apply_market(q,None if arm=='market_calibrated' else r['p'][arm],theta))
                evaluated.append({**r,'p':probs})
        matched=[{**r,'p':{**r['p'],'market_raw':r['matched_market']['p_market']}} for r in family_rows if r['matched_market']]
        closing=[{**r,'p':{**r['p'],'market_close':r['closing_market']['p_market']}} for r in family_rows if r['closing_market']]
        market_arms=spec['market_arms']
        out[family]={'status':'DEVELOPMENT_ONLY' if evaluated else 'MARKET_UNTESTED',
            'matched_line_observations':len(matched),'complete_bundle_observations':len(complete),
            'closing_line_observations':len(closing),'abstentions':reasons,'fits':fitted,
            'matched_scores':{a:summary(matched,a) for a in ['market_raw','count_scale','shared_sigmoid']},
            'closing_scores_separate_information_horizon':{a:summary(closing,a) for a in ['market_close','count_scale','shared_sigmoid']},
            'adjusted_scores':{a:summary(evaluated,a) for a in market_arms},
            'incremental_comparison':paired_interval(evaluated,'market_plus_count_scale','market_plus_shared_sigmoid'),
            'vs_market_only':paired_interval(evaluated,'market_calibrated','market_plus_shared_sigmoid')}
        all_market_rows.extend(evaluated)
    return out,all_market_rows


def audit_old_replay(quotes):
    obj=json.loads((ROOT/'research/v35_frontier/out/cache_replay_v1/results.json').read_text())
    art=json.loads((ROOT/'research/v35_frontier/V35_MODEL_ARTIFACT_V1.json').read_text())
    last=max(art['goals']['support']['calibration_max_kickoff_ts'],art['corners']['support']['stack_calibration_max_kickoff_ts'])
    result=[]
    for row in obj['fixtures']:
        f=row['fixture']; ts=f['kickoff_ts']
        reasons=temporal_eligibility(kickoff_ts=ts,fit_last_kickoff_ts=last)
        result.append({'match_id':f['match_id'],'kickoff_ts':ts,'forecast_ts':ts-HORIZON,
            'reconstruction_exclusions':reasons,'eligible_reconstruction':not reasons,
            'point_in_time_status':'NOT_ESTABLISHED; original artifact constructed after fixtures',
            'matched_time_goal_lines':sum(select_quote(quotes.get(f['match_id'],[]),ts-HORIZON,'goals',l) is not None for l in [2.5,3.5]),
            'original_odds_hours_before_kickoff':row['odds_hours_before_kickoff']})
    return result


def raw_coverage(evidence):
    present=Counter(); nonnull=Counter(); modes=Counter(); providers=Counter()
    for r in evidence:
        modes[str(r.get('availability_mode'))]+=1; providers[str(r.get('provider'))]+=1
        for k,v in (r.get('raw_stats') or {}).items():
            present[k]+=1
            if v is not None:nonnull[k]+=1
    return {'evidence_rows':len(evidence),'availability_modes':dict(modes),'providers':dict(providers),
            'raw_fields':{k:{'present':n,'non_null':nonnull[k]} for k,n in sorted(present.items())},
            'interpretation':'Coverage only; ambiguous semantics are not endorsed as model inputs. Frozen feature support is reused; no extra features fitted.'}


def main():
    if OUT.exists():raise RuntimeError('Immutable output exists; do not overwrite an exposed run')
    spec=json.loads((BASE/'SPEC.json').read_text())
    assert spec['decision_horizon_seconds']==HORIZON and spec['completion_buffer_seconds']==BUFFER
    evidence=[json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
    assert len({r['match_id'] for r in evidence})==len(evidence),'duplicate evidence identities'
    groups=sorted({r['kickoff_ts'] for r in evidence})
    boundaries=[[groups[min(int(np.ceil(len(groups)*f))-1,len(groups)-1)] for f in fs] for fs in spec['fold_fractions']]
    quotes,malformed=snapshots()
    print('Cached odds fixtures',len(quotes),'rejected snapshots',malformed,flush=True)
    print('Building venue panel',flush=True)
    gp=[r for r in build_venue_panel(evidence) if r['eligible_venue']]
    print('Building pressure panel',flush=True)
    cp=[r for r in build_corner_panel(evidence) if r['eligible_pressure']]
    forecasts=[]; construction={}; scores={}
    for family,panel in [('goals',gp),('corners',cp)]:
        pred,info=experiment_family(family,panel,evidence,boundaries,spec,quotes)
        forecasts.extend(pred);construction[family]=info;scores[family]=score_family(pred,spec['families'][family])
    market,market_rows=market_experiment(forecasts,spec)
    replay=audit_old_replay(quotes)
    OUT.mkdir()
    dump(OUT/'results.json',{'status':'DEVELOPMENT_ONLY','production_activation':False,
        'historical_mode':'RETROSPECTIVE_RECONSTRUCTION','boundaries':boundaries,
        'scores':scores,'market':market,'unsupported_targets':spec['unsupported_targets']})
    dump(OUT/'construction.json',construction)
    dump(OUT/'raw_coverage.json',raw_coverage(evidence))
    dump(OUT/'replay_timing_audit.json',replay)
    (OUT/'predictions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in forecasts))
    (OUT/'market_predictions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in market_rows))
    source_paths=list((ROOT/'src/research/v36_calibration').glob('*.py'))+[Path(__file__),BASE/'SPEC.json',EVIDENCE]
    # Bind reused transforms, frozen baselines and artifacts as well as new code.
    source_paths+=list((ROOT/'src/research/evidence_v32').glob('*.py'))
    source_paths+=list((ROOT/'src/research/v35_frontier').glob('*.py'))
    source_paths+=list((ROOT/'src/research/v3_pilot').glob('*.py'))
    source_paths+=[ROOT/'research/v35_frontier/V35_MODEL_ARTIFACT_V1.json',ROOT/'research/evidence_v32/market_audit_v322.py']
    dump(OUT/'manifest.json',{'spec_sha256':sha(BASE/'SPEC.json'),'evidence_sha256':sha(EVIDENCE),
        'sources':{str(p.relative_to(ROOT)):sha(p) for p in source_paths},
        'outputs':{p.name:sha(p) for p in OUT.iterdir() if p.is_file()},
        'offline_only':True,'paid_calls':0,'new_provider_calls':0,
        'market_index_fixtures':len(quotes),'rejected_market_snapshots':malformed})
    print(json.dumps({'status':'DEVELOPMENT_ONLY','forecasts':len(forecasts),
        'market_status':{k:v['status'] for k,v in market.items()},
        'replay_timing_excluded':sum(not r['eligible_reconstruction'] for r in replay)},indent=2),flush=True)


if __name__=='__main__':main()
