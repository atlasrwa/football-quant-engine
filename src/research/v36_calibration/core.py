"""Bounded, chronology-aware calibrators. No IO or network access."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit, logit
from scipy.stats import poisson

HORIZON = 86400
BUFFER = 14400


class Unsupported(RuntimeError):
    pass


def probability(p):
    arr = np.asarray(p, float)
    if not np.all(np.isfinite(arr)) or np.any((arr < 0) | (arr > 1)):
        raise ValueError("invalid probabilities")
    return np.clip(arr, 1e-8, 1-1e-8)


def losses(p, y):
    p = probability(p); y = np.asarray(y, float)
    if p.shape != y.shape or not np.all(np.isin(y, [0, 1])):
        raise ValueError("invalid binary targets/shapes")
    return -(y*np.log(p)+(1-y)*np.log1p(-p)), (p-y)**2


def split_stages(panel, boundaries):
    stages = [[] for _ in range(4)]
    for row in sorted(panel, key=lambda r: (r['kickoff_ts'], r['match_id'])):
        for i, end in enumerate(boundaries):
            if row['kickoff_ts'] <= end:
                stages[i].append(row)
                break
    for i in range(3):
        later = [r for stage in stages[i+1:] for r in stage]
        if later:
            first = min(r['cutoff_ts'] for r in later)
            stages[i] = [r for r in stages[i] if r['kickoff_ts']+BUFFER < first]
    return stages


def prior_corner_rows(rows, forecast_ts):
    return [r for r in rows if float(r['ts'])+BUFFER < forecast_ts]


def require_non_neutral(fixture):
    neutral = fixture.get('is_neutral')
    if neutral is None:
        neutral = (fixture.get('context') or {}).get('is_neutral')
    if neutral is not False:
        raise Unsupported('VENUE_DEEP requires explicitly non-neutral fixture')


def temporal_eligibility(*, kickoff_ts, fit_last_kickoff_ts,
                         artifact_created_at=None, fixture_observed_at=None,
                         point_in_time=False):
    cutoff = kickoff_ts-HORIZON
    reasons = []
    if fit_last_kickoff_ts+BUFFER >= cutoff:
        reasons.append('FIT_LABEL_NOT_AVAILABLE_BEFORE_FORECAST')
    if point_in_time:
        if artifact_created_at is None or artifact_created_at >= cutoff:
            reasons.append('ARTIFACT_NOT_AVAILABLE_BEFORE_FORECAST')
        if fixture_observed_at is None or fixture_observed_at >= cutoff:
            reasons.append('FIXTURE_NOT_AVAILABLE_BEFORE_FORECAST')
    return reasons


def count_probabilities(means, lines):
    means = np.asarray(means, float)
    if means.ndim != 2 or means.shape[1] != 2 or not np.all(np.isfinite(means)) or np.any(means <= 0):
        raise ValueError('invalid side means')
    return probability(poisson.sf(np.floor(lines)[None, :], means.sum(axis=1)[:, None]))


def fit_affine(means, outcomes, ridge=.05):
    x = np.log(np.asarray(means, float)); y = np.asarray(outcomes, float)
    # Side-specific intercepts; one positive shared slope. Identity is prior.
    def objective(t):
        eta = t[:2][None, :] + t[2]*x
        return float(np.mean(np.sum(np.exp(eta)-y*eta, axis=1))
                     + ridge*np.sum((t-np.array([0,0,1]))**2))
    fit = minimize(objective, [0.,0.,1.], method='L-BFGS-B',
                   bounds=[(-2,2),(-2,2),(.1,3)])
    if not fit.success:
        raise Unsupported('count-affine optimizer failed')
    return fit.x


def apply_affine(means, theta):
    return np.exp(np.asarray(theta[:2])[None,:]+theta[2]*np.log(means))


def fit_sigmoid(p, y, ridge=.05):
    x=logit(probability(p)); y=np.asarray(y,float)
    losses(p,y)
    def objective(t):
        z=t[0]+t[1]*x
        return float(np.mean(np.logaddexp(0,z)-y*z)+ridge*(t[0]**2+(t[1]-1)**2))
    fit=minimize(objective,[0.,1.],method='L-BFGS-B',bounds=[(-3,3),(.05,4)])
    if not fit.success: raise Unsupported('sigmoid optimizer failed')
    return fit.x


def apply_sigmoid(p, theta):
    return probability(expit(theta[0]+theta[1]*logit(probability(p))))


def coherent_blend(parent, challenger, weight, kind):
    p=probability(parent); q=probability(challenger)
    if p.shape != q.shape or not 0 <= weight <= 1:
        raise ValueError('invalid blend')
    if kind=='pmf': return probability((1-weight)*p+weight*q)
    if kind=='logit': return probability(expit((1-weight)*logit(p)+weight*logit(q)))
    raise ValueError('unknown blend')


def fit_blend(parent, challenger, y, kind, ridge=.05):
    def objective(w):
        return float(losses(coherent_blend(parent,challenger,w,kind),y)[0].mean()+ridge*w*w)
    fit=minimize_scalar(objective,bounds=(0,1),method='bounded')
    if not fit.success: raise Unsupported('blend optimizer failed')
    return float(fit.x)


def assert_coherent(p):
    p=probability(p)
    if p.ndim!=2 or np.any(np.diff(p,axis=1)>1e-12):
        raise ValueError('non-monotone over-line probabilities')


def fit_market(q, p, y, ridge=.05):
    """Market baseline or market + football residual; shrink toward raw market."""
    zq=logit(probability(q)); y=np.asarray(y,float)
    cols=[np.ones_like(zq),zq]
    if p is not None: cols.append(logit(probability(p))-zq)
    x=np.column_stack(cols); anchor=np.array([0.,1.]+([] if p is None else [0.]))
    def objective(t):
        z=x@t
        return float(np.mean(np.logaddexp(0,z)-y*z)+ridge*np.sum((t-anchor)**2))
    # 0<=c<=b ensures nonnegative contributions of both coherent forecasts.
    cons=[] if p is None else [{'type':'ineq','fun':lambda t:t[1]-t[2]}]
    fit=minimize(objective,anchor,method='SLSQP',
                 bounds=[(-3,3),(.05,4)]+([] if p is None else [(0,4)]),constraints=cons)
    if not fit.success: raise Unsupported('market adjustment optimizer failed')
    return fit.x


def apply_market(q,p,theta):
    zq=logit(probability(q)); z=theta[0]+theta[1]*zq
    if len(theta)==3: z+=theta[2]*(logit(probability(p))-zq)
    return probability(expit(z))


def select_quote(snapshots, cutoff, family, line, max_age=3600):
    """Only actually observed last_seen quotes, never opening-price backdating."""
    market='total_goals' if family=='goals' else 'match_corners'
    candidates=[]
    for snap in snapshots:
        obs=snap['observed_at']
        if not 0 < cutoff-obs <= max_age: continue
        node=(snap['markets'].get(market) or {}).get(str(line)) or {}
        try:
            over=float(node['over']['last_seen']); under=float(node['under']['last_seen'])
        except (KeyError,TypeError,ValueError): continue
        if not (math.isfinite(over) and math.isfinite(under) and min(over,under)>1): continue
        candidates.append({**snap,'p_market':(1/over)/(1/over+1/under),
                           'over_odds':over,'under_odds':under,'age_seconds':cutoff-obs})
    return max(candidates,key=lambda r:r['observed_at']) if candidates else None


def summary(rows, arm):
    if not rows: return {'n_fixtures':0,'n_observations':0}
    p=np.array([r['p'][arm] for r in rows]); y=np.array([r['y'] for r in rows])
    ll,bs=losses(p,y)
    bins=[]
    for lo,hi in zip(np.arange(0,1,.1),np.arange(.1,1.1,.1)):
        take=(p>=lo)&(p<hi if hi<.999 else p<=1)
        if take.any(): bins.append({'lower':float(lo),'n':int(take.sum()),
             'mean_probability':float(p[take].mean()),'event_rate':float(y[take].mean())})
    # Diagnostic fit only: never fed back into any prediction.
    theta=None
    if len(set(y))==2 and len(set(np.round(p,8)))>1:
        x=logit(probability(p))
        fit=minimize(lambda t:float(np.mean(np.logaddexp(0,t[0]+t[1]*x)-y*(t[0]+t[1]*x))),
                     [0.,1.],method='BFGS')
        if fit.success: theta=[float(v) for v in fit.x]
    return {'n_fixtures':len({r['match_id'] for r in rows}),'n_observations':len(rows),
            'log_loss':float(ll.mean()),'brier':float(bs.mean()),
            'calibration_intercept_slope':theta,'reliability_bins':bins}


def paired_interval(rows, reference, challenger, metric='ll', seed=3601):
    blocks=defaultdict(lambda:defaultdict(list))
    for r in rows:
        idx=0 if metric=='ll' else 1
        diff=float(losses(r['p'][reference],r['y'])[idx]-losses(r['p'][challenger],r['y'])[idx])
        iso=datetime.fromtimestamp(r['kickoff_ts'],timezone.utc).isocalendar()
        blocks[(iso.year,iso.week)][r['match_id']].append(diff)
    values=[np.array([np.mean(v) for v in block.values()]) for block in blocks.values()]
    if not values:return {'n_fixtures':0,'interval':None}
    observed=float(np.concatenate(values).mean()); ci=None
    if len(values)>=8:
        rng=np.random.default_rng(seed)
        samples=[np.concatenate([values[i] for i in rng.integers(0,len(values),len(values))]).mean() for _ in range(2000)]
        ci=[float(v) for v in np.quantile(samples,[.025,.975])]
    return {'reference_minus_challenger':observed,'interval':ci,
            'n_fixtures':sum(len(v) for v in values),'week_blocks':len(values),
            'interpretation':'DEVELOPMENT_ONLY; positive favors challenger; no promotion'}
