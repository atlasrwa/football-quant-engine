"""
AUDIT 3b — diagnose whether the poor Dixon-Coles result is MY DC implementation
or the corpus/harness. Three cross-checks on the same cached goals data:

  (1) DC IN-SAMPLE: fit DC on all matches, predict the SAME matches. A correct DC
      MUST beat the naive base rate in-sample (it has strictly more parameters). If
      it does NOT, my DC fit is broken -> the walk-forward negative is my bug, not
      the corpus.
  (2) Global-Poisson point-in-time: predict P(total>2.5) from a single Poisson with
      lambda = mean total goals over PRIOR matches only (no team structure). This is
      the simplest honest point-in-time goals model. Its BSS vs naive should be ~0
      (a Poisson at the base mean is ~equivalent to the base rate for a fixed line).
  (3) DC lambda sanity: mean predicted total goals (lam+mu) vs realized mean total
      goals, in-sample. Should match closely if the fit is right.

Zero API (network blocked). Diagnose only.
"""
import os, sys, glob, re, math
import numpy as np
sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")

import src.research.footystats.client as fsclient
def _blocked(self, endpoint, params=None, **kw):
    rp = dict(params or {}); rp.setdefault("key", "BLOCKED")
    c = self._cache_get(self._cache_key(endpoint, rp))
    if c is not None: return c
    raise RuntimeError("ZERO-API GUARD")
fsclient.FootyStatsResearchClient._request = _blocked
from src.research.footystats.normalizer import MatchNormalizer
import audit_dixon_coles as dc
from scipy.stats import poisson as _poisson

CACHE = dc.CACHE
LINE = 2.5


def dc_in_sample(matches):
    atk, dfc, gamma, rho, idx = dc.fit_dixon_coles(matches)
    preds, actuals, lams = [], [], []
    for m in matches:
        po = dc.p_over_25(atk, dfc, gamma, rho, idx, m["home"], m["away"])
        if po is None: continue
        preds.append(po); actuals.append(1.0 if m["hg"]+m["ag"] > LINE else 0.0)
        ih, ia = idx[m["home"]], idx[m["away"]]
        lam = math.exp(max(-3,min(3, gamma+atk[ih]-dfc[ia])))
        mu = math.exp(max(-3,min(3, atk[ia]-dfc[ih])))
        lams.append(lam+mu)
    preds=np.array(preds); actuals=np.array(actuals)
    bm = np.mean((preds-actuals)**2)
    base = actuals.mean(); bn = np.mean((base-actuals)**2)
    bss = (bn-bm)/bn*100 if bn>0 else None
    realized_mean_tg = np.mean([m["hg"]+m["ag"] for m in matches])
    return {"n":len(preds), "bss_insample_pct":bss, "mean_pred_p":float(preds.mean()),
            "base_rate":float(base), "dc_mean_total_goals":float(np.mean(lams)),
            "realized_mean_total_goals":float(realized_mean_tg)}


def global_poisson_pit(matches, min_train=100):
    preds, actuals, naive = [], [], []
    tg = [m["hg"]+m["ag"] for m in matches]
    for i in range(min_train, len(matches)):
        lam = np.mean(tg[:i])
        po = float(1 - _poisson.cdf(2, lam))
        preds.append(po); actuals.append(1.0 if tg[i] > LINE else 0.0)
        naive.append(sum(1 for x in tg[:i] if x > LINE)/i)
    if len(preds) < 30: return None
    preds=np.array(preds); actuals=np.array(actuals); naive=np.array(naive)
    bm=np.mean((preds-actuals)**2); bn=np.mean((naive-actuals)**2)
    return {"n":len(preds), "bss_vs_naive_pct":((bn-bm)/bn*100 if bn>0 else None)}


def main():
    print("AUDIT 3b — DC diagnosis (in-sample floor + global-Poisson PIT), zero API\n")
    client = fsclient.FootyStatsResearchClient(api_key="BLOCKED", cache_dir=__import__("pathlib").Path(CACHE))
    norm = MatchNormalizer()
    sids = dc.cached_season_ids()
    rows=[]; done=0
    for sid in sids:
        if done>=6: break
        try: ms = dc.load_goals_matches(client, norm, sid)
        except Exception: continue
        if len(ms) < 130: continue
        ins = dc_in_sample(ms)
        gp = global_poisson_pit(ms)
        rows.append((sid, ins, gp)); done+=1
        print(f"season {sid}: n={ins['n']:4d}")
        print(f"   DC IN-SAMPLE BSS vs naive = {ins['bss_insample_pct']:+.2f}%  "
              f"(MUST be >0 if DC fit is correct)")
        print(f"   DC mean total-goals pred={ins['dc_mean_total_goals']:.2f} vs realized={ins['realized_mean_total_goals']:.2f}  "
              f"(should match)")
        print(f"   DC mean P(over2.5)={ins['mean_pred_p']:.3f} vs base rate={ins['base_rate']:.3f}")
        if gp:
            print(f"   GLOBAL-POISSON PIT BSS vs naive = {gp['bss_vs_naive_pct']:+.2f}% (expect ~0)")
    ins_bss = [r[1]["bss_insample_pct"] for r in rows if r[1]["bss_insample_pct"] is not None]
    gp_bss = [r[2]["bss_vs_naive_pct"] for r in rows if r[2] and r[2]["bss_vs_naive_pct"] is not None]
    print("\n" + "="*70)
    print(f"DC in-sample BSS vs naive: mean {np.mean(ins_bss):+.2f}%  (if <=0 -> DC impl broken)")
    if gp_bss:
        print(f"Global-Poisson PIT BSS vs naive: mean {np.mean(gp_bss):+.2f}%  (expect ~0; corpus/harness check)")


if __name__ == "__main__":
    main()
