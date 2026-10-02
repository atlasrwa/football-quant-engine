from __future__ import annotations
import math
import numpy as np
from scipy.special import expit, logit
from scipy.stats import nbinom
from src.research.v36_calibration.core import probability, assert_coherent

LINES=np.asarray([8.5,9.5,10.5],float)

def nb_over(mu,alpha,lines=LINES):
    mu=np.asarray(mu,float)
    alpha=float(alpha)
    if alpha<=0 or np.any(mu<=0): raise ValueError('invalid NB parameters')
    n=1.0/alpha
    p=n/(n+mu)
    out=nbinom.sf(np.floor(np.asarray(lines,float))[None,:],n,p[:,None] if p.ndim else p)
    return probability(out)

def nb_over_scalar(mu,alpha,lines=LINES):
    mu=float(mu); n=1.0/float(alpha); p=n/(n+mu)
    return probability(nbinom.sf(np.floor(np.asarray(lines,float)),n,p))

def challenger_probs(mu_v3,mu_pressure,alpha_v3,alpha_pressure,weight,k,lines=LINES):
    pv=nb_over_scalar(mu_v3,alpha_v3,lines)
    pp=nb_over_scalar(mu_pressure,alpha_pressure,lines)
    z=(1-float(weight))*logit(pv)+float(weight)*logit(pp)
    d=abs(math.log(float(mu_v3)/float(mu_pressure)))
    out=probability(expit(z/(1+float(k)*d)))
    assert_coherent(np.asarray(out)[None,:])
    return out,{'p_v3_nb':pv,'p_pressure_nb':pp,'mean_disagreement':d}
