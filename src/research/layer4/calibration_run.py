"""QFE V2 Layer 4 calibrator fit/select/refit and support diagnostics."""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from scipy.optimize import minimize

from src.research.dataset.manifest import canonical_json,sha256_json
from src.research.layer4.calibrators import (
    IdentityCalibrator,PlattGlobal,BetaGlobal,WeightedIsotonic,RidgeContextPlatt,
    Calibrator,weighted_log_loss,weighted_brier,_logit,_sigmoid,
)
from src.research.layer4.protocol import protocol_v2
from src.research.evaluation.chronology import PROTECTED_START_TS

CALIBRATION_RUN_VERSION='qfe-layer4-calibration-run-v2-pit-replay'
GROUPS=('GOALS_TOTAL','CORNERS_SIDE','CORNERS_TOTAL')


def _read_json(path):
    d=json.loads(Path(path).read_text())
    if not isinstance(d,dict): raise ValueError(path)
    return d


def load_raw_rows(repo_root:Path)->tuple[dict[str,Any],list[dict[str,Any]]]:
    s=_read_json(repo_root/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_V2_PIT.json')
    raw=gzip.decompress((repo_root/'evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_ROWS_V2_PIT.jsonl.gz').read_bytes()).decode()
    rows=[json.loads(x) for x in raw.splitlines() if x.strip()]
    if len(rows)!=s['row_count'] or sha256_json(rows)!=s['rows_hash']: raise ValueError('raw calibration rows mismatch')
    return s,rows


def _arrays(rows):
    return (
        [float(r['raw_probability']) for r in rows],
        [bool(r['outcome_over']) for r in rows],
        [float(r['sample_weight']) for r in rows],
        [r.get('role') for r in rows],
        [r.get('competition_ref') for r in rows],
    )


def _fit_candidate(name:str,rows:list[dict],protocol:dict)->tuple[Calibrator|None,str|None]:
    p,y,w,roles,comps=_arrays(rows); eps=float(protocol['calibration']['probability_clip'])
    if len(set(y))<2: return None,'ONE_CLASS_FIT'
    if name=='IDENTITY': return IdentityCalibrator(),None
    if name=='PLATT_GLOBAL': return PlattGlobal.fit(p,y,w,eps),None
    if name=='BETA_GLOBAL': return BetaGlobal.fit(p,y,w,eps),None
    if name=='ISOTONIC_GLOBAL':
        sup=protocol['calibration']['isotonic_support']; unique=len({r['fixture_key'] for r in rows}); pos=sum(y); neg=len(y)-pos
        if unique<sup['min_unique_fixtures'] or len(rows)<sup['min_event_cells'] or pos<sup['min_each_class_cells'] or neg<sup['min_each_class_cells']:
            return None,'INSUFFICIENT_ISOTONIC_SUPPORT'
        return WeightedIsotonic.fit(p,y,w),None
    if name.startswith('PLATT_ROLE_COMP_RIDGE_L'):
        lam=float(name.rsplit('L',1)[1]); use_role=rows[0]['group']=='CORNERS_SIDE'
        return RidgeContextPlatt.fit(p,y,w,roles,comps,lam,eps,use_role),None
    raise ValueError(name)


def _apply(cal:Calibrator,rows:list[dict])->list[float]:
    return [cal.transform(float(r['raw_probability']),role=r.get('role'),competition_ref=r.get('competition_ref')) for r in rows]


def _metrics(cal:Calibrator,rows:list[dict])->dict[str,float]:
    p=_apply(cal,rows); _,y,w,_,_=_arrays(rows)
    return {'log_loss':weighted_log_loss(p,y,w),'brier':weighted_brier(p,y,w)}


def _select_group(group:str,rows:list[dict],protocol:dict,contract:dict)->dict[str,Any]:
    fit=[r for r in rows if r['phase']=='CALIBRATION_FIT']; select=[r for r in rows if r['phase']=='CALIBRATION_SELECT']
    names=list(protocol['calibration']['candidate_methods']); records=[]; fitted={}
    for name in names:
        cal,reason=_fit_candidate(name,fit,protocol)
        if cal is None:
            records.append({'candidate':name,'fit_status':'INELIGIBLE','reason':reason,'fit_spec':None,'select_metrics':None,'eligible_vs_identity':False}); continue
        fitted[name]=cal; records.append({'candidate':name,'fit_status':'OK','reason':None,'fit_spec':cal.to_spec(),'select_metrics':_metrics(cal,select),'eligible_vs_identity':False})
    by={r['candidate']:r for r in records}; identity=by['IDENTITY']['select_metrics']; tol=float(protocol['calibration']['brier_noninferiority_tolerance'])
    for r in records:
        if r['fit_status']!='OK': continue
        if r['candidate']=='IDENTITY': r['eligible_vs_identity']=True
        else:
            m=r['select_metrics']; r['eligible_vs_identity']=(m['log_loss']<identity['log_loss'] and m['brier']<=identity['brier']+tol)
    elig=[r for r in records if r['eligible_vs_identity']]
    min_ll=min(r['select_metrics']['log_loss'] for r in elig); tie=float(protocol['calibration']['ll_tie_tolerance']); complexity=contract['calibrator_implementation']['full_complexity_order']
    tied=[r for r in elig if r['select_metrics']['log_loss']<=min_ll+tie]
    selected=min(tied,key=lambda r:complexity.index(r['candidate']))['candidate']
    final_cal,reason=_fit_candidate(selected,rows,protocol)
    if final_cal is None: raise RuntimeError(f'final refit failed: {reason}')
    return {
        'group':group,'fit_event_cells':len(fit),'select_event_cells':len(select),'fit_unique_fixtures':len({r['fixture_key'] for r in fit}),'select_unique_fixtures':len({r['fixture_key'] for r in select}),
        'identity_select_metrics':identity,'candidate_results':records,'selected_candidate':selected,'selected_fit_window_spec':fitted[selected].to_spec(),'final_refit_spec':final_cal.to_spec(),'all_calibration_descriptive_metrics':_metrics(final_cal,rows),
    }


def _diagnostic_intercept_slope(probs,outcomes,weights,eps)->dict[str,float]:
    x=np.asarray([_logit(p,eps) for p in probs]); y=np.asarray(outcomes,float); w=np.asarray(weights,float)
    def obj(v):
        q=np.asarray([_sigmoid(float(v[0]+v[1]*z)) for z in x]); return weighted_log_loss(q,y,w,eps)*float(w.sum())
    res=minimize(obj,np.array([0.0,1.0]),method='L-BFGS-B')
    if not res.success: raise RuntimeError(res.message)
    return {'intercept':float(res.x[0]),'slope':float(res.x[1])}


def _bin_index(p:float,bins:list[float])->int:
    i=int(np.searchsorted(np.asarray(bins),p,side='right')-1); return max(0,min(i,len(bins)-2))


def _reliability_band(rows,cal_probs,weights,seed,replicates):
    by={}
    for r,p,w in zip(rows,cal_probs,weights,strict=True):
        block=int(r['kickoff_ts'])//604800; b=by.setdefault(block,[0.,0.,0.]); b[0]+=w*int(bool(r['outcome_over'])); b[1]+=w*p; b[2]+=w
    vals=list(by.values()); total=sum(x[2] for x in vals); point=(sum(x[0] for x in vals)-sum(x[1] for x in vals))/total
    rng=np.random.default_rng(seed); boots=[]; n=len(vals)
    if n:
        for _ in range(replicates):
            idx=rng.integers(0,n,size=n); obs=pred=den=0.
            for i in idx: obs+=vals[i][0];pred+=vals[i][1];den+=vals[i][2]
            boots.append((obs-pred)/den if den else 0.)
    return {'error_observed_minus_prediction':point,'ci_low':float(np.quantile(boots,.025)) if boots else None,'ci_high':float(np.quantile(boots,.975)) if boots else None,'n_time_blocks':n}


def _support_bins(group_rows,final_cal,protocol):
    bins=list(protocol['prediction_support_metadata']['probability_bins']); minfix=int(protocol['prediction_support_metadata']['reliability_min_unique_fixtures']); seed=protocol['bootstrap']['seed']; reps=protocol['bootstrap']['replicates']
    out=[]
    for i in range(len(bins)-1):
        lo,hi=bins[i],bins[i+1]; rows=[r for r in group_rows if _bin_index(float(r['raw_probability']),bins)==i]
        if not rows:
            out.append({'bin_index':i,'raw_probability_low':lo,'raw_probability_high':hi,'event_cells':0,'unique_fixtures':0,'supported':False}); continue
        p=_apply(final_cal,rows); _,y,w,_,_=_arrays(rows); unique=len({r['fixture_key'] for r in rows}); sw=sum(w)
        base={'bin_index':i,'raw_probability_low':lo,'raw_probability_high':hi,'event_cells':len(rows),'unique_fixtures':unique,'supported':unique>=minfix,'mean_raw_probability':sum(float(r['raw_probability'])*ww for r,ww in zip(rows,w,strict=True))/sw,'mean_calibrated_probability':sum(pp*ww for pp,ww in zip(p,w,strict=True))/sw,'observed_rate':sum(int(yy)*ww for yy,ww in zip(y,w,strict=True))/sw}
        base['reliability_error_ci']=_reliability_band(rows,p,w,seed,reps) if unique>=minfix else None; out.append(base)
    return out


def _assert_monotone(rows,cal_probs):
    groups={}
    for r,p in zip(rows,cal_probs,strict=True): groups.setdefault((r['fixture_key'],r['group'],r.get('role')),[]).append((float(r['line']),p))
    for key,vals in groups.items():
        vals=sorted(vals); ps=[x[1] for x in vals]
        if any(ps[i+1]>ps[i]+1e-12 for i in range(len(ps)-1)): raise ValueError(f'calibrated ladder non-monotone: {key}')


def run_calibration(*,repo_root:Path)->tuple[dict[str,Any],list[dict[str,Any]]]:
    repo_root=Path(repo_root); raw_summary,rows=load_raw_rows(repo_root); protocol=protocol_v2().to_dict(); contract=_read_json(repo_root/'evidence/layer4/QFE_LAYER4_EXECUTION_CONTRACT_V2_PIT.json')
    if raw_summary['protocol_hash']!=protocol_v2().protocol_hash or raw_summary['execution_contract_hash']!=contract['contract_hash']: raise ValueError('Layer4 binding mismatch')
    group_results=[]; final_cals={}
    for group in GROUPS:
        gr=[r for r in rows if r['group']==group]; result=_select_group(group,gr,protocol,contract); group_results.append(result)
        spec=result['final_refit_spec']; m=spec['method']
        # reconstruct candidate from final refit spec
        from src.research.layer4.calibrators import calibrator_from_spec
        final_cals[group]=calibrator_from_spec(spec)
    output_rows=[]; diagnostics={}
    for group in GROUPS:
        gr=[r for r in rows if r['group']==group]; cal=final_cals[group]; cp=_apply(cal,gr); _assert_monotone(gr,cp)
        _,y,w,_,_=_arrays(gr); diag=_diagnostic_intercept_slope(cp,y,w,float(protocol['calibration']['probability_clip'])); bins=_support_bins(gr,cal,protocol); diagnostics[group]={'calibration_intercept_slope':diag,'support_bins':bins}
        bin_defs=list(protocol['prediction_support_metadata']['probability_bins']); bin_by={b['bin_index']:b for b in bins}
        for r,p in zip(gr,cp,strict=True):
            bi=_bin_index(float(r['raw_probability']),bin_defs); sb=bin_by[bi]
            output_rows.append({**r,'p_model':p,'selected_calibrator':next(x['selected_candidate'] for x in group_results if x['group']==group),'raw_probability_bin':bi,'calibration_bin_event_cells':sb['event_cells'],'calibration_bin_unique_fixtures':sb['unique_fixtures'],'calibration_bin_mean_prediction':sb.get('mean_calibrated_probability'),'calibration_bin_observed_rate':sb.get('observed_rate'),'calibration_bin_reliability_error_ci':sb.get('reliability_error_ci')})
    output_rows.sort(key=lambda r:(r['kickoff_ts'],r['fixture_key'],r['group'],r.get('role') or '',r['line']))
    if any(int(r['kickoff_ts'])>=PROTECTED_START_TS for r in output_rows): raise ValueError('protected row leaked')
    result={'version':CALIBRATION_RUN_VERSION,'protocol_hash':protocol_v2().protocol_hash,'raw_calibration_hash':raw_summary['raw_calibration_hash'],'execution_contract_hash':contract['contract_hash'],'scientific_status':'CALIBRATION_FIT_SELECT_COMPLETE_PROTECTED_UNOPENED_NO_MARKET','group_results':group_results,'diagnostics':diagnostics,'row_count':len(output_rows),'rows_hash':sha256_json(output_rows),'protected_rows_scored':0,'market_odds_used':False}
    result['calibration_run_hash']=sha256_json(result); return result,output_rows


def render_markdown(d):
    lines=['# QFE V2 Layer 4 — Calibration Selection','',f"Calibration run hash: `{d['calibration_run_hash']}`",'', '> CALIBRATION FIT/SELECT only. PROTECTED remains unopened; market odds were not used.','']
    for g in d['group_results']:
        lines += [f"## {g['group']}",'',f"Selected: **{g['selected_candidate']}**",f"FIT fixtures: **{g['fit_unique_fixtures']}** · SELECT fixtures: **{g['select_unique_fixtures']}**",'', '| Candidate | SELECT LL | SELECT Brier | Eligible |','|---|---:|---:|:---:|']
        for r in g['candidate_results']:
            m=r['select_metrics']; lines.append(f"| {r['candidate']} | {m['log_loss']:.6f} | {m['brier']:.6f} | {r['eligible_vs_identity']} |" if m else f"| {r['candidate']} | n/a | n/a | False |")
        lines.append('')
    return '\n'.join(lines)


def write_calibration(*,summary_path:Path,md_path:Path,rows_path:Path,result,rows):
    raw=''.join(canonical_json(r)+'\n' for r in rows).encode(); gz=gzip.compress(raw,compresslevel=9,mtime=0); summary={**result,'rows_file':Path(rows_path).name,'rows_file_sha256':hashlib.sha256(gz).hexdigest(),'rows_encoding':'canonical-jsonl+gzip(mtime=0)'}
    for path,payload in ((Path(summary_path),canonical_json(summary)+'\n'),(Path(md_path),render_markdown(summary))):
        if path.exists():
            if path.read_text()!=payload: raise FileExistsError(path)
        else: path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payload)
    rp=Path(rows_path)
    if rp.exists():
        if rp.read_bytes()!=gz: raise FileExistsError(rp)
    else: rp.parent.mkdir(parents=True,exist_ok=True); rp.write_bytes(gz)
