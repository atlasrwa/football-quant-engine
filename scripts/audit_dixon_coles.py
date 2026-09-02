"""
AUDIT 3 — Plain textbook Dixon-Coles on GOALS, point-in-time, on the cached corpus.

External check. Dixon & Coles (1997): home/away goals ~ correlated Poisson with
per-team attack a_i, defence b_i, home advantage gamma, and a low-score correlation
correction tau(rho) on {0-0, 1-0, 0-1, 1-1}. NO custom extensions, NO same-match
features (strengths are estimated from PRIOR matches only -> look-ahead free).

We fit strengths by MLE on an expanding window (refit periodically for speed),
predict the full scoreline distribution for each held-out match, derive P(total
goals > 2.5), and score BSS-vs-naive + ECE with the SHIPPED metric functions.

Expectation from literature (stated before running):
  * DC is the standard sharp baseline; it BEATS a naive/uniform predictor by a
    modest margin and is well-calibrated, while NOT beating the market.
  * A tuned DC on Serie A attains RPS 0.1972 vs market 0.1905 (arXiv:2608.11505,
    'Does a Structural Model Add Anything to the Closing Price?', 2026) — i.e. DC
    is close to but below the market, clearly above naive. Dixon & Coles (1997,
    JRSS-C) is the original reference that DC extracts real structure from goals.
  So on goals O/U 2.5 vs the NAIVE base rate we expect a SMALL POSITIVE BSS (low
  single-digit %) and ECE well under 0.05. Not +6-9% (that was leakage); not ~0
  (that would indict the corpus/harness).

Zero API — reads /home/ubuntu/.cache/footystats_research via the cache-first
client with network hard-blocked. Diagnose only.
"""
import os, sys, glob, re, math
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import src.research.footystats.client as fsclient
_orig = fsclient.FootyStatsResearchClient._request
def _blocked(self, endpoint, params=None, **kw):
    rp = dict(params or {}); rp.setdefault("key", "BLOCKED")
    c = self._cache_get(self._cache_key(endpoint, rp))
    if c is not None:
        return c
    raise RuntimeError(f"ZERO-API GUARD blocked: {endpoint}")
fsclient.FootyStatsResearchClient._request = _blocked

from src.research.footystats.normalizer import MatchNormalizer
from src.research.prediction_engine.calibration_metrics import brier_skill_score
from src.research.calibration import CalibrationEvaluator

CACHE = "/home/ubuntu/.cache/footystats_research"
LINE = 2.5
MIN_TRAIN = 100
REFIT = 40
MAX_GOALS = 10


def cached_season_ids():
    ids = []
    for p in glob.glob(f"{CACHE}/league-matches_*season_id:_*.json"):
        m = re.search(r"season_id:_(\d+)", p)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def load_goals_matches(client, normalizer, season_id):
    raw = client.fetch_season_matches(season_id)
    if not raw:
        return []
    ms = sorted(normalizer.normalize_batch(raw), key=lambda x: x.date_unix)
    out = []
    for m in ms:
        if m.home_goals is None or m.away_goals is None:
            continue
        out.append({"home": m.home_team, "away": m.away_team,
                    "hg": int(m.home_goals), "ag": int(m.away_goals),
                    "date": m.date_unix})
    return out


def tau(hg, ag, lam, mu, rho):
    """Dixon-Coles low-score correlation correction."""
    if hg == 0 and ag == 0:
        return 1.0 - lam * mu * rho
    if hg == 0 and ag == 1:
        return 1.0 + lam * rho
    if hg == 1 and ag == 0:
        return 1.0 + mu * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def fit_dixon_coles(matches):
    """Textbook DC MLE on a set of matches. Returns (atk, dfc, gamma, rho, teams)."""
    teams = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hg = np.array([m["hg"] for m in matches])
    ag = np.array([m["ag"] for m in matches])
    hi = np.array([idx[m["home"]] for m in matches])
    ai = np.array([idx[m["away"]] for m in matches])

    # params: attack[n], defence[n], home_adv, rho
    def negll(p):
        atk = p[:n]; dfc = p[n:2 * n]; gamma = p[2 * n]; rho = p[2 * n + 1]
        # identifiability: mean attack = 0 (log scale) via soft penalty
        pen = 50.0 * (atk.mean() ** 2 + dfc.mean() ** 2)
        log_lam = gamma + atk[hi] - dfc[ai]      # home
        log_mu = atk[ai] - dfc[hi]               # away
        log_lam = np.clip(log_lam, -3, 3); log_mu = np.clip(log_mu, -3, 3)
        lam = np.exp(log_lam); mu = np.exp(log_mu)
        # poisson logpmf
        ll = (hg * log_lam - lam - gammaln_arr(hg)) + (ag * log_mu - mu - gammaln_arr(ag))
        # tau correction (only low scores)
        t = np.ones(len(matches))
        m00 = (hg == 0) & (ag == 0); t[m00] = 1 - lam[m00] * mu[m00] * rho
        m01 = (hg == 0) & (ag == 1); t[m01] = 1 + lam[m01] * rho
        m10 = (hg == 1) & (ag == 0); t[m10] = 1 + mu[m10] * rho
        m11 = (hg == 1) & (ag == 1); t[m11] = 1 - rho
        t = np.clip(t, 1e-6, None)
        ll = ll + np.log(t)
        return -np.sum(ll) + pen

    x0 = np.zeros(2 * n + 2); x0[2 * n] = 0.25; x0[2 * n + 1] = -0.05
    res = minimize(negll, x0, method="L-BFGS-B",
                   options={"maxiter": 200, "ftol": 1e-6})
    p = res.x
    return (p[:n], p[n:2 * n], float(p[2 * n]), float(p[2 * n + 1]), idx)


