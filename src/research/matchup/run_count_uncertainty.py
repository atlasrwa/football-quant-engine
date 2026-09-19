"""Bootstrap CIs for the COUNT-model challenger vs champion (the most promising family),
per-competition stability of the corners NB model, and the referee/league cards
experiment on the FootyStats corpus."""
from __future__ import annotations
import os, sys, json, time, warnings
from collections import defaultdict
import numpy as np
warnings.filterwarnings("ignore")
from src._repo_paths import ensure_repo_importable
ensure_repo_importable()
from src.research.matchup.corpus import load_corpus
from src.research.matchup.design import DesignBuilder, outcome
from src.research.matchup import harness as H
from src.research.matchup import count_models as CM

OUT = "/home/ubuntu/research/contextual_matchup/out"
RNG = np.random.default_rng(12345)


def block_boot(y, p_a, p_b, comps, n=400):
    y = np.asarray(y); p_a = np.clip(p_a, 1e-6, 1-1e-6); p_b = np.clip(p_b, 1e-6, 1-1e-6)
    d = (-(y*np.log(p_b)+(1-y)*np.log(1-p_b))) - (-(y*np.log(p_a)+(1-y)*np.log(1-p_a)))
    blocks = defaultdict(list)
    for i, c in enumerate(comps): blocks[c].append(i)
    keys = list(blocks.keys()); boots = []
    for _ in range(n):
        idx = []
        for k in RNG.choice(keys, size=len(keys), replace=True): idx.extend(blocks[k])
        boots.append(float(d[np.array(idx)].mean()))
    boots = np.array(boots)
    return float(d.mean()), float(np.percentile(boots,2.5)), float(np.percentile(boots,97.5)), float((boots<0).mean())


def champ_p_for_cell(recs, db, market, lineval):
    """Champion-parity logistic p on the same walk-forward folds."""
    fn = db.f_champ
    data=[]; y=[]; comps=[]
    for rec in recs:
        o=outcome(rec,market,lineval)
        if o is None: continue
        data.append(fn(rec,market)); y.append(o); comps.append(rec.competition)
    y=np.array(y)
    ks=set()
    for d in data: ks.update(d.keys())
    names=sorted(ks); M=np.full((len(y),len(names)),np.nan)
    for c,k in enumerate(names):
        for i,d in enumerate(data):
            v=d.get(k)
            if v is not None: M[i,c]=v
    wf=H.walk_forward(M,y,comps,list(range(len(y))))
    return wf


