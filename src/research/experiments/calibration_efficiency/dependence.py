"""Signed home/away dependence layer for the corners total (Experiment B).

The champion builds the match total as ``np.convolve(home_pmf, away_pmf)`` — the
independence assumption. This module provides a drop-in JOINT construction that
couples the two side count PMFs with a SIGNED dependence parameter ``rho`` while
PRESERVING the two marginals exactly. It is inserted only in the experiment; the
champion's marginal engine is untouched.

Construction: a GAUSSIAN COPULA over the two discrete marginals.
- Each side's PMF defines a discrete CDF. We map count k to the latent-normal
  interval [Phi^-1(F(k-1)), Phi^-1(F(k))].
- The joint probability of (home=i, away=j) is the bivariate-normal rectangle
  probability over the two intervals at LATENT correlation ``rho``.
- rho = 0  -> the rectangle probability factorises -> joint = outer product of
  marginals -> total PMF == the independence convolution (verified in tests).
- rho < 0  -> negative dependence: high home corners pair with low away corners.
  This REDUCES the variance of the total (the hypothesised correction).
- rho > 0  -> positive dependence, INCREASES total variance.

IMPORTANT — ``rho`` is the LATENT (Gaussian copula) correlation, NOT the
observed count-space Pearson correlation. For discrete count marginals the two
differ: a latent rho of -0.21 induces a count-space correlation of roughly
-0.20 (slightly attenuated by discretisation). The experiment estimates a
count-space residual correlation (~-0.21) and feeds it as the latent rho, which
therefore UNDER-applies the dependence by a small amount. This is a conservative
approximation for the REJECT conclusion (the correctly-scaled latent rho would
be slightly more negative, sharpening the total further and making calibration
WORSE, not better). Any production use would need the exact count->latent
inversion; the experiment does not, because the direction of the error only
strengthens the REJECT.

Marginals are preserved by construction because the copula only redistributes
mass across the joint cells; summing the joint over one axis returns the other
marginal exactly (up to the bivariate-normal quadrature tolerance, which is
enforced by a renormalisation guard and checked in tests).

No SciPy multivariate CDF dependency at call time beyond the standard normal;
the bivariate normal CDF is evaluated by a small, deterministic Gauss-Legendre
quadrature of the standard bivariate density, which is fast and exact enough for
count grids of size ~31.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.stats import norm

# Clamp for latent thresholds so Phi^-1(0)/Phi^-1(1) stay finite.
_Z_CLAMP = 8.0


def _cdf_thresholds(pmf: np.ndarray) -> np.ndarray:
    """Latent-normal thresholds z_k = Phi^-1(F(k)) for a discrete PMF.

    Returns an array of length len(pmf)+1: [-inf-ish, z_0, z_1, ..., z_{K}=+inf-ish]
    where the interval for count k is (thresholds[k], thresholds[k+1]].
    """
    cdf = np.clip(np.cumsum(pmf), 0.0, 1.0)
    # Force the final threshold to exactly 1 so the top bin closes at +inf.
    cdf[-1] = 1.0
    z = norm.ppf(cdf)
    z = np.clip(z, -_Z_CLAMP, _Z_CLAMP)
    return np.concatenate([[-_Z_CLAMP], z])


# Precomputed Gauss-Legendre nodes/weights on [0,1] for integrating the bivariate
# normal CDF via the standard "integrate the density of one variable times the
# conditional normal CDF of the other" identity. 64 nodes is ample for |rho|<0.95.
_GL_NODES, _GL_WEIGHTS = np.polynomial.legendre.leggauss(64)


def _bivar_normal_cdf(h: float, k: float, rho: float) -> float:
    """P(X <= h, Y <= k) for standard bivariate normal with correlation rho.

    Uses the identity  Phi2(h,k;rho) = integral_{-inf}^{h} phi(x) * Phi((k - rho x)
    / sqrt(1-rho^2)) dx, evaluated by mapping (-inf, h] to a finite range via the
    standard-normal quantile substitution so a fixed Gauss-Legendre rule is exact
    to machine-ish precision for smooth integrands.
    """
    if rho <= -0.999999:
        return max(0.0, norm.cdf(h) + norm.cdf(k) - 1.0)
    if rho >= 0.999999:
        return float(norm.cdf(min(h, k)))
    if h <= -_Z_CLAMP or k <= -_Z_CLAMP:
        return 0.0
    if h >= _Z_CLAMP and k >= _Z_CLAMP:
        return 1.0
    s = math.sqrt(1.0 - rho * rho)
    # Substitute x = Phi^-1(u), u in (0, Phi(h)] so the domain is finite and the
    # weight phi(x) dx becomes du. Integrand: Phi((k - rho x)/s).
    upper = float(norm.cdf(h))
    if upper <= 0.0:
        return 0.0
    # Map GL nodes from [-1,1] to [0, upper].
    u = 0.5 * upper * (_GL_NODES + 1.0)
    jac = 0.5 * upper
    x = norm.ppf(np.clip(u, 1e-15, 1 - 1e-15))
    integrand = norm.cdf((k - rho * x) / s)
    return float(np.sum(_GL_WEIGHTS * integrand) * jac)


def _rectangle_prob(h_lo, h_hi, a_lo, a_hi, rho) -> float:
    """Bivariate-normal probability of the rectangle (h_lo,h_hi] x (a_lo,a_hi]."""
    return (
        _bivar_normal_cdf(h_hi, a_hi, rho)
        - _bivar_normal_cdf(h_lo, a_hi, rho)
        - _bivar_normal_cdf(h_hi, a_lo, rho)
        + _bivar_normal_cdf(h_lo, a_lo, rho)
    )


def _bivar_normal_cdf_grid(hz: np.ndarray, az: np.ndarray, rho: float) -> np.ndarray:
    """Vectorized Phi2(hz_i, az_j; rho) over all threshold pairs at once.

    Uses the same identity as ``_bivar_normal_cdf`` but evaluates the whole grid
    with broadcasting: for each home threshold h we integrate phi(x) over
    (-inf, h] of Phi((az - rho x)/s) across ALL away thresholds simultaneously.
    Returns an array of shape (len(hz), len(az)). Deterministic; matches the
    scalar routine to quadrature precision (verified in tests).
    """
    s = math.sqrt(1.0 - rho * rho)
    H = len(hz)
    A = len(az)
    out = np.zeros((H, A), dtype=float)
    # Precompute per-home-threshold quadrature abscissae x and jacobian.
    for i in range(H):
        h = hz[i]
        upper = float(norm.cdf(h))
        if upper <= 0.0:
            continue  # row stays 0
        if h >= _Z_CLAMP:
            # Phi2(+inf, k) = Phi(k)
            out[i, :] = norm.cdf(az)
            continue
        u = 0.5 * upper * (_GL_NODES + 1.0)
        jac = 0.5 * upper
        x = norm.ppf(np.clip(u, 1e-15, 1 - 1e-15))  # (n_nodes,)
        # integrand for every away threshold: Phi((az - rho x)/s), shape (nodes, A)
        arg = (az[None, :] - rho * x[:, None]) / s
        integrand = norm.cdf(arg)
        out[i, :] = (_GL_WEIGHTS[:, None] * integrand).sum(axis=0) * jac
    return out


@dataclass(frozen=True)
class JointCornerDistribution:
    """A joint home/away count distribution with a signed dependence rho.

    Preserves the two input marginals; the total PMF is derived from the joint.
    ``rho == 0`` reproduces the independence convolution exactly.
    """

    home_pmf: np.ndarray
    away_pmf: np.ndarray
    rho: float
    joint: np.ndarray  # shape (len(home_pmf), len(away_pmf))
    _total: np.ndarray

    @property
    def expected_total(self) -> float:
        idx_h = np.arange(len(self.home_pmf))
        idx_a = np.arange(len(self.away_pmf))
        return float((self.home_pmf * idx_h).sum() + (self.away_pmf * idx_a).sum())

    @property
    def total_pmf(self) -> tuple[float, ...]:
        return tuple(float(v) for v in self._total)

    @property
    def total_variance(self) -> float:
        idx = np.arange(len(self._total))
        mean = float((idx * self._total).sum())
        return float(((idx - mean) ** 2 * self._total).sum())

    def p_over(self, line: float) -> float:
        cutoff = math.floor(line)
        if cutoff < 0:
            return 1.0
        if cutoff >= len(self._total) - 1:
            return 0.0
        return min(1.0, max(0.0, 1.0 - float(self._total[: cutoff + 1].sum())))

    def p_under(self, line: float) -> float:
        return 1.0 - self.p_over(line)

    def recovered_home_marginal(self) -> np.ndarray:
        return self.joint.sum(axis=1)

    def recovered_away_marginal(self) -> np.ndarray:
        return self.joint.sum(axis=0)

    # Note: the total PMF is symmetric under a home<->away swap up to ~1e-6
    # (bivariate-normal quadrature tolerance), not exactly, which is immaterial
    # for O/U probabilities at integer cutoffs.


def build_joint(
    home_pmf: Sequence[float], away_pmf: Sequence[float], rho: float
) -> JointCornerDistribution:
    """Couple two side PMFs with a Gaussian copula at correlation ``rho``.

    At rho == 0 the joint is exactly the outer product (independence), so the
    total PMF equals ``np.convolve(home_pmf, away_pmf)``.

    Marginals are preserved: the joint is IPF-normalised (a single proportional
    fit) back onto the input marginals to absorb any quadrature drift, which is a
    no-op at rho==0 and tiny elsewhere. This guarantees
    ``sum_j joint[i,j] == home_pmf[i]`` and ``sum_i joint[i,j] == away_pmf[j]``.
    """
    h = np.asarray(home_pmf, dtype=float)
    a = np.asarray(away_pmf, dtype=float)
    h = h / h.sum() if h.sum() > 0 else h
    a = a / a.sum() if a.sum() > 0 else a

    if rho == 0.0:
        joint = np.outer(h, a)
    else:
        hz = _cdf_thresholds(h)  # len(h)+1
        az = _cdf_thresholds(a)  # len(a)+1
        # Vectorized bivariate-normal CDF on the full threshold grid, then form
        # rectangle probabilities by 2D finite differences:
        #   joint[i,j] = C[i+1,j+1] - C[i,j+1] - C[i+1,j] + C[i,j]
        cdf_grid = _bivar_normal_cdf_grid(hz, az, rho)  # (len(h)+1, len(a)+1)
        joint = (
            cdf_grid[1:, 1:] - cdf_grid[:-1, 1:] - cdf_grid[1:, :-1] + cdf_grid[:-1, :-1]
        )
        joint = np.clip(joint, 0.0, None)
        joint[h <= 0.0, :] = 0.0
        joint[:, a <= 0.0] = 0.0
        # Iterative proportional fitting onto the exact input marginals so the
        # copula NEVER distorts the calibrated side distributions.
        joint = _ipf_to_marginals(joint, h, a)

    total_len = len(h) + len(a) - 1
    total = np.zeros(total_len, dtype=float)
    # total[k] = sum over i+j=k of joint[i,j]
    for i in range(len(h)):
        row = joint[i]
        total[i : i + len(a)] += row
    s = total.sum()
    if s > 0:
        total = total / s
    return JointCornerDistribution(
        home_pmf=h, away_pmf=a, rho=float(rho), joint=joint, _total=total
    )


def _ipf_to_marginals(
    joint: np.ndarray, target_row: np.ndarray, target_col: np.ndarray, *, iters: int = 12
) -> np.ndarray:
    """Iterative proportional fitting so joint's margins == the target margins.

    Preserves the copula's dependence structure (odds ratios) while forcing the
    marginals to equal the calibrated side PMFs exactly. Converges in a few
    iterations for a well-formed copula grid.
    """
    m = np.clip(joint, 0.0, None).copy()
    if m.sum() <= 0:
        return np.outer(target_row, target_col)
    for _ in range(iters):
        row_sums = m.sum(axis=1)
        scale_r = np.divide(target_row, row_sums, out=np.zeros_like(target_row), where=row_sums > 0)
        m = m * scale_r[:, None]
        col_sums = m.sum(axis=0)
        scale_c = np.divide(target_col, col_sums, out=np.zeros_like(target_col), where=col_sums > 0)
        m = m * scale_c[None, :]
        # convergence check
        if np.max(np.abs(m.sum(axis=1) - target_row)) < 1e-12:
            break
    return m
