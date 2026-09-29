"""Offline calibration candidate. Never calls or modifies the corners model."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'three_family_evidence'
loader=importlib.util.spec_from_file_location('development',SOURCE/'run_development.py')
core=importlib.util.module_from_spec(loader);loader.loader.exec_module(core)


def calibrate(means, outcomes):
    logmeans=np.log(means)
    def loss(theta):
        z=theta[:2]+theta[2]*logmeans
        return np.mean(np.sum(np.exp(z)-outcomes*z+gammaln(outcomes+1),axis=1))+.05*(sum(theta[:2]**2)+(theta[2]-1)**2)
    fit=minimize(loss,np.array([0.,0.,1.]),method='L-BFGS-B',bounds=[(-2,2),(-2,2),(.25,3)])
    if not fit.success:raise RuntimeError('calibration convergence failure: '+fit.message)
    return fit.x


def events(mean,family):
    home,away=map(float,mean)
    if family not in ('goals','yellow_card_proxy'):raise ValueError('family out of scope')
    total_line=2.5 if family=='goals' else 3.5
    out={'home':float(poisson.sf(1,home)), 'away':float(poisson.sf(1,away)),
         'total':float(poisson.sf(math.floor(total_line),home+away))}
    if family=='goals':out['btts']=float((-np.expm1(-home))*(-np.expm1(-away)))
    return out


def compare_quote(prediction,quote,max_age_seconds):
    """Binary no-push comparisons only. No fabricated odds or inferred semantics."""
    keys=('fixture_id','market','side','period','line')
    if any(k not in prediction or k not in quote or prediction[k]!=quote[k] for k in keys):
        raise ValueError('market identity mismatch')
    if not prediction.get('settlement_verified') or not quote.get('settlement_verified'):
        raise ValueError('unsupported settlement semantics')
    if not prediction.get('binary_no_push') or not quote.get('binary_no_push'):
        raise ValueError('only binary no-push markets supported')
    freeze=prediction['freeze_ts'];observed=quote['observed_at']
    if not (math.isfinite(freeze) and math.isfinite(observed) and 0<=freeze-observed<=max_age_seconds and freeze<prediction['kickoff_ts']):
        raise ValueError('invalid quote timing')
    p=prediction['p_model'];yes,no=quote['selected_odds'],quote['opposite_odds']
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (p,yes,no)) or not 0<=p<=1 or min(yes,no)<=1:
        raise ValueError('invalid probability or decimal odds')
    market=(1/yes)/(1/yes+1/no)
    return {'p_model':p,'p_market_no_vig':market,'disagreement_pp':100*(p-market),
            'raw_break_even':1/yes,'ev_before_costs':p*yes-1,
            'state':'RESEARCH_COMPARISON_NOT_BET_AUTHORIZATION',
            'calibration_status':prediction.get('calibration_status','UNVALIDATED')}


def main():
    spec=json.loads((ROOT/'spec.json').read_text())
    protected=ROOT.parents[1]/'src/research/v3_pilot/model.py'
    assert hashlib.sha256(protected.read_bytes()).hexdigest()==spec['protected_model_sha256']
    old_manifest=json.loads((SOURCE/'out/development_v1/manifest.json').read_text())
    raw=(SOURCE/'out/development_v1/features.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==old_manifest['files']['features.json']
    panel={r['match_id']:r for r in json.loads(raw)}
    runs=[]
    for folder in ('development_v1','development_v2'):
        for run in json.loads((SOURCE/'out'/folder/'runs.json').read_text()):
            if run.get('arm')=='M2' and run['family'] in ('goals','yellow_card_proxy'):runs.append(run)
    predictions=[];fits=[]
    for run in runs:
        family=run['family'];train,cal,test=([panel[i] for i in run[k+'_ids']] for k in ('train','calibration','test'))
        assert max(r['kickoff_ts']+14400 for r in train)<min(r['cutoff_ts'] for r in cal)
        assert max(r['kickoff_ts']+14400 for r in cal)<min(r['cutoff_ts'] for r in test)
        model=core.Fit(core.matrix(train,family,'M2'),np.array([r['families'][family]['y'] for r in train]).ravel())
        cm=model.predict(core.matrix(cal,family,'M2')).reshape(-1,2)
        ycal=np.array([r['families'][family]['y'] for r in cal]);theta=calibrate(cm,ycal)
        rawmean=model.predict(core.matrix(test,family,'M2')).reshape(-1,2)
        oldfactor=(ycal.sum(axis=0)+20)/(cm.sum(axis=0)+20)
        candidates={'baseline':rawmean*oldfactor,'joint_calibration':np.exp(theta[:2]+theta[2]*np.log(rawmean))}
        fits.append({'family':family,'fold':run['fold'],'parameters':theta.tolist(),'train_n':len(train),'calibration_n':len(cal),'test_n':len(test)})
        for arm,means in candidates.items():
            for row,mean in zip(test,means):
                ys=row['families'][family]['y']
                for target,p in events(mean,family).items():
                    btts=target=='btts';y=int(ys[0]>0 and ys[1]>0) if btts else sum(ys) if target=='total' else ys[0 if target=='home' else 1]
                    line=None if btts else spec['lines'][family+'.'+target]
                    event=y if btts else int(y>line);p=float(np.clip(p,1e-8,1-1e-8))
                    loss=-event*math.log(p)-(1-event)*math.log1p(-p)
                    mu=sum(mean) if target=='total' else mean[0 if target=='home' else 1]
                    predictions.append({'match_id':row['match_id'],'date':row['date'],'fold':run['fold'],
                        'market':'btts' if btts else family+'.'+target,'arm':arm,'event':event,'p':p,
                        'loss':loss,'count_loss':loss if btts else float(-poisson.logpmf(y,mu))})
    results={}
    for market in sorted(set(p['market'] for p in predictions)):
        arms={a:[p for p in predictions if p['market']==market and p['arm']==a] for a in ('baseline','joint_calibration')}
        results[market]={'arms':{k:core.metrics(v) for k,v in arms.items()},
                         'improvement':core.paired(arms['baseline'],arms['joint_calibration']),
                         'state':'POST_EXPOSURE_DEVELOPMENT_ONLY','market_state':'MARKET_UNTESTED','promoted':False}
    output=ROOT/'out';output.mkdir(exist_ok=False)
    for name,value in (('results.json',results),('fits.json',fits),('predictions.json',predictions)):
        (output/name).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    manifest={'spec_sha256':hashlib.sha256((ROOT/'spec.json').read_bytes()).hexdigest(),
              'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'features_sha256':hashlib.sha256(raw).hexdigest(),'corners_unchanged':hashlib.sha256(protected.read_bytes()).hexdigest()==spec['protected_model_sha256'],
              'live_calls':0,'promotions':0,'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in output.iterdir()}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:{'n':v['arms']['baseline']['n'],'gain':v['improvement']['mean_log_loss_improvement'],
        'baseline_brier':v['arms']['baseline']['brier'],'candidate_brier':v['arms']['joint_calibration']['brier']} for k,v in results.items()},indent=2))


if __name__=='__main__':main()