from scipy.special import gammaln as _gammaln
def gammaln_arr(k):
    return _gammaln(k + 1)


def p_over_25(atk, dfc, gamma, rho, idx, home, away):
    """P(home+away goals > 2.5) from the DC scoreline matrix."""
    if home not in idx or away not in idx:
        return None
    ih, ia = idx[home], idx[away]
    lam = math.exp(max(-3, min(3, gamma + atk[ih] - dfc[ia])))
    mu = math.exp(max(-3, min(3, atk[ia] - dfc[ih])))
    # scoreline matrix with tau correction
    hs = np.arange(0, MAX_GOALS + 1)
    ph = np.exp(-lam) * lam ** hs / np.array([math.factorial(k) for k in hs])
    pa = np.exp(-mu) * mu ** hs / np.array([math.factorial(k) for k in hs])
    M = np.outer(ph, pa)
    # apply tau to the four low-score cells
    M[0, 0] *= (1 - lam * mu * rho)
    if MAX_GOALS >= 1:
        M[0, 1] *= (1 + lam * rho)
        M[1, 0] *= (1 + mu * rho)
        M[1, 1] *= (1 - rho)
    M = np.clip(M, 0, None)
    M /= M.sum()
    # P(total > 2.5) = 1 - P(total <= 2)
    p_under = 0.0
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            if h + a <= 2:
                p_under += M[h, a]
    return float(np.clip(1 - p_under, 0.001, 0.999))


def walk_forward_goals(matches):
    n = len(matches)
    if n < MIN_TRAIN + 30:
        return None
    preds, actuals = [], []
    naive_preds = []
    params = None
    for i in range(MIN_TRAIN, n):
        if (i - MIN_TRAIN) % REFIT == 0:
            try:
                atk, dfc, gamma, rho, idx = fit_dixon_coles(matches[:i])
                params = (atk, dfc, gamma, rho, idx)
            except Exception:
                continue
        if params is None:
            continue
        m = matches[i]
        po = p_over_25(*params, m["home"], m["away"])
        if po is None:
            continue
        actual = 1.0 if (m["hg"] + m["ag"]) > LINE else 0.0
        naive = sum(1 for mm in matches[:i] if (mm["hg"] + mm["ag"]) > LINE) / i
        preds.append(po); actuals.append(actual); naive_preds.append(naive)
    if len(preds) < 30:
        return None
    r = brier_skill_score(preds, [bool(a) for a in actuals])
    # BSS vs the naive base-rate predictor computed exactly as the producers do
    bm = np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)])
    bn = np.mean([(p - a) ** 2 for p, a in zip(naive_preds, actuals)])
    bss_vs_train_naive = (bn - bm) / bn * 100 if bn > 0 else None
    ce = CalibrationEvaluator(n_bins=10, min_samples=30).evaluate(preds, [bool(a) for a in actuals])
    return {"n": len(preds), "bss_vs_sample_base_pct": (r.bss * 100 if r.bss is not None else None),
            "bss_vs_train_naive_pct": bss_vs_train_naive,
            "ece": ce.ece, "brier": ce.brier_score,
            "mean_pred": float(np.mean(preds)), "base_rate": float(np.mean(actuals))}


def main():
    print("AUDIT 3 — plain textbook Dixon-Coles on GOALS O/U 2.5 (point-in-time, zero API)")
    print("Literature anchors: DC beats naive modestly & is well-calibrated but does NOT")
    print("beat the market (Dixon&Coles 1997 JRSS-C; arXiv:2608.11505 Serie A: DC RPS")
    print("0.1972 vs market 0.1905). Expect small +BSS vs naive and ECE < ~0.05.\n")

    client = fsclient.FootyStatsResearchClient(api_key="BLOCKED", cache_dir=__import__("pathlib").Path(CACHE))
    normalizer = MatchNormalizer()
    sids = cached_season_ids()

    rows = []
    done = 0
    for sid in sids:
        if done >= 10:
            break
        try:
            ms = load_goals_matches(client, normalizer, sid)
        except Exception as e:
            continue
        if len(ms) < MIN_TRAIN + 30:
            continue
        r = walk_forward_goals(ms)
        if r is None:
            continue
        rows.append(r); done += 1
        print(f"  season {sid}: n={r['n']:4d}  BSS_vs_naive(sample)={_p(r['bss_vs_sample_base_pct'])}  "
              f"BSS_vs_naive(train)={_p(r['bss_vs_train_naive_pct'])}  ECE={r['ece']:.4f}  "
              f"meanP={r['mean_pred']:.3f} base={r['base_rate']:.3f}")

    if rows:
        print("\n" + "=" * 78)
        print("AGGREGATE (sampled cached league-seasons)")
        print("=" * 78)
        for k, lab in [("bss_vs_sample_base_pct", "BSS vs naive (sample base rate)"),
                       ("bss_vs_train_naive_pct", "BSS vs naive (train base rate, producer-style)"),
                       ("ece", "ECE")]:
            vals = [r[k] for r in rows if r.get(k) is not None]
            if vals:
                print(f"  {lab:48s}: mean {np.mean(vals):+.3f}  median {np.median(vals):+.3f}  n_cells={len(vals)}")
        print("\nInterpretation:")
        print("  * small POSITIVE BSS + low ECE  -> corpus & harness SOUND; DC extracts real")
        print("    goal structure point-in-time as literature predicts; negative rich-field")
        print("    results stand.")
        print("  * ~0 / negative BSS or bad ECE -> problem UPSTREAM of modelling (corpus/folds/")
        print("    metric); would reframe the negatives.")
    else:
        print("no cached league-seasons usable for DC goals")


def _p(x):
    return "N/A" if x is None else f"{x:+.2f}%"


if __name__ == "__main__":
    main()
