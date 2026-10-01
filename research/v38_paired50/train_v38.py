from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom,poisson

from src.research.evidence_v32.modeling_v322 import side_design
from src.research.evidence_v32.modeling_v33_corners import build_corner_panel
from src.research.v35_frontier.features import v3_corner_rows
from src.research.v35_frontier.model import FrozenLinearCount
from src.research.v3_pilot.model import predict_corners as predict_v3_corners, InsufficientHistory
from src.research.v36_calibration.core import split_stages, prior_corner_rows, probability, losses, coherent_blend
from src.research.v38_paired50.model import LINES, challenger_probs

ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/'research/v38_paired50/SPEC.json'
V37=ROOT/'research/v37_future50/MODEL_FREEZE.json'
V36_RESULTS=ROOT/'research/v36_calibration/out/results.json'
EVIDENCE=ROOT/'research/evidence_v32/out/evidence_v2/evidence.jsonl'
OUT=ROOT/'research/v38_paired50/MODEL_FREEZE.json'
SANITY=ROOT/'research/v38_paired50/HISTORICAL_SANITY.json'

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def fit_alpha(mu,y):
    mu=np.asarray(mu,float); y=np.asarray(y,int)
    def obj(a):
        n=1.0/a; p=n/(n+mu)
        return float(-np.mean(nbinom.logpmf(y,n,p)))
    fit=minimize_scalar(obj,bounds=(1e-5,2.0),method='bounded',options={'xatol':1e-8})
    if not fit.success: raise RuntimeError('alpha fit failed')
    return float(fit.x)

def parent_means(rows,evidence):
    bycomp={c:v3_corner_rows(evidence,c) for c in {r['competition_id'] for r in rows}}
    out={}
    for r in rows:
        hist=prior_corner_rows(bycomp[r['competition_id']],r['cutoff_ts'])
        target={'match_id':r['match_id'],'competition_id':r['competition_id'],
                'ts':r['kickoff_ts'],'home_id':r['home_id'],'away_id':r['away_id']}
        try: out[r['match_id']]=float(predict_v3_corners(hist,hist,target)['lambda_total'])
        except InsufficientHistory: pass
    return out

def baseline_probs(mu_v3,mu_pressure,w):
    pv=probability(poisson.sf(np.floor(LINES),float(mu_v3)))
    pp=probability(poisson.sf(np.floor(LINES),float(mu_pressure)))
    return coherent_blend(pv[None,:],pp[None,:],float(w),'logit')[0]

def main():
    if OUT.exists() or SANITY.exists(): raise RuntimeError('immutable V38 outputs already exist')
    spec=json.loads(SPEC.read_text()); v37=json.loads(V37.read_text())
    evidence=[json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
    panel=[r for r in build_corner_panel(evidence) if r['eligible_pressure']]
    boundaries=json.loads(V36_RESULTS.read_text())['boundaries'][1]
    train,cal,stack,test=split_stages(panel,boundaries)
    art=v37['corners_artifact']
    model=FrozenLinearCount(art['linear_count'])
    scales=np.asarray(art['count_scales'],float)

    allrows=stack+test
    parents=parent_means(allrows,evidence)

    def pmeans(rows):
        raw=model.predict(side_design(rows,'pressure')).reshape(-1,2)
        return (raw*scales[None,:]).sum(axis=1)

    mu_stack=pmeans(stack)
    y_stack=np.asarray([sum(r['y']) for r in stack],int)
    common=[i for i,r in enumerate(stack) if r['match_id'] in parents]
    if len(common)<300: raise RuntimeError(f'insufficient stack parent support {len(common)}')
    mu_p=mu_stack[common]
    mu_v=np.asarray([parents[stack[i]['match_id']] for i in common],float)
    y=y_stack[common]
    alpha_v=fit_alpha(mu_v,y); alpha_p=fit_alpha(mu_p,y)
    w=float(spec['corner_challenger']['pressure_weight'])

    ybin=(y[:,None]>LINES[None,:]).astype(float)
    def k_obj(k):
        ps=np.vstack([challenger_probs(a,b,alpha_v,alpha_p,w,k)[0] for a,b in zip(mu_v,mu_p)])
        return float(losses(ps,ybin)[0].mean()+float(spec['corner_challenger']['disagreement_shrink']['ridge'])*k*k)
    fit=minimize_scalar(k_obj,bounds=tuple(spec['corner_challenger']['disagreement_shrink']['k_bounds']),method='bounded',options={'xatol':1e-8})
    if not fit.success: raise RuntimeError('k fit failed')
    k=float(fit.x)

    freeze={
      'version':'QFE_V38_MODEL_FREEZE_1','spec_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),
      'v37_model_freeze_sha256':v37['freeze_sha256'],'evidence_content_sha256':digest(evidence),
      'training_stage':'V36_FOLD1_PROBABILITY_CALIBRATION','training_fixtures':len(common),
      'fit_last_kickoff_ts':max(stack[i]['kickoff_ts'] for i in common),
      'pressure_weight':w,'alpha_v3':alpha_v,'alpha_pressure':alpha_p,'disagreement_k':k,
      'registered_lines':LINES.tolist(),'goals_identical_to_v37':True,'refit_during_paired50':False
    }
    freeze['freeze_sha256']=digest(freeze)
    OUT.write_text(json.dumps(freeze,indent=2,sort_keys=True)+'\n')

    mu_test=pmeans(test)
    rows=[]
    for i,r in enumerate(test):
        if r['match_id'] not in parents: continue
        mv=float(parents[r['match_id']]); mp=float(mu_test[i]); yy=(np.asarray([sum(r['y'])])[:,None]>LINES[None,:]).astype(float)[0]
        base=baseline_probs(mv,mp,w); chal,_=challenger_probs(mv,mp,alpha_v,alpha_p,w,k)
        for j,line in enumerate(LINES):
            rows.append({'match_id':r['match_id'],'competition_id':r['competition_id'],'line':float(line),'y':int(yy[j]),'p_v37':float(base[j]),'p_v38':float(chal[j]),'kickoff_ts':r['kickoff_ts']})
    pv37=np.array([r['p_v37'] for r in rows]); pv38=np.array([r['p_v38'] for r in rows]); yy=np.array([r['y'] for r in rows])
    ll37,br37=losses(pv37,yy); ll38,br38=losses(pv38,yy)
    sanity={
      'status':'DIAGNOSTIC_ONLY_NO_RETUNING','n_fixtures':len({r['match_id'] for r in rows}),'n_observations':len(rows),
      'v37':{'log_loss':float(ll37.mean()),'brier':float(br37.mean())},
      'v38':{'log_loss':float(ll38.mean()),'brier':float(br38.mean())},
      'paired_gain':{'log_loss_v37_minus_v38':float((ll37-ll38).mean()),'brier_v37_minus_v38':float((br37-br38).mean())},
      'parameters':{'alpha_v3':alpha_v,'alpha_pressure':alpha_p,'disagreement_k':k,'pressure_weight':w},
      'note':'Frozen spec forbids retuning from this sanity result.'
    }
    SANITY.write_text(json.dumps(sanity,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'freeze':freeze,'sanity':sanity},indent=2))

if __name__=='__main__': main()
