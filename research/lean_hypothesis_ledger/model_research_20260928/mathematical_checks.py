#!/usr/bin/env python3
"""Synthetic mathematics only. No football observations, fitting or promotion."""
import json, math
from pathlib import Path

def poisson(mu,n):
    return math.exp(-mu+n*math.log(mu)-math.lgamma(n+1))

def negbin(mu,r,n):
    return math.exp(math.lgamma(n+r)-math.lgamma(r)-math.lgamma(n+1)
                    +r*math.log(r/(r+mu))+n*math.log(mu/(r+mu)))

def over(pmf,line):
    return 1-sum(pmf(k) for k in range(math.floor(line)+1))

mu,r=10.0,10.0
sensitivity=[]
for line in [8.5,9.5,12.5]:
    p=over(lambda n:poisson(mu,n),line)
    q=over(lambda n:negbin(mu,r,n),line)
    sensitivity.append(dict(line=line,poisson=p,negative_binomial=q,difference_pp=100*(q-p)))
assert sensitivity[0]['negative_binomial']<sensitivity[0]['poisson']
assert sensitivity[-1]['negative_binomial']>sensitivity[-1]['poisson']
assert abs(sum(negbin(mu,r,n) for n in range(300))-1)<1e-12

lh,la,rho=1.6,1.2,-0.1
def tau(h,a):
    if (h,a)==(0,0): return 1-lh*la*rho
    if (h,a)==(0,1): return 1+lh*rho
    if (h,a)==(1,0): return 1+la*rho
    if (h,a)==(1,1): return 1-rho
    return 1.0
base={(h,a):poisson(lh,h)*poisson(la,a) for h in range(40) for a in range(40)}
dc={k:p*tau(*k) for k,p in base.items()}
assert min(dc.values())>=0
assert abs(sum(dc.values())-1)<1e-12
metrics={}
for key,rule in [('over2_5',lambda h,a:h+a>=3),('btts',lambda h,a:h>0 and a>0),('draw',lambda h,a:h==a)]:
    p=sum(v for (h,a),v in base.items() if rule(h,a))
    q=sum(v for (h,a),v in dc.items() if rule(h,a))
    metrics[key]={'poisson':p,'dixon_coles_fixed_rates':q,'difference_pp':100*(q-p)}
assert abs(metrics['over2_5']['difference_pp'])<1e-10
assert abs(metrics['btts']['difference_pp'])>0.1

# Binary no-push, no commission: EV = d*p-1; probability band must scale by d.
p,d,dp=.60,2.10,.04
ev=p*d-1
lower=(p-dp)*d-1
assert math.isclose(lower,ev-d*dp)
out={'classification':'SYNTHETIC_MATHEMATICAL_DEMONSTRATION_NOT_EMPIRICAL_EVIDENCE',
'parameters_not_fitted':True,
'dispersion_demo':{'mean':mu,'poisson_variance':mu,'nb_shape':r,'nb_variance':mu+mu*mu/r,'markets':sensitivity},
'dixon_coles_demo':{'lambda_home':lh,'lambda_away':la,'rho':rho,'metrics':metrics,
'interpretation':'At fixed rates the standard four-cell correction leaves all total-over lines >=2.5 unchanged. Refitting rates can change those totals.'},
'ev_units_demo':{'p':p,'odds':d,'illustrative_probability_allowance':dp,'point_ev':ev,
'correct_lower_ev_for_this_assumed_allowance':lower,'incorrect_subtract_probability_directly':ev-dp,
'allowance_is_validated_confidence_bound':False}}
Path(__file__).with_name('MATHEMATICAL_CHECKS.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
