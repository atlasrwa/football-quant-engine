"""Frozen V1.2.2 evaluation functions. No file I/O and no model fitting."""
from __future__ import annotations
import datetime as dt
from typing import Dict, Mapping, Sequence
import numpy as np

BOOTSTRAP_RESAMPLES=10000
BOOTSTRAP_SEED=0
MIN_DELTA=0.001
MAX_ECE_DETERIORATION=0.005
FAMILY_ALPHA=0.05
FAMILY_ORDER=("GOALS","CORNERS","TEAM_TOTALS","BOOKINGS")
ECE_BINS=10

def logloss(p,y):
    q=min(max(float(p),1e-15),1-1e-15)
    return -(float(y)*np.log(q)+(1-float(y))*np.log(1-q))

def ece(p,y,n_bins=ECE_BINS):
    p=np.asarray(p,float); y=np.asarray(y,float)
    if len(p)==0: return None
    out=0.0
    for b in range(n_bins):
        lo,hi=b/n_bins,(b+1)/n_bins
        m=(p>=lo)&(p<(hi) if b<n_bins-1 else p<=hi)
        if m.sum(): out += (m.sum()/len(p))*abs(float(p[m].mean()-y[m].mean()))
    return float(out)

def iso_week(kickoff):
    d=dt.datetime.fromtimestamp(float(kickoff),dt.timezone.utc).isocalendar()
    return f"{d.year}-W{d.week:02d}"

def holm_adjust(pvals: Mapping[str,float]) -> Dict[str,float]:
    items=sorted(pvals.items(),key=lambda kv:(kv[1],kv[0]))
    m=len(items); adj={}; running=0.0
    for rank,(k,p) in enumerate(items,1):
        running=max(running,(m-rank+1)*float(p))
        adj[k]=min(1.0,running)
    return adj

def family_compare(rows_by_target: Mapping[str,Sequence[Mapping]], *, resamples=BOOTSTRAP_RESAMPLES,
                   seed=BOOTSTRAP_SEED) -> Dict:
    """Equal-weight target means. Same resampled ISO-week blocks are used across targets."""
    cleaned={}
    for tid,rows in rows_by_target.items():
        rr=[r for r in rows if np.isfinite(r["p0"]) and np.isfinite(r["p1"])]
        if rr: cleaned[tid]=rr
    if not cleaned:
        return {"status":"NOT_EVALUABLE","reason":"NO_PAIRED_ROWS"}
    blocks=sorted({iso_week(r["kickoff"]) for rr in cleaned.values() for r in rr})
    bix={b:i for i,b in enumerate(blocks)}; nb=len(blocks)
    target_stats={}; sums=[]; counts=[]
    for tid in sorted(cleaned):
        rr=cleaned[tid]
        y=np.array([r["y"] for r in rr],float)
        p0=np.array([r["p0"] for r in rr],float); p1=np.array([r["p1"] for r in rr],float)
        delta=np.array([logloss(a,t)-logloss(b,t) for a,b,t in zip(p0,p1,y)])
        bi=np.array([bix[iso_week(r["kickoff"])] for r in rr])
        bs=np.bincount(bi,weights=delta,minlength=nb); bc=np.bincount(bi,minlength=nb).astype(float)
        sums.append(bs); counts.append(bc)
        target_stats[tid]={"n":len(rr),"delta_logloss":float(delta.mean()),
            "logloss_m0":float(np.mean([logloss(p,t) for p,t in zip(p0,y)])),
            "logloss_m1":float(np.mean([logloss(p,t) for p,t in zip(p1,y)])),
            "brier_m0":float(np.mean((p0-y)**2)),"brier_m1":float(np.mean((p1-y)**2)),
            "ece_m0":ece(p0,y),"ece_m1":ece(p1,y)}
    delta=float(np.mean([x["delta_logloss"] for x in target_stats.values()]))
    e0=float(np.mean([x["ece_m0"] for x in target_stats.values()]))
    e1=float(np.mean([x["ece_m1"] for x in target_stats.values()]))
    b0=float(np.mean([x["brier_m0"] for x in target_stats.values()]))
    b1=float(np.mean([x["brier_m1"] for x in target_stats.values()]))
    rng=np.random.default_rng(seed); draw=rng.integers(0,nb,size=(resamples,nb))
    treps=[]
    for bs,bc in zip(sums,counts):
        den=bc[draw].sum(axis=1); num=bs[draw].sum(axis=1)
        treps.append(np.divide(num,den,out=np.full(resamples,np.nan),where=den>0))
    reps=np.nanmean(np.vstack(treps),axis=0)
    lo,hi=np.nanpercentile(reps,[2.5,97.5])
    return {"status":"OK","n_targets":len(target_stats),"n_blocks":nb,
            "delta_logloss_m0_minus_m1":delta,"ci_lower":float(lo),"ci_upper":float(hi),
            "one_sided_p":float(np.nanmean(reps<=0.0)),
            "ece_m0":e0,"ece_m1":e1,"brier_m0":b0,"brier_m1":b1,
            "target_details":target_stats,"bootstrap_resamples":int(resamples),"bootstrap_seed":int(seed)}

def gate(cmp: Mapping, holm_p: float) -> Dict:
    if cmp.get("status")!="OK":
        return {"pass":False,"reason":"NOT_EVALUABLE"}
    checks={"delta_positive":cmp["delta_logloss_m0_minus_m1"]>0,
            "ci_lower_gt_zero":cmp["ci_lower"]>0,
            "delta_ge_0_001":cmp["delta_logloss_m0_minus_m1"]>=MIN_DELTA,
            "calibration":cmp["ece_m1"]<=cmp["ece_m0"]+MAX_ECE_DETERIORATION,
            "holm_p_le_0_05":float(holm_p)<=FAMILY_ALPHA}
    return {"pass":all(checks.values()),"checks":checks,"holm_adjusted_p":float(holm_p)}
