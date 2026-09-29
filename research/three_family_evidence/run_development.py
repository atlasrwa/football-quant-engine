"""Fixed offline development comparisons; never promotion or PIT replay."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import datetime as dt
import numpy as np
from scipy.special import expit, logit
from scipy.stats import poisson
from scipy.optimize import minimize
from sklearn.linear_model import PoissonRegressor

ROOT = Path(__file__).resolve().parent
MAP = {'shots':'overview.total_shots', 'sot':'overview.shots_on_target',
       'box':'shots.shots_inside_box', 'big':'overview.big_chances',
       'blocked':'shots.blocked_shots', 'crosses':'passes.accurate_crosses',
       'entries':'passes.final_third_entries', 'fouls':'overview.fouls',
       'tackles':'defending.tackles'}
BUNDLES = {'goals':['shots','sot','box','big'],
           'corners':['shots','blocked','crosses','entries'],
           'yellow_card_proxy':['fouls','tackles']}
FAMILY_KEY = {'goals':'goals','corners':'corners','yellow_card_proxy':'bookings'}
ALIASES = [('overview.total_shots','shots.total_shots'),
           ('overview.shots_on_target','shots.shots_on_target'),
           ('overview.tackles','defending.tackles')]


def number(x):
    return x if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0 else None


def semantics(row):
    """Quarantine conflicting cells rather than invent corrected observations."""
    raw = row['raw_stats']
    bad = {(c['path'],c['side']) for c in row['period_checks']}
    issues = list(row['period_checks'])
    for path in MAP.values():
        for side in ('home','away'):
            values=[number(raw.get(path+'.'+period+'.'+side)) for period in ('all','first_half','second_half')]
            if None not in values and values[0]!=values[1]+values[2] and (path,side) not in bad:
                bad.add((path,side))
                issues.append({'path':path,'side':side,'status':'PERIOD_RECONCILIATION_REQUIRED'})
    for a,b in ALIASES:
        for side in ('home','away'):
            x,y=raw.get(a+'.all.'+side),raw.get(b+'.all.'+side)
            if number(x) is not None and number(y) is not None and x!=y:
                bad.update(((a,side),(b,side)))
                issues.append({'path':a,'side':side,'status':'DUPLICATE_CONFLICT'})
    result = {}
    for side in ('home','away'):
        safe = row['targets']['corners.'+side]['period_status']=='NO_EXTRA_TIME_RECORDED'
        metrics = {name:(number(raw.get(path+'.all.'+side)) if safe and (path,side) not in bad else None)
                   for name,path in MAP.items()}
        for family,source in FAMILY_KEY.items():
            target=row['targets'][source+'.'+side]
            path={'corners':'overview.corner_kicks','yellow_card_proxy':'overview.yellow_cards'}.get(family)
            metrics[family] = (target['value'] if family=='goals' or (safe and (path,side) not in bad) else None)
        result[side]=metrics
    return result,issues


def weighted(entries, key, kind, cutoff):
    pairs=[(e[kind].get(key),2**(-(cutoff-e['ts'])/86400/365)) for e in entries]
    pairs=[(v,w) for v,w in pairs if v is not None]
    return (sum(v*w for v,w in pairs),sum(w for v,w in pairs),len(pairs))


def profile(entries, pool, cutoff):
    out={}
    for key in list(MAP)+list(BUNDLES):
        for kind in ('own','opp'):
            num,den,n=weighted(entries,key,kind,cutoff)
            gn,gd,_=weighted(pool,key,kind,cutoff)
            mean=gn/gd if gd else None
            out[kind+'_'+key]=(num+5*mean)/(den+5) if mean is not None else None
            out[kind+'_'+key+'_n']=n
    return out


def similar(entries, opposing_profile, family, cutoff):
    dimensions=['opp_'+family,'opp_shots']
    current=[opposing_profile[k] for k in dimensions]
    if any(v is None for v in current):return None,0
    values=[]
    for e in entries:
        past=[e['opponent_profile'][k] for k in dimensions]
        if e['own'][family] is None or any(v is None for v in past):continue
        d=sum(((a-b)/(1+abs(b)))**2 for a,b in zip(past,current))
        weight=math.exp(-0.5*d)*2**(-(cutoff-e['ts'])/86400/365)
        values.append((e['own'][family],weight))
    if len(values)<3:return None,len(values)
    num,den,_=weighted(entries,family,'own',cutoff)
    base=num/den
    return (sum(v*w for v,w in values)+5*base)/(sum(w for v,w in values)+5)-base,len(values)


def features(rows):
    history=defaultdict(list);pool=[];out=[];audit=[]
    for row in rows:
        cutoff=row['kickoff_ts']-24*3600
        # Four-hour buffer is a reconstruction convention, not observed completion.
        eligible_pool=[e for e in pool if e['ts']+4*3600<cutoff]
        sides={s:[e for e in history[row[s+'_id']] if e['ts']+4*3600<cutoff] for s in ('home','away')}
        profiles={s:profile(sides[s],eligible_pool,cutoff) for s in sides}
        metrics,issues=semantics(row)
        if issues:audit.append({'match_id':row['match_id'],'issues':issues})
        record={'match_id':row['match_id'],'date':row['kickoff'][:10],
                'kickoff_ts':row['kickoff_ts'],'cutoff_ts':cutoff,'families':{},
                'source_match_ids':sorted(set(e['match_id'] for es in sides.values() for e in es)),
                'max_source_kickoff':max([e['ts'] for e in eligible_pool],default=None)}
        for family,bundle in BUNDLES.items():
            item={'y':[metrics[s][family] for s in ('home','away')],'sides':{},
                  'eligible':all(profiles[s]['own_'+family+'_n']>=3 for s in sides)}
            for side,other in (('home','away'),('away','home')):
                p,q=profiles[side],profiles[other]
                neutral=row['context']['is_neutral']
                venue=None if neutral is None else (0 if neutral else (1 if side=='home' else -1))
                base=[p['own_'+family],p['opp_'+family],q['own_'+family],q['opp_'+family],venue]
                rich=base+[v for key in bundle for v in (p['own_'+key],q['opp_'+key])]
                h,hn=similar(sides[side],q,family,cutoff)
                item['sides'][side]={'M1':base,'M2':rich,'M2+H':rich+[h],
                    'hypothesis_support':hn,'target_history_n':p['own_'+family+'_n'],
                    'rich_history_n':{k:p['own_'+k+'_n'] for k in bundle}}
            record['families'][family]=item
        out.append(record)
        # Append only after computing both teams' historical pre-fixture profiles.
        for side,other in (('home','away'),('away','home')):
            entry={'match_id':row['match_id'],'ts':row['kickoff_ts'],
                   'own':metrics[side],'opp':metrics[other],
                   'opponent_profile':profiles[other]}
            history[row[side+'_id']].append(entry);pool.append(entry)
    return out,audit


class Fit:
    def __init__(self,x,y):
        x=np.asarray(x,dtype=float)
        self.median=np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).any() else 0 for col in x.T])
        x=self.impute(x);self.mean=x.mean(axis=0);self.std=x.std(axis=0);self.std[self.std==0]=1
        self.model=PoissonRegressor(alpha=1,max_iter=2000,tol=1e-8).fit((x-self.mean)/self.std,y)
    def impute(self,x):
        missing=~np.isfinite(x)
        return np.column_stack((np.where(missing,self.median,x),missing.astype(float)))
    def predict(self,x):
        x=self.impute(np.asarray(x,dtype=float))
        return np.maximum(self.model.predict((x-self.mean)/self.std),1e-8)


def matrix(rows,family,arm):
    return [r['families'][family]['sides'][s][arm] for r in rows for s in ('home','away')]


def metrics(predictions):
    y=np.array([r['event'] for r in predictions]);p=np.array([r['p'] for r in predictions])
    reliability=[]
    for low in (0,.2,.4,.6,.8):
        mask=(p>=low)&(p<low+.2+1e-12)
        if mask.any():reliability.append({'lower':low,'n':int(mask.sum()),'mean_p':float(p[mask].mean()),'observed':float(y[mask].mean())})
    cal=None
    if len(set(y))==2:
        z=logit(np.clip(p,1e-8,1-1e-8))
        def objective(b):return np.mean(np.logaddexp(0,b[0]+b[1]*z)-y*(b[0]+b[1]*z))
        fit=minimize(objective,[0.,1.],method='BFGS')
        if fit.success and np.isfinite(fit.x).all():cal={'intercept':float(fit.x[0]),'slope':float(fit.x[1])}
    return {'n':len(predictions),'log_loss':float(np.mean([r['loss'] for r in predictions])),
            'brier':float(np.mean((p-y)**2)),
            'count_log_loss':float(np.mean([r['count_loss'] for r in predictions])),
            'reliability':reliability,'calibration_diagnostic':cal,
            'calibration_noninferiority':'NOT_ESTABLISHED'}


def paired(a,b):
    assert [(r['match_id'],r['fold']) for r in a]==[(r['match_id'],r['fold']) for r in b]
    groups=defaultdict(list)
    for x,y in zip(a,b):
        day=dt.date.fromisoformat(x['date']);key=tuple(day.isocalendar()[:2])
        groups[key].append(x['loss']-y['loss'])
    blocks=list(groups.values());rng=np.random.default_rng(729);means=[]
    for _ in range(1000):
        selected=rng.integers(0,len(blocks),len(blocks))
        means.append(np.mean([v for i in selected for v in blocks[i]]))
    return {'mean_log_loss_improvement':float(np.mean([x['loss']-y['loss'] for x,y in zip(a,b)])),
            'descriptive_week_block_95_interval':list(map(float,np.quantile(means,[.025,.975]))),
            'week_blocks':len(blocks),'n':len(a),'confirmatory':False,
            'warning':'Nominal development interval; multiplicity unadjusted; few blocks and repeated teams limit inference.'}


def run(panel,spec):
    predictions=[];runs=[]
    for family in BUNDLES:
        valid=[r for r in panel if r['families'][family]['eligible'] and None not in r['families'][family]['y']]
        for fold_id,fold in enumerate(spec['folds']):
            train=[r for r in valid if r['date']<fold['train_before']]
            cal=[r for r in valid if fold['train_before']<=r['date']<fold['calibration_before']]
            test=[r for r in valid if fold['calibration_before']<=r['date']<fold['test_before']]
            # Boundary time guard: all fitted/calibration labels must precede first target freeze.
            if cal:train=[r for r in train if r['kickoff_ts']+4*3600<min(x['cutoff_ts'] for x in cal)]
            if test:cal=[r for r in cal if r['kickoff_ts']+4*3600<min(x['cutoff_ts'] for x in test)]
            counts={'family':family,'fold':fold_id,'train_n':len(train),'calibration_n':len(cal),'test_n':len(test)}
            if len(train)<30 or len(cal)<15 or len(test)<10:
                runs.append(dict(counts,state='INSUFFICIENT_SUPPORT'));continue
            ytrain=np.array([r['families'][family]['y'] for r in train]).ravel()
            ycal=np.array([r['families'][family]['y'] for r in cal])
            for arm in ('M1','M2','M2+H'):
                model=Fit(matrix(train,family,arm),ytrain)
                cm=model.predict(matrix(cal,family,arm)).reshape(-1,2)
                factor=(ycal.sum(axis=0)+20)/(cm.sum(axis=0)+20)
                means=model.predict(matrix(test,family,arm)).reshape(-1,2)*factor
                runs.append(dict(counts,state='FITTED_DEVELOPMENT',arm=arm,calibration_factor=factor.tolist(),
                    train_ids=[r['match_id'] for r in train],calibration_ids=[r['match_id'] for r in cal],test_ids=[r['match_id'] for r in test]))
                for r,mu in zip(test,means):
                    outcomes=r['families'][family]['y']
                    for target,index in (('home',0),('away',1),('total',None)):
                        y=sum(outcomes) if index is None else outcomes[index]
                        mean=float(sum(mu) if index is None else mu[index])
                        line=spec['lines'][family][target];p=float(np.clip(poisson.sf(math.floor(line),mean),1e-8,1-1e-8))
                        event=int(y>line)
                        predictions.append({'match_id':r['match_id'],'date':r['date'],'fold':fold_id,
                            'family':family,'target':target,'arm':arm,'y':y,'mean':mean,'line':line,
                            'event':event,'p':p,'loss':-event*math.log(p)-(1-event)*math.log1p(-p),
                            'count_loss':float(-poisson.logpmf(y,mean))})
    results={}
    for family in BUNDLES:
        for target in ('home','away','total'):
            arms={arm:[p for p in predictions if p['family']==family and p['target']==target and p['arm']==arm] for arm in ('M1','M2','M2+H')}
            result={'state':'DEVELOPMENT_ONLY','market_state':'MARKET_UNTESTED','promoted':False,
                    'semantic_target':'PROVIDER_YELLOW_CARD_PROXY' if family=='yellow_card_proxy' else 'REGULATION_COUNT',
                    'arms':{arm:metrics(ps) for arm,ps in arms.items() if ps}}
            if all(arms.values()):
                result['M1_minus_M2']=paired(arms['M1'],arms['M2'])
                result['M2_minus_M2H']=paired(arms['M2'],arms['M2+H'])
            else:result['state']='INSUFFICIENT_SUPPORT'
            results[family+'.'+target]=result
    return predictions,runs,results


def main():
    spec=json.loads((ROOT/'development_spec_v1.json').read_text())
    raw=(ROOT/'out/v1/evidence.jsonl').read_bytes()
    rows=[json.loads(line) for line in raw.splitlines()]
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    if digest!=spec['input_digest']:raise ValueError('frozen input digest mismatch')
    panel,audit=features(rows)
    predictions,runs,results=run(panel,spec)
    out=ROOT/'out/development_v1';out.mkdir(exist_ok=False)
    for name,value in [('features.json',panel),('semantic_audit.json',audit),('predictions.json',predictions),
                       ('runs.json',runs),('results.json',results)]:
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    manifest={'input_digest':digest,'spec_sha256':hashlib.sha256((ROOT/'development_spec_v1.json').read_bytes()).hexdigest(),
              'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'availability':'RETROSPECTIVE_RECONSTRUCTION_NOT_PIT_REPLAY','live_calls':0,'promotions':0,
              'feature_rows':len(panel),'flagged_matches':len(audit),
              'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'runs':[{k:v for k,v in r.items() if not k.endswith('_ids')} for r in runs],
                      'results':{k:{'n':v['arms'].get('M1',{}).get('n',0),
                         'M1_minus_M2':v.get('M1_minus_M2'), 'M2_minus_M2H':v.get('M2_minus_M2H')} for k,v in results.items()}},indent=2))


if __name__=='__main__':main()
