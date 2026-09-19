"""Count/distributional challengers for goals and corners (PHASE F).

Goals: predict home & away goal means via Poisson/NB regression on matchup features,
then derive P(total>line) and BTTS coherently. Optional Dixon-Coles low-score adjustment.
Corners: predict home & away corner means similarly -> P(total corners > line).

All chronological OOS, train-only preprocessing. Coherent line probs by construction
(one lambda -> monotone P(over) across lines).
"""
from __future__ import annotations
import warnings
import numpy as np
from math import exp, factorial
warnings.filterwarnings("ignore")
from sklearn.linear_model import PoissonRegressor
from scipy.stats import nbinom, poisson


def _prep(Xtr, Xte):
    med = np.nanmedian(Xtr, 0); med = np.where(np.isnan(med), 0, med)
    Xtr = Xtr.copy(); Xte = Xte.copy()
    for A in (Xtr, Xte):
        idx = np.where(np.isnan(A)); A[idx] = np.take(med, idx[1])
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    return (Xtr - mu) / sd, (Xte - mu) / sd


def fit_poisson_means(Xtr, ytr_home, ytr_away, Xte, alpha=1.0):
    """Fit two Poisson regressors (home goals, away goals). Return (lam_home, lam_away) for test."""
    Xtr_s, Xte_s = _prep(Xtr, Xte)
    mh = PoissonRegressor(alpha=alpha, max_iter=2000).fit(Xtr_s, ytr_home)
    ma = PoissonRegressor(alpha=alpha, max_iter=2000).fit(Xtr_s, ytr_away)
    lh = np.clip(mh.predict(Xte_s), 0.05, 8.0)
    la = np.clip(ma.predict(Xte_s), 0.05, 8.0)
    return lh, la


def total_over_prob_poisson(lh, la, line, max_goals=15):
    """P(home+away > line) assuming independent Poisson (sum is Poisson(lh+la))."""
    lam = lh + la
    k = int(np.floor(line))
    # P(total > line) = 1 - P(total <= k) = 1 - CDF(k)
    return 1.0 - poisson.cdf(k, lam)


def btts_prob_poisson(lh, la):
    """P(home>=1 and away>=1) = (1-e^-lh)(1-e^-la)."""
    return (1 - np.exp(-lh)) * (1 - np.exp(-la))


def dixon_coles_tau(x, y, lh, la, rho):
    """Low-score dependence correction factor."""
    if x == 0 and y == 0:
        return 1 - lh * la * rho
    if x == 0 and y == 1:
        return 1 + lh * rho
    if x == 1 and y == 0:
        return 1 + la * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def total_over_prob_dc(lh, la, line, rho=-0.05, max_goals=12):
    """P(total>line) under a Dixon-Coles-adjusted bivariate Poisson (scalar lh,la)."""
    k = int(np.floor(line))
    p_le = 0.0
    for x in range(0, max_goals + 1):
        for y in range(0, max_goals + 1):
            if x + y > k:
                continue
            px = exp(-lh) * lh ** x / factorial(x)
            py = exp(-la) * la ** y / factorial(y)
            tau = dixon_coles_tau(x, y, lh, la, rho)
            p_le += px * py * max(tau, 0.0)
    return float(np.clip(1 - p_le, 0.01, 0.99))


def fit_nb_dispersion(y):
    """Estimate NB dispersion (size r) from a sample via method of moments. Returns r or None."""
    m = np.mean(y); v = np.var(y)
    if v <= m:  # not overdispersed -> Poisson adequate
        return None
    r = m * m / (v - m)
    return max(r, 0.5)


def total_over_prob_nb(lh, la, line, r_total, max_n=40):
    """P(total>line) modeling the TOTAL directly as NB(mean=lh+la, size=r_total)."""
    mean = lh + la
    k = int(np.floor(line))
    # nbinom param: n=r, p=r/(r+mean)
    p = r_total / (r_total + mean)
    return 1.0 - nbinom.cdf(k, r_total, p)
