"""Weighted, monotone calibrators for QFE V2 Layer 4."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from typing import Any, Iterable

import numpy as np
from scipy.optimize import minimize


def _clip(p:float,eps:float)->float: return min(max(float(p),eps),1.0-eps)

def _logit(p:float,eps:float)->float:
    q=_clip(p,eps); return log(q/(1.0-q))

def _sigmoid(z:float)->float:
    if z>=0:
        e=exp(-min(z,700)); return 1.0/(1.0+e)
    e=exp(max(z,-700)); return e/(1.0+e)


def weighted_log_loss(probs, outcomes, weights, eps=1e-12)->float:
    total=sum(weights)
    if total<=0: raise ValueError('nonpositive total weight')
    return sum(w*(-log(_clip(p,eps)) if y else -log(1-_clip(p,eps))) for p,y,w in zip(probs,outcomes,weights,strict=True))/total


def weighted_brier(probs,outcomes,weights)->float:
    total=sum(weights)
    if total<=0: raise ValueError('nonpositive total weight')
    return sum(w*(float(p)-int(bool(y)))**2 for p,y,w in zip(probs,outcomes,weights,strict=True))/total


class Calibrator:
    name='BASE'
    def transform(self,p:float,*,role:str|None=None,competition_ref:str|None=None)->float: raise NotImplementedError
    def to_spec(self)->dict[str,Any]: raise NotImplementedError


@dataclass
class IdentityCalibrator(Calibrator):
    name='IDENTITY'
    def transform(self,p,**kwargs): return float(p)
    def to_spec(self): return {'method':self.name}


@dataclass
class PlattGlobal(Calibrator):
    intercept:float
    slope:float
    eps:float
    name='PLATT_GLOBAL'
    @classmethod
    def fit(cls,probs,outcomes,weights,eps):
        x=np.asarray([_logit(p,eps) for p in probs]); y=np.asarray(outcomes,float); w=np.asarray(weights,float)
        def obj(v):
            q=np.asarray([_sigmoid(float(v[0]+v[1]*z)) for z in x]); return weighted_log_loss(q,y,w,eps)*float(w.sum())
        res=minimize(obj,np.array([0.0,1.0]),method='L-BFGS-B',bounds=[(None,None),(1e-6,None)])
        if not res.success: raise RuntimeError(res.message)
        return cls(float(res.x[0]),float(res.x[1]),eps)
    def transform(self,p,**kwargs): return _sigmoid(self.intercept+self.slope*_logit(p,self.eps))
    def to_spec(self): return {'method':self.name,'intercept':self.intercept,'slope':self.slope,'eps':self.eps}


@dataclass
class BetaGlobal(Calibrator):
    intercept:float
    a:float
    b:float
    eps:float
    name='BETA_GLOBAL'
    @classmethod
    def fit(cls,probs,outcomes,weights,eps):
        p=np.asarray([_clip(x,eps) for x in probs]); y=np.asarray(outcomes,float); w=np.asarray(weights,float)
        x1=np.log(p); x2=-np.log(1-p)
        def obj(v):
            q=np.asarray([_sigmoid(float(v[0]+v[1]*a+v[2]*b)) for a,b in zip(x1,x2,strict=True)]); return weighted_log_loss(q,y,w,eps)*float(w.sum())
        res=minimize(obj,np.array([0.0,1.0,1.0]),method='L-BFGS-B',bounds=[(None,None),(0.0,None),(0.0,None)])
        if not res.success: raise RuntimeError(res.message)
        return cls(float(res.x[0]),float(res.x[1]),float(res.x[2]),eps)
    def transform(self,p,**kwargs):
        q=_clip(p,self.eps); return _sigmoid(self.intercept+self.a*log(q)-self.b*log(1-q))
    def to_spec(self): return {'method':self.name,'intercept':self.intercept,'a':self.a,'b':self.b,'eps':self.eps}


@dataclass
class WeightedIsotonic(Calibrator):
    x_points:tuple[float,...]
    y_points:tuple[float,...]
    name='ISOTONIC_GLOBAL'
    @classmethod
    def fit(cls,probs,outcomes,weights):
        order=np.argsort(np.asarray(probs,float),kind='mergesort')
        x=np.asarray(probs,float)[order]; y=np.asarray(outcomes,float)[order]; w=np.asarray(weights,float)[order]
        # collapse equal x before weighted PAV
        ux=[]; sy=[]; sw=[]
        for xv,yv,wv in zip(x,y,w,strict=True):
            if ux and xv==ux[-1]: sy[-1]+=yv*wv; sw[-1]+=wv
            else: ux.append(float(xv)); sy.append(float(yv*wv)); sw.append(float(wv))
        means=[a/b for a,b in zip(sy,sw,strict=True)]
        blocks=[[i,i+1,means[i],sw[i]] for i in range(len(ux))]
        i=0
        while i<len(blocks)-1:
            if blocks[i][2]>blocks[i+1][2]+1e-15:
                a,b=blocks[i],blocks[i+1]; ww=a[3]+b[3]; val=(a[2]*a[3]+b[2]*b[3])/ww
                blocks[i]=[a[0],b[1],val,ww]; blocks.pop(i+1); i=max(i-1,0)
            else: i+=1
        iso=np.zeros(len(ux))
        for start,end,val,_ in blocks: iso[start:end]=val
        return cls(tuple(ux),tuple(float(v) for v in iso))
    def transform(self,p,**kwargs):
        if not self.x_points: return float(p)
        return float(np.interp(float(p),np.asarray(self.x_points),np.asarray(self.y_points),left=self.y_points[0],right=self.y_points[-1]))
    def to_spec(self): return {'method':self.name,'x_points':list(self.x_points),'y_points':list(self.y_points)}


@dataclass
class RidgeContextPlatt(Calibrator):
    intercept:float
    slope:float
    role_coeffs:dict[str,float]
    competition_coeffs:dict[str,float]
    ridge_lambda:float
    eps:float
    name='PLATT_ROLE_COMP_RIDGE'
    @classmethod
    def fit(cls,probs,outcomes,weights,roles,competitions,ridge_lambda,eps,use_role):
        role_names=sorted({str(r) for r in roles if r is not None}) if use_role else []
        comp_names=sorted({str(c) for c in competitions if c is not None})
        ri={r:i for i,r in enumerate(role_names)}; ci={c:i for i,c in enumerate(comp_names)}
        x=np.asarray([_logit(p,eps) for p in probs]); y=np.asarray(outcomes,float); w=np.asarray(weights,float)
        n=2+len(role_names)+len(comp_names)
        def obj(v):
            z=v[0]+v[1]*x
            off=2
            if role_names:
                z=z+np.asarray([v[off+ri[str(r)]] if r is not None and str(r) in ri else 0.0 for r in roles]); off+=len(role_names)
            if comp_names: z=z+np.asarray([v[off+ci[str(c)]] if c is not None and str(c) in ci else 0.0 for c in competitions])
            q=np.asarray([_sigmoid(float(a)) for a in z]); loss=weighted_log_loss(q,y,w,eps)*float(w.sum())
            dev=v[2:]; return float(loss+ridge_lambda*np.dot(dev,dev))
        x0=np.zeros(n); x0[1]=1.0; bounds=[(None,None),(1e-6,None)]+[(None,None)]*(n-2)
        res=minimize(obj,x0,method='L-BFGS-B',bounds=bounds,options={'maxiter':2000})
        if not res.success: raise RuntimeError(res.message)
        off=2; rc={r:float(res.x[off+i]) for r,i in ri.items()}; off+=len(role_names); cc={c:float(res.x[off+i]) for c,i in ci.items()}
        return cls(float(res.x[0]),float(res.x[1]),rc,cc,float(ridge_lambda),eps)
    def transform(self,p,*,role=None,competition_ref=None):
        z=self.intercept+self.slope*_logit(p,self.eps)
        if role is not None: z+=self.role_coeffs.get(str(role),0.0)
        if competition_ref is not None: z+=self.competition_coeffs.get(str(competition_ref),0.0)
        return _sigmoid(z)
    def to_spec(self): return {'method':self.name,'intercept':self.intercept,'slope':self.slope,'role_coeffs':dict(sorted(self.role_coeffs.items())),'competition_coeffs':dict(sorted(self.competition_coeffs.items())),'ridge_lambda':self.ridge_lambda,'eps':self.eps}


def calibrator_from_spec(spec:dict[str,Any])->Calibrator:
    m=spec['method']
    if m=='IDENTITY': return IdentityCalibrator()
    if m=='PLATT_GLOBAL': return PlattGlobal(spec['intercept'],spec['slope'],spec['eps'])
    if m=='BETA_GLOBAL': return BetaGlobal(spec['intercept'],spec['a'],spec['b'],spec['eps'])
    if m=='ISOTONIC_GLOBAL': return WeightedIsotonic(tuple(spec['x_points']),tuple(spec['y_points']))
    if m=='PLATT_ROLE_COMP_RIDGE': return RidgeContextPlatt(spec['intercept'],spec['slope'],dict(spec['role_coeffs']),dict(spec['competition_coeffs']),spec['ridge_lambda'],spec['eps'])
    raise ValueError(m)