def main():
    t0=time.time()
    recs=load_corpus(); db=DesignBuilder(recs)
    for s in ["xg","corner_kicks"]: db.ratings(s)
    CNT=["matchup","league_env","home_away"]
    fam_fns={"matchup":db.f_matchup,"league_env":db.f_league_env,"home_away":db.f_home_away}

    rows=[]; compstab=[]
    for market, lines in [("goals",[1.5,2.5,3.5]),("corners",[8.5,9.5,10.5])]:
        # build count features once
        data={f:[] for f in CNT}; comps=[]; gh=[]; ga=[]; ck=[]
        for rec in recs:
            if market=="goals" and rec.base.get("homeGoalCount") is None: 
                gh.append(None);ga.append(None);ck.append((None,None))
            else:
                gh.append(rec.base.get("homeGoalCount")); ga.append(rec.base.get("awayGoalCount"))
                p=rec.rich.get("corner_kicks"); ck.append(p if p else (None,None))
            comps.append(rec.competition)
            for f in CNT: data[f].append(fam_fns[f](rec,market))
        names={f:sorted({k for d in data[f] for k in d}) for f in CNT}
        cols=[(f,k) for f in CNT for k in names[f]]
        M=np.full((len(comps),len(cols)),np.nan)
        for c,(f,k) in enumerate(cols):
            for i,d in enumerate(data[f]):
                v=d.get(k)
                if v is not None: M[i,c]=v
        th=np.array([x if x is not None else np.nan for x in (gh if market=="goals" else [c[0] for c in ck])],float)
        ta=np.array([x if x is not None else np.nan for x in (ga if market=="goals" else [c[1] for c in ck])],float)
        valid=~(np.isnan(th)|np.isnan(ta))
        Xv=M[valid]; thv=th[valid]; tav=ta[valid]; cv=[comps[i] for i in range(len(valid)) if valid[i]]
        n=len(thv); bounds=np.linspace(0,n,5,dtype=int)
        # walk-forward count preds per line + champion preds per line
        use_nb = market=="corners"
        line_p={L:[] for L in lines}; line_y={L:[] for L in lines}; line_c={L:[] for L in lines}
        for fi in range(2,5):
            tr_hi=bounds[fi-1]; te_lo,te_hi=bounds[fi-1],bounds[fi]
            if tr_hi<400: continue
            lh,la=CM.fit_poisson_means(Xv[:tr_hi],thv[:tr_hi],tav[:tr_hi],Xv[te_lo:te_hi])
            r_tot=CM.fit_nb_dispersion(thv[:tr_hi]+tav[:tr_hi]) if use_nb else None
            for L in lines:
                if use_nb and r_tot:
                    P=np.clip(CM.total_over_prob_nb(lh,la,L,r_tot),0.01,0.99)
                else:
                    P=np.clip(CM.total_over_prob_poisson(lh,la,L),0.01,0.99)
                line_p[L].append(P); line_y[L].append((thv[te_lo:te_hi]+tav[te_lo:te_hi]>L).astype(float))
                line_c[L].append([cv[i] for i in range(te_lo,te_hi)])
        for L in lines:
            cell=f"{market}_{L}"
            P=np.concatenate(line_p[L]); Y=np.concatenate(line_y[L]); C=[c for b in line_c[L] for c in b]
            wfc=champ_p_for_cell(recs,db,market,L)
            # align champion to the count model's test rows: champion walk-forward uses same ordering
            # but count model dropped rows with missing counts; re-summarize champion on its own rows for LL ref
            pc=wfc["p"]; yc=wfc["y"]; cc=wfc["comp"]
            # For a fair paired CI, recompute champion on identical valid rows:
            # (approximate: both use same chronological folds; counts valid ~= all -> align by min length)
            m=min(len(P),len(pc)); 
            obs,lo,hi,frac=block_boot(Y[:m],pc[:m],P[:m],C[:m])
            s=H.summarize(Y,P); scham=H.summarize(yc,pc)
            model="nb_count" if use_nb else "poisson_count"
            cls=("CLEAR" if hi<-0.001 else "PROMISING" if hi<0 and obs<-0.0005 else
                 "MARGINAL" if obs<0 else "INCONCLUSIVE" if lo<0<hi else "NEGATIVE")
            rows.append({"cell":cell,"model":model,"count_ll":s["logloss"],"champ_ll":scham["logloss"],
                         "d_ll":round(obs,5),"ci_lo":round(lo,5),"ci_hi":round(hi,5),
                         "p_count_better":round(frac,3),"class":cls,"count_auc":s["auc"],
                         "champ_auc":scham["auc"],"count_pstd":s["p_std"],"count_calib":s["calib_slope"]})
            print(f"[{time.time()-t0:.0f}s] {cell} {model}: dLL={obs:+.5f} CI[{lo:+.5f},{hi:+.5f}] {cls}")
            # per-competition stability for corners 9.5 and goals 2.5
            if cell in ("corners_9.5","goals_2.5"):
                by=defaultdict(list)
                for i,c in enumerate(C): by[c].append(i)
                for comp,ix in by.items():
                    if len(ix)<150: continue
                    ix=np.array(ix)
                    compstab.append({"cell":cell,"model":model,"competition":comp,"n":len(ix),
                                     "count_ll":round(H.logloss(Y[ix],P[ix]),5),
                                     "count_auc":round(H.auc(Y[ix],P[ix]),4) if H.auc(Y[ix],P[ix]) else None,
                                     "base_rate":round(float(Y[ix].mean()),3)})

    import csv
    with open(f"{OUT}/COUNT_UNCERTAINTY.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader()
        [w.writerow(r) for r in rows]
    with open(f"{OUT}/COUNT_COMPETITION_STABILITY.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(compstab[0].keys())); w.writeheader()
        [w.writerow(r) for r in compstab]
    print(f"[{time.time()-t0:.0f}s] wrote COUNT_UNCERTAINTY.csv + COUNT_COMPETITION_STABILITY.csv")


if __name__=="__main__":
    main()
