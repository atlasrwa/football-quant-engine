"""Cards referee/league-environment experiment on the FootyStats corpus.

The champion cards model (FootyStats) is reconstructed here, then we test whether
adding PIT-safe referee tendency + league card environment improves chronological OOS,
with particular attention to the known high-confidence UNDER tail overconfidence.

FootyStats corpus is the only place refereeID lives (~83% coverage).
"""
from __future__ import annotations
import os, sys, warnings
from collections import defaultdict
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")
import pilotC_stat_mixer as mix
from src.research.matchup.referee_env import RefereeLeagueContext
from src.research.matchup import harness as H

OUT = "/home/ubuntu/research/contextual_matchup/out"
RNG = np.random.default_rng(12345)


def block_boot(y, p_a, p_b, comps, n=300):
    y=np.asarray(y); p_a=np.clip(p_a,1e-6,1-1e-6); p_b=np.clip(p_b,1e-6,1-1e-6)
    d=(-(y*np.log(p_b)+(1-y)*np.log(1-p_b)))-(-(y*np.log(p_a)+(1-y)*np.log(1-p_a)))
    blocks=defaultdict(list)
    for i,c in enumerate(comps): blocks[c].append(i)
    keys=list(blocks.keys()); boots=[]
    for _ in range(n):
        idx=[]
        for k in RNG.choice(keys,size=len(keys),replace=True): idx.extend(blocks[k])
        boots.append(float(d[np.array(idx)].mean()))
    boots=np.array(boots)
    return float(d.mean()),float(np.percentile(boots,2.5)),float(np.percentile(boots,97.5)),float((boots<0).mean())


def main():
    ms = mix.load_corpus()
    hist = mix.build_histories(ms)
    ctx = RefereeLeagueContext(ms)
    line = 4.5
    # champion feature vector (cards pool) reused from mix.match_features
    names = mix.feat_names("cards")
    X=[]; y=[]; comps=[]; ref=[]; leng=[]
    for m in ms:
        o = mix.outcome(m, "cards", line)
        if o is None: continue
        X.append(mix.match_features(hist, m, "cards")); y.append(o)
        comps.append(str(m.get("competition_id")))
        ref.append(ctx.referee_tendency(m.get("id")))
        leng.append(ctx.league_cards(m.get("id")))
    y=np.array(y)
    # coverage keep >=0.6
    Xarr=np.array([[ (np.nan if v is None else v) for v in r] for r in X],float)
    cov=np.mean(~np.isnan(Xarr),0); keep=[i for i in range(len(names)) if cov[i]>=0.6]
    Xk=Xarr[:,keep]
    ref=np.array([np.nan if v is None else v for v in ref]).reshape(-1,1)
    leng=np.array([np.nan if v is None else v for v in leng]).reshape(-1,1)

    def wf(M):
        return H.walk_forward(M,y,comps,list(range(len(y))))

    champ=wf(Xk)
    champ_ref=wf(np.hstack([Xk,ref]))
    champ_env=wf(np.hstack([Xk,leng]))
    champ_both=wf(np.hstack([Xk,ref,leng]))
    res={}
    for name,w in [("champ",champ),("champ+referee",champ_ref),("champ+leagueenv",champ_env),("champ+ref+env",champ_both)]:
        s=H.summarize(w["y"],w["p"])
        res[name]=(w,s)
        print(f"{name:18s} LL={s['logloss']} Brier={s['brier']} AUC={s['auc']} p_std={s['p_std']} calib={s['calib_slope']}")
    # CI for champ+ref+env vs champ (align rows)
    wc=champ["p"]; yb=champ["y"]; cb=champ["comp"]; wb=champ_both["p"]
    m=min(len(wc),len(wb))
    obs,lo,hi,frac=block_boot(yb[:m],wc[:m],wb[:m],cb[:m])
    print(f"champ+ref+env vs champ: dLL={obs:+.5f} CI[{lo:+.5f},{hi:+.5f}] p_better={frac:.3f}")

    # Tail forensics: high-confidence UNDER predictions (p<=0.2) — accuracy champ vs +ref+env
    def under_tail(w):
        p=w["p"]; yy=w["y"]; mk=p<=0.25
        if mk.sum()==0: return None
        # predicted UNDER, correct if actual==0
        acc=float((yy[mk]==0).mean())
        return {"n":int(mk.sum()),"under_acc":round(acc,4),"mean_p":round(float(p[mk].mean()),4)}
    import json
    tail={"champ":under_tail(champ),"champ+ref+env":under_tail(champ_both)}
    out={"line":line,
         "models":{k:v[1] for k,v in res.items()},
         "champ_vs_ref_env":{"d_ll":round(obs,5),"ci_lo":round(lo,5),"ci_hi":round(hi,5),"p_better":round(frac,3),
                             "class":("CLEAR" if hi<-0.001 else "PROMISING" if hi<0 and obs<-0.0005 else "MARGINAL" if obs<0 else "INCONCLUSIVE")},
         "under_tail_forensics":tail}
    json.dump(out,open(f"{OUT}/REFEREE_CARDS.json","w"),indent=2,default=str)
    print("under-tail (p<=0.25):", tail)
    print("wrote REFEREE_CARDS.json")


if __name__=="__main__":
    main()
